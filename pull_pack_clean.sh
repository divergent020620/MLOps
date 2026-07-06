#!/bin/bash

# 镜像列表
images=(
"ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01"
"ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.03.01"

"ccr.ccs.tencentyun.com/cube-studio/notebook:vscode-ubuntu-cpu-base"
"ccr.ccs.tencentyun.com/cube-studio/notebook:vscode-ubuntu-gpu-base"
"ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu22.04"
"ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu22.04-cuda11.8.0-cudnn8"
"ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-cpu-1.0.0"
"ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-bigdata"
"ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-machinelearning"
"ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu-deeplearning"

"ccr.ccs.tencentyun.com/cube-studio/nni:20240501"

"docker.io/library/phpmyadmin:5.2.1"

"ccr.ccs.tencentyun.com/cube-studio/tfserving:2.3.4"
"ccr.ccs.tencentyun.com/cube-studio/tritonserver:22.07-py3"
"ccr.ccs.tencentyun.com/cube-studio/torchserve:0.7.1-cpu"
)

# 输出目录
OUTPUT_DIR="./images_export"
mkdir -p "$OUTPUT_DIR"

# 计数器
total=${#images[@]}
current=0

echo "=========================================="
echo "开始处理 $total 个镜像"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="

for img in "${images[@]}"
do
    current=$((current + 1))
    echo ""
    echo "[$current/$total] 处理镜像: $img"
    echo "------------------------------------------"

    # 生成文件名
    filename=$(echo "$img" | sed 's/[\/:]/_/g').tar
    filepath="$OUTPUT_DIR/$filename"

    # 检查文件是否已存在
    if [ -f "$filepath" ]; then
        echo "⊙ 文件已存在，跳过: $filename"
        size=$(du -h "$filepath" | cut -f1)
        echo "  文件大小: $size"
        echo "------------------------------------------"
        continue
    fi

    # 1. 拉取镜像
    echo "步骤 1/3: 拉取镜像..."
    if sudo ctr -n k8s.io images pull "$img"; then
        echo "✓ 拉取成功"
    else
        echo "✗ 拉取失败，跳过此镜像"
        continue
    fi

    # 2. 导出镜像
    echo "步骤 2/3: 导出镜像到 $filename ..."
    if sudo ctr -n k8s.io images export "$filepath" "$img"; then
        echo "✓ 导出成功"
        # 显示文件大小
        size=$(du -h "$filepath" | cut -f1)
        echo "  文件大小: $size"
    else
        echo "✗ 导出失败"
        # 导出失败也继续删除镜像
    fi

    # 3. 删除镜像释放空间
    echo "步骤 3/3: 删除镜像释放空间..."
    if sudo ctr -n k8s.io images rm "$img"; then
        echo "✓ 删除成功"
    else
        echo "✗ 删除失败（可能已被删除）"
    fi

    echo "------------------------------------------"
done

echo ""
echo "=========================================="
echo "所有镜像处理完成！"
echo "导出文件位置: $OUTPUT_DIR"
echo "文件列表:"
ls -lh "$OUTPUT_DIR"
echo "=========================================="
