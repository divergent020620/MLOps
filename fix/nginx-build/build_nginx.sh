#!/bin/bash
# ============================================================================
# Cube Studio — 行外一键编译 nginx 并打包
#
# 用法:
#   bash fix/nginx-build/build_nginx.sh [NGINX_VERSION] [NGINX_SHA256]
# 示例:
#   bash fix/nginx-build/build_nginx.sh 1.28.0
#   bash fix/nginx-build/build_nginx.sh 1.28.0 <nginx.org 公布的 sha256>
#
# 产物:
#   fix/nginx-build/out/       nginx 二进制 + 配置 + mime.types
#   fix/fe-nginx-kylin.tgz     行内装配用压缩包（对标 fe-caddy-kylin.tgz）
#
# 前置: 本机有 docker（Docker Desktop 即可）。编译在容器里做，Windows 只负责打包。
#
# 注：全程使用相对路径 + cd，避免 git bash 的 MSYS 路径转换在 docker CLI 上出错。
# ============================================================================
set -euo pipefail

NGINX_VERSION="${1:-1.28.0}"
NGINX_SHA256="${2:-}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="$HERE/out"
IMAGE="cube-nginx-builder:local"
VERIFY_CT="cube-nginx-verify"
PKG="$ROOT/fix/fe-nginx-kylin.tgz"

echo "=========================================="
echo "  nginx 源码编译（行外）"
echo "  版本:     $NGINX_VERSION"
echo "  构建基底: rockylinux:8 (glibc 2.28，匹配麒麟 V10 SP3)"
echo "  产物:     $PKG"
echo "=========================================="

command -v docker >/dev/null 2>&1 || { echo "!! 找不到 docker"; exit 1; }

cleanup() {
  docker rm -f "$VERIFY_CT" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ── 1. 编译 ────────────────────────────────────────────────────────────────
echo ""
echo "=== [1/5] 编译 nginx ==="
BUILD_ARGS=(--build-arg "NGINX_VERSION=$NGINX_VERSION")
if [ -n "$NGINX_SHA256" ]; then
  BUILD_ARGS+=(--build-arg "NGINX_SHA256=$NGINX_SHA256")
fi

cd "$ROOT"
docker build \
  "${BUILD_ARGS[@]}" \
  -t "$IMAGE" \
  -f fix/nginx-build/Dockerfile.nginx-build \
  .

# ── 2. 抽取产物 ────────────────────────────────────────────────────────────
echo ""
echo "=== [2/5] 抽取二进制与 mime.types ==="
rm -rf "$OUT"
mkdir -p "$OUT"
cd "$OUT"

CID="$(docker create "$IMAGE")"
docker cp "$CID:/usr/local/nginx/sbin/nginx" ./nginx
docker cp "$CID:/etc/nginx/mime.types"       ./mime.types
docker rm -f "$CID" >/dev/null 2>&1 || true

# 配置沿用仓库现有版本，一行不改 —— 本方案相对 Caddy 的最大优势
cp "$ROOT/install/docker/dockerFrontend/nginx.conf"    ./nginx.conf
cp "$ROOT/install/docker/dockerFrontend/nginx.80.conf" ./nginx.80.conf
cp "$ROOT/install/docker/dockerFrontend/start.sh"      ./start.sh

chmod +x ./nginx ./start.sh
ls -l

# ── 3. 产物核验（在 Linux 容器里跑）────────────────────────────────────────
echo ""
echo "=== [3/5] 核验产物 ==="
docker rm -f "$VERIFY_CT" >/dev/null 2>&1 || true
docker run -d --name "$VERIFY_CT" "$IMAGE" sleep 300 >/dev/null

# 用 docker cp + 相对路径把配置送进去，绕开 Windows 路径转换
cd "$OUT"
docker cp ./nginx        "$VERIFY_CT:/usr/local/nginx/sbin/nginx"
docker cp ./mime.types   "$VERIFY_CT:/etc/nginx/mime.types"
docker cp ./nginx.conf   "$VERIFY_CT:/etc/nginx/nginx.conf"
docker cp ./nginx.80.conf "$VERIFY_CT:/etc/nginx/conf.d/default.conf"

docker exec "$VERIFY_CT" bash -c '
set -e
echo "── 动态依赖（应无 perl/gd/libtiff/libXpm）──"
ldd /usr/local/nginx/sbin/nginx

echo "── 被禁组件检查 ──"
if ldd /usr/local/nginx/sbin/nginx | grep -iE "perl|libgd|libtiff|libXpm|libxslt"; then
  echo "!!! 产物链接了被禁组件，终止"; exit 1
fi
echo "OK：无被禁组件"

echo "── 最高 glibc 符号版本（必须 <= 2.28）──"
objdump -T /usr/local/nginx/sbin/nginx | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -3

echo "── nginx 版本 ──"
/usr/local/nginx/sbin/nginx -v

echo "── 配置语法校验 ──"
groupadd -r nginx 2>/dev/null || true
useradd -r -g nginx -s /sbin/nologin nginx 2>/dev/null || true
mkdir -p /data/log/nginx /var/log/nginx /data/web/frontend
/usr/local/nginx/sbin/nginx -t
'

docker rm -f "$VERIFY_CT" >/dev/null 2>&1 || true

# ── 4. 打包 ────────────────────────────────────────────────────────────────
echo ""
echo "=== [4/5] 打包 ==="
cd "$OUT"
sha256sum nginx mime.types nginx.conf nginx.80.conf start.sh > SHA256SUMS.txt
cat SHA256SUMS.txt
tar czf "$PKG" nginx mime.types nginx.conf nginx.80.conf start.sh SHA256SUMS.txt
ls -lh "$PKG"

# ── 5. 收尾 ────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  完成"
echo "=========================================="
echo "产物: $PKG"
echo ""
echo "下一步（行内装配）见 fix/nginx-build/README.md"
