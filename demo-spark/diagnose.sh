#!/bin/bash
# 在 Executor 上运行的文件系统诊断
echo "========== HOSTNAME =========="
hostname
echo "========== CWD =========="
pwd
echo "========== CWD LS (-la) =========="
ls -la
echo "========== pyspark_env SYMLINK =========="
ls -la pyspark_env 2>&1
echo "========== pyspark_env/bin/python =========="
ls -la pyspark_env/bin/python 2>&1
echo "========== find python =========="
find . -maxdepth 3 -name python -type f 2>&1 | head -20
echo "========== find .tar.gz =========="
find . -maxdepth 2 -name '*.tar.gz' -type f 2>&1
echo "========== ENV: PYTHON =========="
env | grep -i python
echo "========== DONE =========="