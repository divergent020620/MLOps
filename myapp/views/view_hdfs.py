"""
HDFS 浏览器 API — 提供 HDFS 目录浏览、搜索、文件列表等 REST 端点。

参考 SQLLab 模式 (view_sqllab.py): BaseMyappView + @expose_api

端点:
  GET  /hdfs_browser/api/list_dir      — 浏览目录 (分页)
  GET  /hdfs_browser/api/search        — 模糊搜索路径
  GET  /hdfs_browser/api/list_files    — 列出 parquet 文件 (支持日期过滤)
  GET  /hdfs_browser/api/get_schema    — 获取 parquet 文件 schema
  GET  /hdfs_browser/api/get_config    — 获取 HDFS 配置信息
"""

import traceback
import logging
import json
import time

from flask_appbuilder.baseviews import expose_api
from flask import jsonify, g, request

import os as _os

from myapp import app, appbuilder, db
from myapp.views.base import BaseMyappView
from myapp.utils.hdfs_client import HDFSClient, HDFSConfig

conf = app.config
logger = logging.getLogger(__name__)

# 持久化配置文件路径
HDFS_CONFIG_FILE = _os.path.join(conf.get('DATA_DIR', '/home/myapp'), 'hdfs_config.json')

# HDFSClient 实例缓存 (避免每次请求都 kinit)
_client_cache = None
_client_cache_time = 0
_CLIENT_CACHE_TTL = 600  # 10分钟


