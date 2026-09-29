#!/bin/bash
set -e

HUB=10.240.125.39/cube-studio/notebook
TAG=jupyter-ubuntu-spark2-20260707
PROXY=http://172.20.10.3:7890

echo "=== Build spark-client image ==="
docker build \
  --build-arg HTTP_PROXY=${PROXY} \
  --build-arg HTTPS_PROXY=${PROXY} \
  -t ${HUB}:${TAG} \
  -f Dockerfile .
echo "Image: ${HUB}:${TAG}"
