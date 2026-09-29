#!/bin/bash
# 前端构建部署脚本
# 用法: bash build_frontend.sh [TAG]
# 示例: bash build_frontend.sh 20260714
set -e

TAG="${1:-$(date +%Y%m%d)}"
REPO="192.168.11.12/cube-studio/kubeflow-dashboard-frontend"
ROOT="$(cd "$(dirname "$0")" && pwd)"

# 基础镜像（仅包含 nginx，构建时只替换静态文件）
BASE_IMAGE="192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-20260730"

echo "=========================================="
echo "  前端构建部署"
echo "  基础镜像: $BASE_IMAGE"
echo "  新镜像:   $REPO:$TAG"
echo "=========================================="

echo ""
echo "=== npm build ==="
cd "$ROOT/myapp/frontend"
npm run build

echo ""
echo "=== 构建镜像 ==="
cat > /tmp/Dockerfile.frontend << DOCKERFILE
FROM $BASE_IMAGE
COPY ./myapp/static/appbuilder/frontend /data/web/frontend
RUN rm -rf /data/web/frontend/manifest.json /data/web/frontend/robots.txt
COPY ./myapp/static /data/web/static
DOCKERFILE
cd "$ROOT"
docker build -t "$REPO:$TAG" -f /tmp/Dockerfile.frontend .

echo ""
echo "=== 推送镜像 ==="
docker push "$REPO:$TAG"

echo ""
echo "=== 更新部署 ==="
kubectl set image deployment/kubeflow-dashboard-frontend -n infra \
  kubeflow-dashboard-frontend="$REPO:$TAG"
kubectl rollout status deployment/kubeflow-dashboard-frontend -n infra --timeout=120s

echo ""
echo "=== 完成: $REPO:$TAG ==="
