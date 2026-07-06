#!/bin/bash
# Cube Studio Dataset Init - 在 Jupyter Notebook 启动时执行
# 将 dataset_helper.py 复制到当前用户的工作目录

USERNAME=${USERNAME:-default}
NOTEBOOK_DIR="/mnt/${USERNAME}"
DATASET_HELPER="/opt/dataset_helper.py"
DATASET_SAVEPATH="${DATASET_SAVEPATH:-/mnt/${USERNAME}/datasets}"

# 确保 dataset 目录可访问
if [ -d "${DATASET_SAVEPATH}" ]; then
    # 创建软链接（如果还没存在）
    if [ ! -L "${NOTEBOOK_DIR}/datasets" ] && [ ! -d "${NOTEBOOK_DIR}/datasets" ]; then
        ln -sf "${DATASET_SAVEPATH}" "${NOTEBOOK_DIR}/datasets"
        echo "[DatasetInit] 数据集目录已链接: ${NOTEBOOK_DIR}/datasets -> ${DATASET_SAVEPATH}"
    fi
fi

# 复制 helper 脚本到 notebook 工作目录
if [ -f "${DATASET_HELPER}" ]; then
    cp -f "${DATASET_HELPER}" "${NOTEBOOK_DIR}/dataset_helper.py"
    echo "[DatasetInit] dataset_helper.py 已复制到 ${NOTEBOOK_DIR}/"
fi

echo "[DatasetInit] 初始化完成"
