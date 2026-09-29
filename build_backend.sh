#!/bin/bash
# 后端构建部署脚本
# 用法: bash build_backend.sh [TAG]
# 示例: bash build_backend.sh 20260714
set -e

TAG="${1:-$(date +%Y%m%d)}"
REPO="192.168.11.12/cube-studio/kubeflow-dashboard"
ROOT="$(cd "$(dirname "$0")" && pwd)"

# 基础镜像（从当前 running 版本取，已包含所有依赖）
BASE_IMAGE="192.168.11.12/cube-studio/kubeflow-dashboard:20260703"

echo "=========================================="
echo "  后端构建部署"
echo "  基础镜像: $BASE_IMAGE"
echo "  新镜像:   $REPO:$TAG"
echo "=========================================="

# 生成 Dockerfile
cat > /tmp/Dockerfile.backend << DOCKERFILE
FROM $BASE_IMAGE
COPY myapp /home/myapp/myapp
RUN chmod +x /home/myapp/myapp/bin/myapp
DOCKERFILE

echo ""
echo "=== 构建镜像 ==="
cd "$ROOT"
docker build -t "$REPO:$TAG" -f /tmp/Dockerfile.backend .

echo ""
echo "=== 推送镜像 ==="
docker push "$REPO:$TAG"

echo ""
echo "=== 更新部署 ==="
kubectl set image deployment/kubeflow-dashboard -n infra \
  kubeflow-dashboard="$REPO:$TAG"

kubectl set image deployment/kubeflow-dashboard-schedule -n infra \
  kubeflow-dashboard-schedule="$REPO:$TAG"

kubectl set image deployment/kubeflow-dashboard-worker -n infra \
  kubeflow-dashboard-worker="$REPO:$TAG"

kubectl set image deployment/kubeflow-watch -n infra \
  kubeflow-watch-workflow="$REPO:$TAG"

echo ""
echo "=== 等待 rollout ==="
kubectl rollout status deployment/kubeflow-dashboard -n infra --timeout=120s
kubectl rollout status deployment/kubeflow-dashboard-schedule -n infra --timeout=120s
kubectl rollout status deployment/kubeflow-dashboard-worker -n infra --timeout=120s
kubectl rollout status deployment/kubeflow-watch -n infra --timeout=120s

echo ""
echo "=== 完成: $REPO:$TAG ==="
