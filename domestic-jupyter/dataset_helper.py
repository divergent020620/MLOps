"""
Cube Studio Dataset Helper — Jupyter Notebook 数据集加载工具

在 Jupyter Notebook 中使用:
    from dataset_helper import list_datasets, load_dataset

    # 列出所有可用数据集
    datasets = list_datasets()
    for ds in datasets:
        print(ds['label'], ds['entries_num'])

    # 加载数据集
    df = load_dataset('your_dataset_name')
    print(df.head())

"""

import os
import json
import sys
from typing import List, Dict, Any, Optional

# Cube Studio API 地址 (从环境变量或 notebook 路径推断)
_cube_api_base = os.getenv('CUBE_STUDIO_API', 'http://localhost/dataset_modelview/api')


def _get_username() -> str:
    """获取当前 notebook 用户名。"""
    # notebook 工作目录通常为 /mnt/{username}
    cwd = os.getcwd()
    if '/mnt/' in cwd:
        parts = cwd.split('/mnt/')[-1].split('/')
        return parts[0] if parts else 'default'
    return os.getenv('USERNAME', os.getenv('USER', 'default'))


def list_datasets() -> list:
    """
    从 Cube Studio API 获取所有可用数据集列表。

    返回:
        [{id, name, label, describe, source_type, storage_size,
          entries_num, columns, local_path, load_code}]
    """
    import urllib.request
    import urllib.error

    url = f'{_cube_api_base}/jupyter_list'
    try:
        req = urllib.request.Request(url)
        # 传递 cookie (如果 notebook 在同一域名下)
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 0:
                return data.get('result', [])
            else:
                print(f'[DatasetHelper] API 错误: {data.get("message", "未知")}')
                return []
    except Exception as e:
        print(f'[DatasetHelper] 无法连接 Cube Studio API: {e}')
        return _list_local_datasets()


def _list_local_datasets():
    """从本地挂载路径列出数据集。"""
    username = _get_username()
    base_path = os.getenv('DATASET_SAVEPATH', f'/mnt/{username}/datasets')
    datasets = []

    if os.path.exists(base_path):
        for name in os.listdir(base_path):
            dir_path = os.path.join(base_path, name)
            if os.path.isdir(dir_path):
                data_file = os.path.join(dir_path, 'data.parquet')
                header_file = os.path.join(dir_path, 'header.json')
                if os.path.exists(data_file):
                    size = os.path.getsize(data_file)
                    columns = []
                    if os.path.exists(header_file):
                        try:
                            with open(header_file, 'r') as f:
                                columns = json.load(f)
                        except Exception:
                            pass
                    datasets.append({
                        'name': name,
                        'label': name,
                        'local_path': data_file,
                        'storage_size': _format_size(size),
                        'columns': columns,
                        'load_code': f"df = pd.read_parquet('{data_file}')",
                    })
    return datasets


def load_dataset(name: str, preview: bool = False) -> 'pd.DataFrame':
    """
    加载指定名称的数据集。

    参数:
        name: 数据集名称
        preview: True 时只读取前10行

    返回:
        pandas DataFrame
    """
    import pandas as pd

    username = _get_username()
    base_path = os.getenv('DATASET_SAVEPATH', f'/mnt/{username}/datasets')

    # 尝试多个可能的路径
    candidates = [
        os.path.join(base_path, f'{name}', 'data.parquet'),
        os.path.join(base_path, f'{name}_latest', 'data.parquet'),
        os.path.join(base_path, name, 'data.parquet'),
    ]

    data_path = None
    for path in candidates:
        if os.path.exists(path):
            data_path = path
            break

    if not data_path:
        # 尝试部分匹配
        if os.path.exists(base_path):
            for dname in os.listdir(base_path):
                if dname.startswith(name):
                    p = os.path.join(base_path, dname, 'data.parquet')
                    if os.path.exists(p):
                        data_path = p
                        break

    if not data_path:
        raise FileNotFoundError(
            f'数据集 "{name}" 未找到。可用数据集: {[d["name"] for d in list_datasets()]}'
        )

    if preview:
        print(f'[DatasetHelper] 预览模式: 只加载前10行')

    nrows = 10 if preview else None
    return pd.read_parquet(data_path, nrows=nrows)


def get_load_code(name: str) -> str:
    """
    返回加载数据集的 Python 代码片段。
    """
    datasets = list_datasets()
    for ds in datasets:
        if ds['name'] == name or ds['name'].startswith(name):
            return ds.get('load_code', f"""
import pandas as pd
df = pd.read_parquet('{ds["local_path"]}')
print(df.info())
print(df.head())
""")
    return f"# 数据集 '{name}' 未找到\n# 使用 list_datasets() 查看可用数据集"


def _format_size(size: int) -> str:
    """格式化文件大小。"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


# ─── 自动执行: 打印可用数据集 ──────────────────────────────────

if __name__ == '__main__':
    print('=' * 60)
    print('  Cube Studio Dataset Helper')
    print('=' * 60)
    datasets = list_datasets()
    if datasets:
        print(f'\n可用的数据集 ({len(datasets)} 个):\n')
        for ds in datasets:
            print(f'  📊 {ds["label"] or ds["name"]}')
            print(f'     ID: {ds["id"]}')
            print(f'     类型: {ds.get("source_type", "-")}')
            print(f'     大小: {ds.get("storage_size", "-")}')
            print(f'     列数: {len(ds.get("columns", []))}')
            if ds.get('describe'):
                print(f'     描述: {ds["describe"]}')
            print()
    else:
        print('\n  暂无可用的数据集')
        print(f'  请先在 Cube Studio 中下载 HDFS 数据集\n')
