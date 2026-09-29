#!/bin/bash
# Cube Studio 迭代构建脚本
# 用法: bash install/docker/update/build.sh <新版本号>
# 示例: bash install/docker/update/build.sh 20260729
#
# 会自动:
#   1. 构建前端产物
#   2. 构建 & 推送前端镜像
#   3. 构建 & 推送后端镜像
#   4. 打印 rollout 命令

set -e

if [ -z "$1" ]; then
    echo "用法: bash $0 <新版本号>"
    echo "示例: bash $0 20260729"
    exit 1
fi

VERSION=$1
REGISTRY="192.168.11.12/cube-studio"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

cd "$PROJECT_ROOT"

echo "============================================"
echo "  Cube Studio 构建 — 版本: $VERSION"
echo "============================================"

# --------------------------------------------------
# 1. 前端产物
# --------------------------------------------------
echo ""
echo "[1/4] 构建前端产物..."
cd myapp/frontend
npm run build
cd "$PROJECT_ROOT"

# 复制前端产物到 Docker 构建所需的路径
echo "[1/4] 复制前端产物到 static/appbuilder/frontend..."
if [ -d myapp/frontend/build ] && [ "$(ls -A myapp/frontend/build 2>/dev/null)" ]; then
    # 标准 CRA 输出在 build/，追加复制到目标目录
    rm -rf myapp/static/appbuilder/frontend/*
    cp -r myapp/frontend/build/* myapp/static/appbuilder/frontend/
    echo "[1/4] 已从 build/ 复制"
elif [ -d myapp/static/appbuilder/frontend ] && [ "$(ls -A myapp/static/appbuilder/frontend 2>/dev/null)" ]; then
    # build 产物已直接输出到目标目录，无需复制
    echo "[1/4] 产物已在目标目录，跳过复制"
else
    echo "[1/4] 错误: 未找到前端构建产物！请先运行: cd myapp/frontend && npm run build"
    exit 1
fi

# --------------------------------------------------
# 2. 构建前端镜像
# --------------------------------------------------
echo ""
echo "[2/4] 构建前端镜像..."
docker build --network=host \
    -t $REGISTRY/kubeflow-dashboard-frontend:$VERSION \
    -f install/docker/update/Dockerfile.frontend .

# --------------------------------------------------
# 3. 构建后端镜像
# --------------------------------------------------
echo ""
echo "[3/4] 构建后端镜像..."
docker build --network=host \
    -t $REGISTRY/kubeflow-dashboard:$VERSION \
    -f install/docker/update/Dockerfile.backend .

# --------------------------------------------------
# 4. 推送镜像
# --------------------------------------------------
echo ""
echo "[4/4] 推送镜像..."
docker push $REGISTRY/kubeflow-dashboard-frontend:$VERSION
docker push $REGISTRY/kubeflow-dashboard:$VERSION

echo ""
echo "============================================"
echo "  构建完成！执行以下命令 rollout:"
echo "============================================"
echo ""
echo "  kubectl set image deploy/kubeflow-dashboard-frontend \\"
echo "    kubeflow-dashboard-frontend=$REGISTRY/kubeflow-dashboard-frontend:$VERSION -n infra"
echo ""
echo "  kubectl set image deploy/kubeflow-dashboard \\"
echo "    kubeflow-dashboard=$REGISTRY/kubeflow-dashboard:$VERSION -n infra"
echo ""
echo "  kubectl set image deploy/kubeflow-dashboard-worker \\"
echo "    kubeflow-dashboard-worker=$REGISTRY/kubeflow-dashboard:$VERSION -n infra"
echo ""
echo "  kubectl set image deploy/kubeflow-dashboard-schedule \\"
echo "    kubeflow-dashboard-schedule=$REGISTRY/kubeflow-dashboard:$VERSION -n infra"
echo ""
echo "  kubectl set image deploy/kubeflow-watch \\"
echo "    kubeflow-watch-workflow=$REGISTRY/kubeflow-dashboard:$VERSION -n infra"
echo ""
echo "============================================"
