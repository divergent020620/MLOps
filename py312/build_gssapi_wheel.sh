#!/bin/bash
# ============================================================================
# gssapi cp312 manylinux2014 wheel 构建 v3
# 容器: quay.io/pypa/manylinux2014_x86_64(环境健康, glibc 2.17 基线)
# 步骤: yum krb5-devel -> python-build-standalone(CPython 3.12.10 manylinux2014)
#        -> pip wheel gssapi==1.9.0(产物天然 manylinux2014, 行内麒麟 2.28 可装)
# 产物: py312/wheels/gssapi-1.9.0-cp312-cp312-manylinux2014_x86_64.whl
# ============================================================================
set -euo pipefail
export MSYS2_ARG_CONV_EXCL='*'
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ROOT_W="$(cygpath -m "$ROOT")"
mkdir -p "$ROOT/py312/wheels"

echo "=== [1/3] 启动 manylinux 容器并装 krb5-devel ==="
docker rm -f gss-build 2>/dev/null || true
docker run -d --name gss-build quay.io/pypa/manylinux2014_x86_64 bash -c "sleep 10800"
docker exec gss-build bash -c "yum install -y krb5-devel >/dev/null 2>&1 && echo krb5-devel OK"

echo "=== [2/3] 下载 python-build-standalone CPython 3.12.10(manylinux2014) ==="
docker exec gss-build bash -c "
set -e
URL=\$(curl -sL https://api.github.com/repos/astral-sh/python-build-standalone/releases \
  | python3 -c '
import json,sys
rels=json.load(sys.stdin)
for r in rels:
    for a in r.get(\"assets\",[]):
        if \"cpython-3.12.10\" in a[\"name\"] and \"x86_64-unknown-linux-gnu-install_only.tar.gz\" in a[\"name\"]:
            print(a[\"browser_download_url\"]); sys.exit(0)
')"
docker exec -e URL="$URL" gss-build bash -c "
cd /opt && curl -sL \"\$URL\" | tar xzf - && /opt/python/bin/python3.12 --version && echo standalone OK"

echo "=== [3/3] pip wheel gssapi ==="
docker exec gss-build bash -c "
/opt/python/bin/pip install -q wheel setuptools cython &&
/opt/python/bin/python -m pip wheel gssapi==1.9.0 --no-deps -w /out && echo wheel-done"
docker cp gss-build:/out/. "$ROOT_W/py312/wheels/" 2>/dev/null || true
docker rm -f gss-build >/dev/null 2>&1 || true

ls -la "$ROOT_W/py312/wheels" | grep gssapi
echo "=== 完成 ==="
