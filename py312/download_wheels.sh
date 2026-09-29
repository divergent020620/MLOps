#!/bin/bash
# ============================================================================
# 行外 cp312 wheel 采购脚本
# 目标: 锁定 Python 3.12 + manylinux2014(glibc 2.17), 保证行内麒麟(glibc 2.28)可装
# 约束: --only-binary=:all: 零编译; 对只有 sdist 的纯 py 包(jieba/wtforms-json 等)
#       先用 pip wheel 在行外打成 wheel 放入 wheels/ 再全量下载
# 用法: bash py312/download_wheels.sh
# 产物: py312/wheels/*.whl
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Docker 挂载用正斜杠 Windows 路径; MSYS2_ARG_CONV_EXCL 关闭 git-bash 的路径转换
export MSYS2_ARG_CONV_EXCL='*'
REPO_ROOT_W="$(cygpath -m "$REPO_ROOT")"
WHEELS_DIR="$REPO_ROOT/py312/wheels"
REQS="$REPO_ROOT/install/docker/requirements.txt"
mkdir -p "$WHEELS_DIR"

echo "=== [1/2] 纯 py sdist 包行外打 wheel ==="
docker run --rm \
  -v "$REPO_ROOT_W/py312/wheels:/wheels" \
  -v "$REPO_ROOT_W/py312/sources:/sdist" \
  notebook:jupyter-ubuntu-py312 \
  bash -c '
    for pkg in wtforms-json==0.3.5 jieba==0.42.1 hdfs==2.7.3 krbcontext==0.10; do
      name="${pkg%%==*}"; ver="${pkg##*==}"
      if ! ls /wheels/*.whl 2>/dev/null | grep -qi "${name//-/_}-${ver}"; then
        echo "  -> build $pkg"
        ( cd /sdist && /opt/python/bin/pip download "$pkg" --no-deps -d . 2>/dev/null ) || true
        /opt/python/bin/pip wheel /sdist/*-"$ver".tar.gz --no-deps -w /wheels 2>/dev/null \
          || /opt/python/bin/pip wheel "$pkg" --no-deps -w /wheels || true
      fi
    done
  '

echo "=== [2/2] 全量 cp312 manylinux2014 wheel 下载 ==="
docker run --rm \
  -v "$REPO_ROOT_W/install/docker/requirements.txt:/requirements.txt" \
  -v "$REPO_ROOT_W/py312/wheels:/wheels" \
  notebook:jupyter-ubuntu-py312 \
  bash -c "
    /opt/python/bin/pip download -r /requirements.txt --dest /wheels \
      --find-links /wheels \
      --python-version 3.12 \
      --platform manylinux2014_x86_64 \
      --platform manylinux_2_17_x86_64 \
      --platform manylinux_2_28_x86_64 \
      --implementation cp --abi cp312 \
      --only-binary=:all:
  "

echo "=== 下载完成, 共 $(ls "$WHEELS_DIR"/*.whl 2>/dev/null | wc -l) 个 wheel ==="
