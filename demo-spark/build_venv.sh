#!/bin/bash
set -e
cd "$(dirname "$0")"

IMG_TAG=pyspark-venv-builder
PROXY=http://172.20.10.3:7890

echo "Building venv-builder image..."
docker build --network=host \
  --build-arg HTTP_PROXY=$PROXY \
  --build-arg HTTPS_PROXY=$PROXY \
  -t $IMG_TAG -f Dockerfile.venv .

# 用绝对路径（Docker on Windows 需要）
echo "Packing..."
docker run --rm \
  -v "C:/Users/27404/Desktop/BOS/cubeStudio/cube-studio-master/demo-spark:/output" \
  $IMG_TAG bash -c 'cd /opt && tar -czf /output/pyspark_env.tar.gz pyspark_env/ && echo Done: $(ls -lh /output/pyspark_env.tar.gz)'

# 验证
echo "=== Verify ==="
tar tvzf pyspark_env.tar.gz | grep -E "bin/python$" && echo "python binary: OK"
tar tvzf pyspark_env.tar.gz | grep "libpython3.7m.so.1.0" && echo "shared lib: OK"
echo "Success!"