def _load_persisted_config():
    """加载持久化的 HDFS 配置 (JSON 文件)，优先于 env/config.py 默认值。"""
    base = conf.get('HDFS_CONFIG', {}).copy()
    if _os.path.exists(HDFS_CONFIG_FILE):
        try:
            with open(HDFS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            base.update(saved)
        except Exception:
            pass
    return base


def _save_persisted_config(config_dict):
    """保存 HDFS 配置到 JSON 文件。"""
    current = {}
    if _os.path.exists(HDFS_CONFIG_FILE):
        try:
            with open(HDFS_CONFIG_FILE, 'r', encoding='utf-8') as f:
                current = json.load(f)
        except Exception:
            pass
    current.update(config_dict)
    _os.makedirs(_os.path.dirname(HDFS_CONFIG_FILE), exist_ok=True)
    with open(HDFS_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def _get_client():
    """
    创建或复用 HDFS 客户端实例。缓存 10 分钟避免每次都 kinit。
    """
    global _client_cache, _client_cache_time
    now = time.time()

    if _client_cache is not None and (now - _client_cache_time) < _CLIENT_CACHE_TTL:
        # 尝试验证缓存的连接是否仍然有效
        try:
            _client_cache.client.status('/')
            return _client_cache, None
        except Exception:
            # 连接失效，关闭旧连接后重新创建
            try:
                _client_cache.close()
            except Exception:
                pass
            _client_cache = None

    hdfs_conf = _load_persisted_config()
    config = HDFSConfig(hdfs_conf)
    if not config.is_valid():
        return None, 'HDFS 配置不完整，请联系管理员配置 HDFS_URL / HDFS_KEYTAB_PATH / HDFS_PRINCIPAL'
    try:
        client = HDFSClient(config)
        _client_cache = client
        _client_cache_time = now
        return client, None
    except Exception as e:
        return None, f'HDFS 连接失败: {str(e)}'


class HDFS_Browser_View(BaseMyappView):
    route_base = '/hdfs_browser/api'

    # ─── 获取配置 ─────────────────────────────────────────────

    @expose_api(description='获取HDFS配置信息', url='/get_config', methods=['GET'])
    def get_config(self):
        """
        返回 HDFS 配置摘要 (不暴露 keytab 路径等敏感信息)。
        不做实际连接测试，仅检查配置完整性。
        """
        hdfs_conf = _load_persisted_config()
        config = HDFSConfig(hdfs_conf)
        valid = config.is_valid()
        return jsonify({
            'status': 0,
            'message': '',
            'result': {
                'base_path': hdfs_conf.get('base_path', '/user/hive/warehouse'),
                'url': hdfs_conf.get('url', ''),
                'connected': None,  # 不主动连接，前端通过 HDFSConfig 页面的"刷新状态"获取
                'configured': valid,
                'connect_error': None if valid else 'HDFS 配置不完整，请联系管理员',
                'partition_col_candidates': HDFSClient.PARTITION_COL_CANDIDATES,
                'preview_rows': conf.get('DATASET_PREVIEW_ROWS', 10),
                'is_admin': g.user.is_admin() if hasattr(g.user, 'is_admin') else False,
            }
        })

    @expose_api(description='测试HDFS连接', url='/test_connection', methods=['GET'])
    def test_connection(self):
        """显式测试 HDFS 连接（执行 kinit + status），用于 HDFSConfig 页面刷新。"""
        client, err = _get_client()
        connected = client is not None
        hdfs_conf = _load_persisted_config()
        if client:
            try:
                client.close()
            except Exception:
                pass
        return jsonify({
            'status': 0,
            'message': '',
            'result': {
                'connected': connected,
                'connect_error': err if not connected else None,
                'base_path': hdfs_conf.get('base_path', '/user/hive/warehouse'),
                'url': hdfs_conf.get('url', ''),
            }
        })

    # ─── Admin: 完整配置 (含敏感信息) ───────────────────────

    @expose_api(description='获取完整HDFS配置(admin)', url='/get_config_full', methods=['GET'])
    def get_config_full(self):
        """返回完整 HDFS 配置，仅 admin 可访问。"""
        if not g.user.is_admin():
            return jsonify({'status': 1, 'message': '仅管理员可访问', 'result': None})
        hdfs_conf = _load_persisted_config()
        # 也返回 dataset 存储路径
        result = {
            'url': hdfs_conf.get('url', ''),
            'keytab_path': hdfs_conf.get('keytab_path', ''),
            'principal': hdfs_conf.get('principal', ''),
            'base_path': hdfs_conf.get('base_path', '/user/hive/warehouse'),
            'datasavepath': hdfs_conf.get('datasavepath', conf.get('DATASET_SAVEPATH', '/data/k8s/kubeflow/datasets')),
            'page_size': hdfs_conf.get('page_size', 50),
        }
        return jsonify({
            'status': 0,
            'message': '',
            'result': result
        })

    # ─── Admin: 保存配置 ────────────────────────────────────

    @expose_api(description='保存HDFS配置(admin)', url='/save_config', methods=['POST'])
    def save_config(self):
        """保存 HDFS 连接配置，仅 admin 可操作。"""
        if not g.user.is_admin():
            return jsonify({'status': 1, 'message': '仅管理员可保存配置', 'result': None})

        req_data = request.get_json(silent=True) or {}
        allowed_keys = ['url', 'keytab_path', 'principal', 'base_path', 'datasavepath']

        updates = {k: req_data[k] for k in allowed_keys if k in req_data}
        if not updates:
            return jsonify({'status': 1, 'message': '无有效配置项', 'result': None})

        _save_persisted_config(updates)

        # 测试新配置是否能连接
        client, err = _get_client()
        connected = client is not None
        if client:
            client.close()

        return jsonify({
            'status': 0,
            'message': '配置已保存' + ('，连接测试成功' if connected else f'，但连接测试失败: {err}'),
            'result': {
                'saved': updates,
                'connected': connected,
                'connect_error': err if not connected else None,
            }
        })

    # ─── 浏览目录 (分页) ─────────────────────────────────────

    @expose_api(description='浏览HDFS目录', url='/list_dir', methods=['GET'])
    def list_dir(self):
        """
        分页列出 HDFS 目录内容。

        Query 参数:
            path:      目录路径 (相对于 base_path 或绝对路径)
            page:      页码 (默认 1)
            page_size: 每页条数 (默认 50, 最大 200)

        返回:
            {dirs: [{name, path, mtime}], files: [{name, path, size, mtime}],
             has_more, total_count, current_path}
        """
        client, err = _get_client()
        if not client:
            return jsonify({'status': 1, 'message': err, 'result': None})

        try:
            path = request.args.get('path', '')
            page = max(1, int(request.args.get('page', 1)))
            page_size = min(200, max(10, int(request.args.get('page_size', 50))))

            result = client.list_dir(path, page=page, page_size=page_size)
            return jsonify({
                'status': 0,
                'message': '',
                'result': result,
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({'status': 1, 'message': f'目录浏览失败: {str(e)}', 'result': None})
        finally:
            pass  # 客户端已缓存，不关闭

    # ─── 模糊搜索 ─────────────────────────────────────────────

    @expose_api(description='模糊搜索HDFS路径', url='/search', methods=['GET'])
    def search(self):
        """
        模糊搜索 HDFS 路径 (匹配 db/table 名称)。

        Query 参数:
            q:     库名关键词
            table: 表名关键词（可选，为空则仅搜库）
            limit: 返回数量限制 (默认 20)

        返回:
            [{name, path, depth}]
        """
        client, err = _get_client()
        if not client:
            return jsonify({'status': 1, 'message': err, 'result': None})

        try:
            query = request.args.get('q', '').strip()
            if not query:
                return jsonify({'status': 0, 'message': '', 'result': []})

            table_query = request.args.get('table', '').strip()
            limit = max(5, int(request.args.get('limit', 1000)))

            results = client.search('', query, table_query=table_query, limit=limit)
            return jsonify({
                'status': 0,
                'message': '',
                'result': results,
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({'status': 1, 'message': f'搜索失败: {str(e)}', 'result': []})
        finally:
            pass  # 客户端已缓存，不关闭

    # ─── 列出 Parquet 文件 (按日期) ────────────────────────────

    @expose_api(description='列出parquet文件(支持日期过滤)', url='/list_files', methods=['GET'])
    def list_files(self):
        """
        列出目录下的 parquet 文件，支持按分区列和日期范围过滤。

        Query 参数:
            path:           目录路径
            partition_col:  分区列名 (如 dt, partition_dt; 不传则自动检测)
            date_start:     起始日期 (YYYYMMDD 或 YYYY-MM-DD)
            date_end:       截止日期 (YYYYMMDD 或 YYYY-MM-DD)

        返回:
            [{name, path, size, mtime, partition_value}]
        """
        client, err = _get_client()
        if not client:
            return jsonify({'status': 1, 'message': err, 'result': None})

        try:
            path = request.args.get('path', '')
            if not path:
                return jsonify({'status': 1, 'message': '请指定路径 path 参数', 'result': None})

            partition_col = request.args.get('partition_col') or None
            date_start = request.args.get('date_start') or None
            date_end = request.args.get('date_end') or None

            # 最多返回 2000 个文件，超过则标记截断
            MAX_FILES = 2000
            files = client.list_parquet_files(
                path=path,
                partition_col=partition_col,
                date_start=date_start,
                date_end=date_end,
                max_files=MAX_FILES,
            )
            truncated = len(files) >= MAX_FILES

            # 汇总信息
            total_size = sum(f.get('size', 0) for f in files)
            partition_values = sorted(set(
                f.get('partition_value') for f in files if f.get('partition_value')
            ))

            return jsonify({
                'status': 0,
                'message': '',
                'result': {
                    'files': files,
                    'total_count': len(files),
                    'total_size': total_size,
                    'partition_values': partition_values,
                    'detected_partition_col': partition_col,
                    'truncated': truncated,
                }
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({'status': 1, 'message': f'文件列表获取失败: {str(e)}', 'result': None})
        finally:
            pass  # 客户端已缓存，不关闭

    # ─── 获取 Parquet Schema ──────────────────────────────────

    # Parquet footer 默认读取大小 (覆盖大部分场景的 footer + metadata)
    PARQUET_TAIL_READ_SIZE = 1024 * 1024  # 1MB

    @expose_api(description='获取parquet文件schema', url='/get_schema', methods=['GET'])
    def get_schema(self):
        """
        获取 HDFS 上 parquet 文件的 schema (列名+类型)。
        优化：只读取文件尾部 footer，不下载整个文件。

        Query 参数:
            path: parquet 文件在 HDFS 上的路径

        返回:
            {columns: [{name, type}]}
        """
        client, err = _get_client()
        if not client:
            return jsonify({'status': 1, 'message': err, 'result': None})

        try:
            file_path = request.args.get('path', '')
            if not file_path:
                return jsonify({'status': 1, 'message': '请指定文件路径 path', 'result': None})

            # 获取文件大小
            try:
                file_status = client.client.status(file_path)
                file_size = file_status.get('length', 0)
            except Exception as e:
                return jsonify({
                    'status': 1,
                    'message': f'获取文件信息失败: {str(e)}',
                    'result': None,
                })

            if file_size == 0:
                return jsonify({
                    'status': 1,
                    'message': '文件大小为 0，无法读取 schema',
                    'result': None,
                })

            # Parquet 文件最后 4 字节是 magic bytes "PAR1"
            # 再往前 4 字节是 footer length (小端 int32)
            read_size = min(self.PARQUET_TAIL_READ_SIZE, file_size)
            tail_data = None

            try:
                # 用 hdfs 库的 read() 读取文件尾部 (支持 offset + length)
                with client.client.read(
                    file_path, offset=file_size - read_size, length=read_size
                ) as reader:
                    tail_data = reader.read()
            except Exception:
                # 回退：某些 HDFS 配置可能不支持 range read，改用下载临时文件
                logger.warning(
                    f'Range read 失败，回退到完整下载: {file_path}'
                )
                import tempfile
                with tempfile.NamedTemporaryFile(
                    suffix='.parquet', delete=False
                ) as tmp:
                    tmp_path = tmp.name
                try:
                    client.download(file_path, tmp_path)
                    import pyarrow.parquet as pq
                    pf = pq.ParquetFile(tmp_path)
                    schema = [
                        {'name': field.name, 'type': str(field.type)}
                        for field in pf.schema_arrow
                    ]
                finally:
                    _os.unlink(tmp_path)

                return jsonify({
                    'status': 0,
                    'message': '',
                    'result': {'columns': schema},
                })

            # 从尾部数据解析 footer
            import io as _io
            import pyarrow.parquet as pq

            tail_buf = _io.BytesIO(tail_data)

            # 最后 4 字节 = PAR1 magic
            tail_buf.seek(-4, _io.SEEK_END)
            if tail_buf.read(4) != b'PAR1':
                raise RuntimeError('不是有效的 Parquet 文件 (缺少 PAR1 尾部标识)')

            # 再往前 4 字节 = footer length (little-endian int32)
            tail_buf.seek(-8, _io.SEEK_END)
            footer_len_bytes = tail_buf.read(4)
            footer_len = int.from_bytes(footer_len_bytes, 'little')

            if footer_len <= 0 or footer_len > read_size - 8:
                # footer 超出读取范围，回退到完整下载
                import tempfile
                with tempfile.NamedTemporaryFile(
                    suffix='.parquet', delete=False
                ) as tmp:
                    tmp_path = tmp.name
                try:
                    client.download(file_path, tmp_path)
                    pf = pq.ParquetFile(tmp_path)
                    schema = [
                        {'name': field.name, 'type': str(field.type)}
                        for field in pf.schema_arrow
                    ]
                finally:
                    _os.unlink(tmp_path)
            else:
                # footer 在读取范围内，直接从内存解析
                footer_start = read_size - 8 - footer_len
                tail_buf.seek(footer_start)
                footer_data = tail_buf.read(footer_len + 8)

                footer_buf = _io.BytesIO(footer_data)
                pf = pq.ParquetFile(footer_buf)
                schema = [
                    {'name': field.name, 'type': str(field.type)}
                    for field in pf.schema_arrow
                ]

            return jsonify({
                'status': 0,
                'message': '',
                'result': {'columns': schema},
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                'status': 1,
                'message': f'Schema 获取失败: {str(e)}',
                'result': None,
            })


# ─── 注册 API ───────────────────────────────────────────────────

appbuilder.add_api(HDFS_Browser_View)
