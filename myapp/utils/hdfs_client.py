"""
HDFS Client Utility — Kerberos-authenticated HDFS operations.

基于用户 demo 代码中使用的 hdfs 库 (KerberosClient) 封装:
  - 目录浏览 (分页)
  - 模糊搜索路径
  - 按分区列 + 日期范围列出 parquet 文件
  - 文件下载 (支持进度回调、断点续传)
  - Parquet schema 读取 (PyArrow)
  - Parquet 数据预览 (PyArrow)
"""

import os
import re
import json
import logging
import time
import subprocess
import traceback
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 单次 list_parquet_files 最大递归深度，防止深层目录结构导致过多 HDFS 调用
MAX_RECURSION_DEPTH = 5


class HDFSConfig:
    """HDFS 连接配置，从 app.config['HDFS_CONFIG'] 读取。"""

    def __init__(self, config_dict=None):
        config_dict = config_dict or {}
        self.url = config_dict.get('url', os.getenv('HDFS_URL', ''))
        self.keytab_path = config_dict.get('keytab_path', os.getenv('HDFS_KEYTAB_PATH', ''))
        self.principal = config_dict.get('principal', os.getenv('HDFS_PRINCIPAL', ''))
        self.base_path = config_dict.get('base_path', os.getenv('HDFS_BASE_PATH', '/user/hive/warehouse'))
        self.timeout = config_dict.get('timeout', 30)

    def is_valid(self):
        return bool(self.url and self.keytab_path and self.principal)


