"""
HDFS 数据集下载 Celery 异步任务。

提供:
  - download_hdfs_dataset: 从 HDFS 下载 parquet 文件 → 生成 data.parquet / header.json / preview.json
  - 支持并发下载、断点续传、进度追踪、错误重试
  - 流式合并 parquet (避免全量 OOM)
"""

import os
import json
import logging
import traceback
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from myapp.tasks.celery_app import celery_app
from myapp.utils.celery import session_scope
from myapp.utils.hdfs_client import HDFSClient, HDFSConfig

logger = logging.getLogger(__name__)

# 并发下载线程数
MAX_DOWNLOAD_WORKERS = int(os.environ.get('HDFS_DOWNLOAD_WORKERS', '5'))


@celery_app.task(name='task.download_hdfs_dataset', bind=True, max_retries=2,
                 soft_time_limit=7200, time_limit=7500)
def download_hdfs_dataset(task, dataset_id, hdfs_config=None, hosts_entries=None):
    """
    从 HDFS 下载 parquet 数据集。

    流程:
      1. 读取 Dataset 记录
      2. 初始化 HDFSClient (Kerberos)
      3. 根据 expand.hdfs 配置下载文件到本地
      4. 合并 parquet → 生成 header.json + preview.json
      5. 更新 Dataset 元数据

    断点续传: 检查本地已有文件，跳过已下载的。
    错误处理: Kerberos 过期 / 网络中断 → 自动重试或标记 failed。
    """
    logging.info(f'============= begin download_hdfs_dataset task, dataset_id={dataset_id}')

    # 写入后端传入的 hosts 条目，确保 worker 能解析 HDFS 节点
    if hosts_entries:
        try:
            with open('/etc/hosts', 'r') as hf:
                existing = hf.read()
            with open('/etc/hosts', 'a') as hf:
                for entry in hosts_entries:
                    if entry not in existing:
                        hf.write(entry + '\n')
                        logging.info(f'写入 hosts: {entry}')
        except Exception as e:
            logging.warning(f'写入 hosts 失败 (继续执行): {e}')

    # 延迟导入避免循环依赖
    from myapp.models.model_dataset import Dataset
    from myapp import app

    conf = app.config

    # ── 1. 获取 Dataset 记录 ──────────────────────────────────
    with session_scope(nullpool=True) as dbsession:
        dataset = dbsession.query(Dataset).filter_by(id=dataset_id).first()
        if not dataset:
            logging.error(f'Dataset id={dataset_id} 不存在')
            return {'status': 'failed', 'error': 'Dataset 不存在'}

        # 更新下载状态
        expand = json.loads(dataset.expand) if dataset.expand else {}
        hdfs_meta = expand.get('hdfs', {})
        hdfs_meta['download_status'] = 'downloading'
        hdfs_meta['download_progress'] = 0
        hdfs_meta['celery_task_id'] = task.request.id
        hdfs_meta['error_message'] = None
        expand['hdfs'] = hdfs_meta
        dataset.expand = json.dumps(expand)
        dbsession.commit()

        hdfs_meta = expand['hdfs']

        # HDFS 配置：优先使用任务参数（跨 pod 共享），回退到本地文件
        if hdfs_config:
            persisted_config = hdfs_config
        else:
            hdfs_config_file = os.path.join(conf.get('DATA_DIR', '/home/myapp'), 'hdfs_config.json')
            persisted_config = {}
            if os.path.exists(hdfs_config_file):
                try:
                    with open(hdfs_config_file, 'r', encoding='utf-8') as f:
                        persisted_config = json.load(f)
                except Exception:
                    pass

        # datasavepath: 持久化配置优先，否则用 config.py 默认值
        datasetsavepath = persisted_config.get('datasavepath') or conf.get(
            'DATASET_SAVEPATH', os.path.join('/data/k8s/kubeflow', 'datasets'))

        _dataset_name = dataset.name or f'dataset_{dataset_id}'
        _dataset_version = dataset.version or 'latest'

    # ── 2. 初始化 HDFSClient ──────────────────────────────────
    try:
        # 合并 config.py 默认值 + 持久化配置
        hdfs_conf = conf.get('HDFS_CONFIG', {}).copy()
        hdfs_conf.update({k: v for k, v in persisted_config.items() if k in ('url', 'keytab_path', 'principal', 'base_path')})
        hdfs_config = HDFSConfig(hdfs_conf)
        client = HDFSClient(hdfs_config)
    except Exception as e:
        _update_status(dataset_id, 'failed', error=f'HDFS 连接失败: {str(e)}')
        raise

    # ── 3. 收集文件列表 ─────────────────────────────────────
    try:
        full_hdfs_path = hdfs_meta.get('full_path', '')
        partition_col = hdfs_meta.get('partition_col', 'dt')
        partition_values = hdfs_meta.get('partition_values', [])

        # 本地存储目录
        dataset_name = _dataset_name
        dataset_version = _dataset_version
        local_dir = os.path.join(datasetsavepath, f'{dataset_name}_{dataset_version}')
        os.makedirs(local_dir, exist_ok=True)

        # 收集所有要下载的文件
        all_files = []
        for pv in partition_values:
            part_dir = f'{partition_col}={pv}'
            search_path = os.path.join(full_hdfs_path, part_dir) if full_hdfs_path else ''
            if not search_path or search_path == '/':
                search_path = full_hdfs_path

            try:
                pv_files = client.list_parquet_files(
                    path=search_path,
                    partition_col=partition_col,
                    date_start=pv,
                    date_end=pv,
                )
                all_files.extend(pv_files)
            except Exception as e:
                logging.warning(f'列出分区 {pv} 文件失败: {e}')
                continue

        if not all_files:
            _update_status(dataset_id, 'failed', error='未找到任何匹配的 parquet 文件')
            client.close()
            return {'status': 'failed', 'error': '未找到匹配的文件'}

        total_files = len(all_files)
        failed_files = []  # 记录下载失败的文件

        # ── 4. 并发下载文件 ─────────────────────────────────
        def _download_one(file_info):
            """单个文件下载任务 (线程安全，各自创建 HDFSClient)。"""
            remote_path = file_info['path']
            file_name = remote_path.split('/')[-1]
            local_file = os.path.join(local_dir, 'raw', file_name)
            os.makedirs(os.path.dirname(local_file), exist_ok=True)

            # 检查是否已完成
            partial_marker = local_file + '.partial'
            if os.path.exists(local_file) and not os.path.exists(partial_marker):
                try:
                    remote_size = client.client.status(remote_path).get('length', 0)
                    if os.path.getsize(local_file) == remote_size and remote_size > 0:
                        return {'file': file_name, 'status': 'skipped'}
                except Exception:
                    pass

            try:
                result = client.download(remote_path, local_file, resume=True)
                if result.get('skipped'):
                    return {'file': file_name, 'status': 'skipped'}
                return {'file': file_name, 'status': 'downloaded'}
            except Exception as e:
                logging.error(f'下载文件失败 {file_name}: {e}')
                return {'file': file_name, 'status': 'failed', 'error': str(e)}

        # 使用线程池并发下载
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
            futures = {
                executor.submit(_download_one, fi): fi for fi in all_files
            }
            for future in as_completed(futures):
                result = future.result()
                if result['status'] == 'failed':
                    failed_files.append(result)
                completed += 1
                progress = int(completed / total_files * 80)  # 80% 给下载阶段
                _update_progress(dataset_id, progress)
                logging.info(
                    f'下载进度 [{completed}/{total_files}]: {result["file"]} ({result["status"]})'
                )

    except Exception as e:
        logging.error(f'下载过程出错: {e}')
        _update_status(dataset_id, 'failed', error=f'下载失败: {str(e)}')
        raise
    finally:
        try:
            client.close()
        except Exception:
            pass

    # ── 4. 流式合并 + 生成 header.json / preview.json ────────
    try:
        header_path = os.path.join(local_dir, 'header.json')
        preview_path = os.path.join(local_dir, 'preview.json')
        data_path = os.path.join(local_dir, 'data.parquet')

        # 收集 raw 目录下的所有 parquet 文件 (排序保证顺序一致)
        raw_dir = os.path.join(local_dir, 'raw')
        parquet_files = sorted([
            os.path.join(raw_dir, f) for f in os.listdir(raw_dir)
            if f.endswith('.parquet') or f.endswith('.parq') or f.endswith('.pq')
        ]) if os.path.exists(raw_dir) else []

        if parquet_files:
            try:
                import pyarrow.parquet as pq
                import pyarrow as pa

                if len(parquet_files) == 1:
                    # 单个文件：直接重命名
                    shutil.move(parquet_files[0], data_path)
                    total_rows = None  # 后面从 metadata 读
                else:
                    # 逐 Row Group 读写：单个 RG 约 128MB，远低于全文件
                    first_schema = pq.read_schema(parquet_files[0])
                    writer = pq.ParquetWriter(data_path, first_schema)
                    _merge_rows = 0

                    for idx, pf_path in enumerate(parquet_files):
                        try:
                            pf = pq.ParquetFile(pf_path)
                            for rg_idx in range(pf.metadata.num_row_groups):
                                rg_table = pf.read_row_group(rg_idx)
                                writer.write_table(rg_table)
                                _merge_rows += rg_table.num_rows
                        except Exception as e:
                            logging.error(f'合并文件失败 (跳过): {pf_path} - {e}')
                            failed_files.append({
                                'file': os.path.basename(pf_path),
                                'status': 'merge_failed',
                                'error': str(e),
                            })
                        if (idx + 1) % 20 == 0:
                            logging.info(f'合并进度: {idx+1}/{len(parquet_files)}, 累计 {_merge_rows} 行')
                    writer.close()
                    total_rows = _merge_rows
                    logging.info(f'合并完成, {total_rows} 行')

                # 生成 header.json
                reader = pq.ParquetFile(data_path)
                schema = reader.schema_arrow
                header = [
                    {'name': field.name, 'type': str(field.type)}
                    for field in schema
                ]
                with open(header_path, 'w', encoding='utf-8') as f:
                    json.dump(header, f, ensure_ascii=False, indent=2)

                # 生成 preview.json — 只读第一个 row group 避免全量 OOM
                preview_rows = conf.get('DATASET_PREVIEW_ROWS', 10)
                preview_reader = pq.ParquetFile(data_path)
                first_rg = preview_reader.read_row_group(0)
                table = first_rg.slice(0, min(preview_rows, first_rg.num_rows))
                columns = table.column_names
                rows = []
                for i in range(table.num_rows):
                    row = {}
                    for col in columns:
                        val = table[col][i].as_py()
                        if isinstance(val, bytes):
                            try:
                                val = val.decode('utf-8')
                            except Exception:
                                val = str(val)
                        elif hasattr(val, 'isoformat'):
                            val = val.isoformat()
                        row[col] = val
                    rows.append(row)
                with open(preview_path, 'w', encoding='utf-8') as f:
                    json.dump(rows, f, ensure_ascii=False, indent=2)

                # 记录总行数
                if total_rows is None:
                    total_rows = reader.metadata.num_rows if reader.metadata else 0
                total_size = sum(
                    os.path.getsize(os.path.join(local_dir, fname))
                    for fname in ['data.parquet', 'header.json', 'preview.json']
                    if os.path.exists(os.path.join(local_dir, fname))
                )

            except ImportError:
                logging.warning('pyarrow 未安装，无法生成 header/preview')
                header = []
                rows = []
                total_rows = 0
                total_size = 0
        else:
            logging.warning('raw 目录下无 parquet 文件')
            header = []
            rows = []
            total_rows = 0
            total_size = 0

        # ── 5. 更新 Dataset 元数据 ─────────────────────────────
        _update_progress(dataset_id, 95)

        # 确定最终状态
        if failed_files:
            fail_count = len(failed_files)
            final_status = 'completed' if fail_count <= max(1, total_files * 0.1) else 'partial'
            error_msg = (
                f'{fail_count}/{total_files} 个文件失败: '
                + '; '.join(
                    f"{f['file']}: {f.get('error', 'unknown')}"
                    for f in failed_files[:5]
                )
            )
            if fail_count > 5:
                error_msg += f' ... 及其他 {fail_count - 5} 个'
        else:
            final_status = 'completed'
            error_msg = None

        with session_scope(nullpool=True) as dbsession:
            dataset = dbsession.query(Dataset).filter_by(id=dataset_id).first()
            if dataset:
                expand = json.loads(dataset.expand) if dataset.expand else {}
                hdfs_meta = expand.get('hdfs', {})
                hdfs_meta['download_status'] = final_status
                hdfs_meta['download_progress'] = 100
                hdfs_meta['failed_files'] = [
                    {'file': f['file'], 'error': f.get('error', '')}
                    for f in failed_files
                ]
                if error_msg:
                    hdfs_meta['error_message'] = error_msg
                hdfs_meta['file_manifest'] = [
                    {'name': f, 'size': os.path.getsize(os.path.join(local_dir, f))}
                    for f in os.listdir(local_dir)
                    if os.path.isfile(os.path.join(local_dir, f))
                ]
                hdfs_meta['downloaded_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                expand['hdfs'] = hdfs_meta
                expand['schema'] = header
                dataset.expand = json.dumps(expand)
                dataset.path = local_dir
                dataset.storage_size = str(total_size) if total_size else ''
                dataset.entries_num = str(total_rows) if total_rows else ''
                dbsession.commit()

        logging.info(
            f'============= download_hdfs_dataset {final_status}, '
            f'dataset_id={dataset_id}, failed={len(failed_files)}/{total_files}'
        )
        return {
            'status': final_status,
            'dataset_id': dataset_id,
            'failed_files': failed_files,
        }

    except Exception as e:
        logging.error(f'处理 parquet 文件失败: {e}')
        traceback.print_exc()
        _update_status(dataset_id, 'failed', error=f'处理失败: {str(e)}')
        raise


# ─── 辅助函数 ────────────────────────────────────────────────────

def _update_status(dataset_id, status, progress=None, error=None):
    """更新 Dataset expand 中的下载状态。"""
    from myapp.models.model_dataset import Dataset
    try:
        with session_scope(nullpool=True) as dbsession:
            dataset = dbsession.query(Dataset).filter_by(id=dataset_id).first()
            if dataset:
                expand = json.loads(dataset.expand) if dataset.expand else {}
                hdfs_meta = expand.get('hdfs', {})
                hdfs_meta['download_status'] = status
                if progress is not None:
                    hdfs_meta['download_progress'] = progress
                if error:
                    hdfs_meta['error_message'] = error
                expand['hdfs'] = hdfs_meta
                dataset.expand = json.dumps(expand)
                dbsession.commit()
    except Exception as e:
        logging.error(f'_update_status 失败 dataset_id={dataset_id}: {e}')


def _update_progress(dataset_id, progress):
    """更新下载进度 (0-100)。"""
    _update_status(dataset_id, 'downloading', progress=progress)
