"""
Cube Studio Dataset — Jupyter Server Extension

安装:
    pip install -e .
    jupyter serverextension enable --py cube_studio_dataset --sys-prefix
"""

from setuptools import setup

setup(
    name='cube_studio_dataset',
    version='1.0.0',
    description='Cube Studio Dataset Panel for JupyterLab - browse and load HDFS datasets',
    packages=['cube_studio_dataset'],
    package_dir={'cube_studio_dataset': '.'},
    include_package_data=True,
    zip_safe=False,
)