class HDFSClient:
    """
    基于 Kerberos 认证的 HDFS 客户端。

    用法:
        config = HDFSConfig(app.config.get('HDFS_CONFIG', {}))
        client = HDFSClient(config)
        dirs, files = client.list_dir('/user/hive/warehouse')
        client.download('/remote/path/file.parquet', '/local/path/file.parquet')
        client.close()
    """

    # 分区列候选名 (按优先级)
    PARTITION_COL_CANDIDATES = ['dt', 'partition_dt', 'date', 'p_date', 'day', 'fdate']

    def __init__(self, config: HDFSConfig):
        self.config = config
        self._client = None
        if config.is_valid():
            self._authenticate()

    # ─── 认证与连接池 ─────────────────────────────────────────

    _auth_time = None       # 上次 kinit 时间 (类级共享)
    _auth_lock = None       # 线程锁 (延迟初始化)

    @classmethod
    def _get_auth_lock(cls):
        import threading
        if cls._auth_lock is None:
            cls._auth_lock = threading.Lock()
        return cls._auth_lock

    def _authenticate(self):
        """Kerberos kinit 认证 (subprocess.run 替代 os.system)。"""
        # 检查 ticket 缓存是否仍有效 (klist 检查)
        if not self._ticket_valid():
            with self._get_auth_lock():
                if not self._ticket_valid():
                    keytab = self.config.keytab_path
                    principal = self.config.principal
                    try:
                        result = subprocess.run(
                            ['kinit', '-kt', keytab, principal],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if result.returncode != 0:
                            stderr = result.stderr.strip() or result.stdout.strip()
                            raise RuntimeError(
                                f'kinit 认证失败 (exit={result.returncode}): {stderr}'
                            )
                    except subprocess.TimeoutExpired:
                        raise RuntimeError('kinit 认证超时 (30s)')
                    except FileNotFoundError:
                        raise RuntimeError(
                            'kinit 命令不可用，请安装 krb5-user 包'
                        )
                    HDFSClient._auth_time = datetime.now()

        try:
            from hdfs.ext.kerberos import KerberosClient
            self._client = KerberosClient(self.config.url, timeout=self.config.timeout)
            # 验证连接: 尝试列出根目录
            self._client.status('/')
            logger.info(f'HDFS KerberosClient 已连接到 {self.config.url}')
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(f'''HDFS Kerberos 客户端初始化失败: {e}
请安装系统依赖:
  apt-get install -y krb5-user libkrb5-dev
  pip install requests_kerberos hdfs''')
            raise RuntimeError(f'缺少 Kerberos 依赖: {e}. 请安装 krb5-user, libkrb5-dev, requests_kerberos')
        except Exception as e:
            logger.error(f'HDFS 连接失败: {e}')
            # 连接失败意味着 ticket 可能无效，重置认证时间
            HDFSClient._auth_time = None
            raise RuntimeError(f'HDFS 连接失败: {e}')

    def _ticket_valid(self):
        """检查 Kerberos ticket 是否有效 (距上次 kinit < 9 小时视为有效)。"""
        if HDFSClient._auth_time is None:
            return False
        elapsed = datetime.now() - HDFSClient._auth_time
        # Kerberos ticket 默认 10h 有效期，9h 提前刷新
        if elapsed > timedelta(hours=9):
            return False
        return True

    @property
    def client(self):
        """延迟初始化 + 自动重连。"""
        if self._client is None:
            self._authenticate()
        return self._client

    def _ensure_connected(self):
        """确保连接有效，必要时重新认证。"""
        try:
            # 尝试列出根目录来检测连接
            if self._client is None:
                self._authenticate()
                return
            self._client.status('/')
        except Exception:
            logger.info('HDFS 连接可能已过期，尝试重新认证...')
            self._authenticate()

    # ─── 目录浏览 ───────────────────────────────────────────

    def list_dir(self, path='', page=1, page_size=50, max_items=100) -> dict:
        """
        分页列出目录内容。

        返回:
            {
                'dirs': [{name, path, mtime}],
                'files': [{name, path, size, mtime}],
                'has_more': bool,
                'total_count': int,
                'current_path': str
            }
        """
        self._ensure_connected()
        path = self._normalize_path(path)

        try:
            raw = self.client.list(path, status=True)
        except Exception as e:
            logger.error(f'list_dir 失败 path={path}: {e}')
            raise

        dirs = []
        files = []

        for item_name, item_status in raw:
            full_path = os.path.join(path, item_name) if path else '/' + item_name
            mtime = item_status.get('modificationTime', '')
            if isinstance(mtime, (int, float)):
                mtime = datetime.fromtimestamp(mtime / 1000).strftime('%Y-%m-%d %H:%M:%S')

            if item_status.get('type') == 'DIRECTORY':
                dirs.append({
                    'name': item_name,
                    'path': full_path,
                    'mtime': mtime,
                })
            else:
                files.append({
                    'name': item_name,
                    'path': full_path,
                    'size': item_status.get('length', 0),
                    'mtime': mtime,
                })

        # 排序: 目录在前, 按名称排序
        dirs.sort(key=lambda d: d['name'].lower())
        files.sort(key=lambda f: f['name'].lower())

        # 截断：目录树最多展示 max_items 条
        original_dir_count = len(dirs)
        truncated = original_dir_count > max_items
        dirs = dirs[:max_items]

        # total_count 基于截断后数据，保证分页一致性
        total_count = len(dirs) + len(files)

        # 分页 (简化实现: 先合在一起分页)
        all_items = [{'type': 'dir', **d} for d in dirs] + [{'type': 'file', **f} for f in files]
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_items[start:end]

        result_dirs = [i for i in page_items if i['type'] == 'dir']
        result_files = [i for i in page_items if i['type'] == 'file']
        # 去掉 type key
        for d in result_dirs:
            del d['type']
        for f in result_files:
            del f['type']

        return {
            'dirs': result_dirs,
            'files': result_files,
            'has_more': end < total_count,
            'total_count': total_count,
            'current_path': path,
            'truncated': truncated,
        }

    # ─── 模糊搜索（非递归）───────────────────────────────────

    # 搜表时最多搜索多少个匹配的库 (防止遍历过多目录)
    MAX_SEARCH_DBS = 15

    def search(self, base_path, query, table_query='', limit=1000) -> list:
        """
        非递归模糊搜索。
          - query: 库名关键词，在 base_path 下搜索匹配的库 (空字符串 = 列出所有库)
          - table_query: 表名关键词（可选），在匹配到的库下搜索表
            - 搜不到时仅在 query 极短 (≤2字符) 时回退展示该库下全部目录
            - 为空时仅搜库
          - limit: 总结果数上限

        返回: [{name, path, depth}]
        """
        self._ensure_connected()
        base_path = self._normalize_path(base_path)

        # 一次性获取 base_path 下列表，缓存复用避免重复 HDFS 调用
        try:
            base_raw = self.client.list(base_path, status=True)
        except Exception as e:
            logger.error(f'搜索失败: 无法列出 {base_path}: {e}')
            return []

        start_time = time.time()

        if query:
            dbs = self._filter_matching_dirs(base_raw, base_path, query, limit=200)
        else:
            # 无搜索词：列出所有库 (限制 200 个)
            dbs = self._all_dirs_from_listing(base_raw, base_path, limit=200, depth=0)

        elapsed = time.time() - start_time
        if elapsed > 5:
            logger.warning(f'搜索库阶段耗时 {elapsed:.1f}s, query="{query}", 匹配 {len(dbs)} 个库')

        if not table_query:
            return dbs

        # 有表名：在匹配的库下搜表 (限制搜索的库数量)
        if len(dbs) > self.MAX_SEARCH_DBS:
            logger.warning(
                f'匹配的库过多 ({len(dbs)} > {self.MAX_SEARCH_DBS})，'
                f'仅搜索前 {self.MAX_SEARCH_DBS} 个'
            )
            dbs = dbs[:self.MAX_SEARCH_DBS]

        results = []
        for db in dbs:
            remaining = limit - len(results)
            if remaining <= 0:
                break
            try:
                db_raw = self.client.list(db['path'], status=True)
            except Exception:
                logger.warning(f'搜索表失败: 无法列出 {db["path"]}')
                continue

            tables = self._filter_matching_dirs(
                db_raw, db['path'], table_query, limit=remaining, depth=1
            )

            if not tables and len(table_query) <= 2:
                # 仅极短搜索词才回退展示全部 (长词不回退，避免返回无关结果)
                tables = self._all_dirs_from_listing(
                    db_raw, db['path'], limit=remaining, depth=1
                )

            results.extend(tables)

        elapsed_total = time.time() - start_time
        if elapsed_total > 10:
            logger.warning(
                f'搜索总耗时 {elapsed_total:.1f}s, query="{query}", '
                f'table_query="{table_query}", 结果 {len(results)} 条'
            )

        return results

    def _filter_matching_dirs(self, raw_listing: list, parent_path: str,
                              query_str: str, limit: int, depth: int = 0) -> list:
        """从已有的 listing 结果中筛选匹配的子目录。"""
        results = []
        q = query_str.lower()
        for item_name, item_status in raw_listing:
            if len(results) >= limit:
                break
            if item_status.get('type') != 'DIRECTORY':
                continue
            if q in item_name.lower():
                full_path = os.path.join(parent_path, item_name)
                results.append({
                    'name': item_name,
                    'path': full_path,
                    'depth': depth,
                })
        return results

    def _all_dirs_from_listing(self, raw_listing: list, parent_path: str,
                               limit: int, depth: int = 0) -> list:
        """从已有的 listing 结果中提取所有子目录 (无过滤)。"""
        results = []
        for item_name, item_status in raw_listing:
            if len(results) >= limit:
                break
            if item_status.get('type') == 'DIRECTORY':
                results.append({
                    'name': item_name,
                    'path': os.path.join(parent_path, item_name),
                    'depth': depth,
                })
        return results

    def _list_matching_dirs(self, path, query_str, limit, depth=0):
        """列出目录下名称匹配 query 的子目录（单层，不递归）。
        保留用于向后兼容，内部委托给 _filter_matching_dirs。
        """
        try:
            raw = self.client.list(path, status=True)
        except Exception:
            logger.warning(f'_list_matching_dirs 失败 path={path}')
            return []
        return self._filter_matching_dirs(raw, path, query_str, limit, depth=depth)

    # ─── 按分区列 + 日期列出 Parquet 文件 ────────────────────

    def list_parquet_files(self, path, partition_col=None, date_start=None, date_end=None,
                           max_files=2000, _depth=0) -> list:
        """
        列出目录下的 parquet 文件，支持按分区列和日期范围过滤。

        参数:
            path: HDFS 目录路径
            partition_col: 分区列名 (None 则自动检测 dt= 或 partition_dt=)
            date_start: 起始日期 (YYYYMMDD 格式)
            date_end: 截止日期 (YYYYMMDD 格式)

        返回: [{name, path, size, mtime, partition_value}]
        """
        self._ensure_connected()
        path = self._normalize_path(path)

        # 自动检测分区列
        if not partition_col:
            partition_col = self._detect_partition_col(path)

        result_files = []

        try:
            raw = self.client.list(path, status=True)
        except Exception as e:
            logger.error(f'list_parquet_files 失败 path={path}: {e}')
            raise

        # 分区目录按名称倒序排列，优先展示最新分区
        sorted_items = sorted(raw, key=lambda x: x[0], reverse=True)

        for item_name, item_status in sorted_items:
            if len(result_files) >= max_files:
                break
            try:
                item_type = item_status.get('type', '')
                if item_type == 'DIRECTORY' and partition_col:
                    # 检查是否是分区目录 (如 dt=20260620)
                    partition_value = self._parse_partition_value(item_name, partition_col)
                    if partition_value:
                        if self._in_date_range(partition_value, date_start, date_end):
                            # 进入分区目录，收集 parquet 文件
                            sub_path = os.path.join(path, item_name)
                            try:
                                sub_raw = self.client.list(sub_path, status=True)
                            except Exception:
                                continue
                            for sub_name, sub_status in sub_raw:
                                if len(result_files) >= max_files:
                                    break
                                if self._is_parquet_file(sub_name):
                                    result_files.append({
                                        'name': sub_name,
                                        'path': os.path.join(sub_path, sub_name),
                                        'size': sub_status.get('length', 0),
                                        'mtime': self._format_mtime(sub_status.get('modificationTime')),
                                        'partition_value': partition_value,
                                    })
                    else:
                        # 可能是中间层目录 (如 extra_folder)，递归进入 (有深度限制)
                        if _depth >= MAX_RECURSION_DEPTH:
                            continue
                        if len(result_files) >= max_files:
                            break
                        sub_path = os.path.join(path, item_name)
                        try:
                            remaining = max_files - len(result_files)
                            result_files.extend(
                                self.list_parquet_files(
                                    sub_path, partition_col, date_start, date_end,
                                    max_files=remaining, _depth=_depth + 1,
                                )
                            )
                        except Exception:
                            pass
                elif item_type != 'DIRECTORY' and self._is_parquet_file(item_name):
                    result_files.append({
                        'name': item_name,
                        'path': os.path.join(path, item_name),
                        'size': item_status.get('length', 0),
                        'mtime': self._format_mtime(item_status.get('modificationTime')),
                        'partition_value': None,
                    })
            except Exception:
                continue

        return result_files

    def _detect_partition_col(self, path):
        """自动检测路径下第一个目录使用的分区列名。"""
        try:
            raw = self.client.list(path, status=True)
            for item_name, item_status in raw:
                if item_status.get('type') == 'DIRECTORY':
                    for col in self.PARTITION_COL_CANDIDATES:
                        if item_name.startswith(f'{col}='):
                            return col
        except Exception:
            pass
        return 'dt'  # 默认

    def _parse_partition_value(self, dir_name, partition_col):
        """解析分区值，如 'dt=20260620' → '20260620'。"""
        prefix = f'{partition_col}='
        if dir_name.startswith(prefix):
            return dir_name[len(prefix):]
        return None

    def _in_date_range(self, partition_value, date_start, date_end):
        """检查分区值是否在日期范围内。"""
        if not partition_value:
            return True  # 无分区值则全部返回
        if not date_start and not date_end:
            return True

        # 提取 partition_value 中的日期部分 (可能包含 - 如 2026-06-20)
        date_str = re.sub(r'[^0-9]', '', partition_value)[:8]
        if len(date_str) < 8:
            return True

        if date_start and date_str < date_start.replace('-', '')[:8]:
            return False
        if date_end and date_str > date_end.replace('-', '')[:8]:
            return False
        return True

    # ─── 文件下载 ───────────────────────────────────────────

    def download(self, remote_path, local_path, progress_callback=None, resume=True):
        """
        下载单个文件。

        参数:
            remote_path: HDFS 远程路径
            local_path: 本地目标路径
            progress_callback: 进度回调 fn(bytes_downloaded, total_bytes)
            resume: 是否支持断点续传 (检查本地已有文件 + .partial 标记)

        返回:
            {'success': bool, 'local_path': str, 'size': int, 'skipped': bool}
        """
        self._ensure_connected()

        # 获取远程文件大小
        try:
            status = self.client.status(remote_path)
            remote_size = status.get('length', 0)
        except Exception as e:
            logger.error(f'获取文件状态失败 {remote_path}: {e}')
            raise

        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        partial_marker = local_path + '.partial'

        # 断点续传检查：文件存在 + 无 .partial 标记 + 大小匹配 → 跳过
        if resume and os.path.exists(local_path) and not os.path.exists(partial_marker):
            local_size = os.path.getsize(local_path)
            if local_size == remote_size and remote_size > 0:
                logger.info(f'文件已完整存在，跳过: {local_path}')
                return {
                    'success': True,
                    'local_path': local_path,
                    'size': remote_size,
                    'skipped': True,
                }

        # 下载前写入 .partial 标记 (用于识别未完成下载)
        with open(partial_marker, 'w') as pm:
            pm.write(str(int(time.time())))

        try:
            # 使用 hdfs 库的 download 方法
            self.client.download(remote_path, local_path, overwrite=True)

            # 下载成功，移除 .partial 标记
            if os.path.exists(partial_marker):
                os.remove(partial_marker)

            if progress_callback:
                progress_callback(remote_size, remote_size)

            logger.info(f'下载完成: {remote_path} → {local_path} ({remote_size} bytes)')
            return {
                'success': True,
                'local_path': local_path,
                'size': remote_size,
                'skipped': False,
            }

        except Exception as e:
            logger.error(f'下载失败 {remote_path}: {e}')
            # 保留部分下载的文件和 .partial 标记，下次可续传
            raise

    # ─── Parquet 操作 (PyArrow) ──────────────────────────────

    def read_schema(self, file_path):
        """
        读取 parquet 文件的 schema。

        返回: [{'name': 'col1', 'type': 'int64'}, ...]
        """
        try:
            import pyarrow.parquet as pq
            parquet_file = pq.ParquetFile(file_path)
            schema = parquet_file.schema_arrow
            return [{'name': field.name, 'type': str(field.type)} for field in schema]
        except ImportError:
            logger.error('pyarrow 未安装')
            raise
        except Exception as e:
            logger.error(f'读取 schema 失败 {file_path}: {e}')
            raise

    def read_preview(self, file_path, nrows=10):
        """
        读取 parquet 文件的前 N 行数据。

        返回: [{'col1': val1, 'col2': val2, ...}, ...]
        """
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(file_path).slice(0, nrows)
            # 转换为 dict 列表
            columns = table.column_names
            rows = []
            for i in range(table.num_rows):
                row = {}
                for col in columns:
                    val = table[col][i].as_py()
                    # 处理特殊类型
                    if isinstance(val, bytes):
                        try:
                            val = val.decode('utf-8')
                        except Exception:
                            val = str(val)
                    elif hasattr(val, 'isoformat'):  # datetime
                        val = val.isoformat()
                    row[col] = val
                rows.append(row)
            return rows
        except ImportError:
            logger.error('pyarrow 未安装')
            raise
        except Exception as e:
            logger.error(f'读取 preview 失败 {file_path}: {e}')
            raise

    # ─── 工具方法 ───────────────────────────────────────────

    def _normalize_path(self, path):
        """规范化路径。"""
        if not path or path == '/':
            return self.config.base_path
        if not path.startswith('/'):
            path = '/' + path
        # 如果 path 不是从 base_path 开始的，自动添加
        if self.config.base_path and not path.startswith(self.config.base_path):
            path = os.path.join(self.config.base_path, path.lstrip('/'))
        return path

    @staticmethod
    def _is_parquet_file(name):
        """判断是否为 parquet 文件。"""
        return name.endswith('.parquet') or name.endswith('.parq') or name.endswith('.pq')

    @staticmethod
    def _format_mtime(mtime_val):
        """格式化修改时间。"""
        if mtime_val is None:
            return ''
        if isinstance(mtime_val, (int, float)):
            try:
                return datetime.fromtimestamp(mtime_val / 1000).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return str(mtime_val)
        return str(mtime_val)

    def close(self):
        """关闭客户端连接。"""
        self._client = None
        logger.info('HDFSClient 已关闭')


# ─── 从 app.config 创建客户端的工厂函数 ────────────────────


def get_hdfs_client(config_dict=None):
    """
    从 flask app.config 创建 HDFSClient 实例。

    用法:
        from myapp.utils.hdfs_client import get_hdfs_client
        client = get_hdfs_client(app.config.get('HDFS_CONFIG'))
    """
    config = HDFSConfig(config_dict)
    if not config.is_valid():
        logger.warning('HDFS_CONFIG 不完整，HDFSClient 将无法使用')
    return HDFSClient(config)
