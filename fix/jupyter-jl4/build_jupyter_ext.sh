#!/bin/bash
# ============================================================================
# Cube Studio — 行外一键构建 JupyterLab 4 数据集扩展
#
# 产出 M3 缺失的材料：
#   out/cube_studio_dataset-<ver>-py3-none-any.whl  ← M3 材料 2（JL4 适配版，自带前端产物）
#   out/labextension-dist/                          ← M3 材料 3（JL4 预构建前端包）
#   out/jupyter-requirements.txt                    ← M3 材料 1
#   out/dataset_helper.py 等                        ← 纯 Python 数据集落地件
#   末了整体打包：fix/jupyter-jl4-pack.tgz
#
# 用法:
#   bash fix/jupyter-jl4/build_jupyter_ext.sh
#   bash fix/jupyter-jl4/build_jupyter_ext.sh --fresh    # 清 node_modules/venv 重来
#   bash fix/jupyter-jl4/build_jupyter_ext.sh --no-venv  # 复用已装好 jupyterlab 的 venv
#
# 前置: 宿主机有 node >= 18 与 npm（已实测 node v24 + npm 11 可用）。
#       不需要 docker —— 全程在宿主机 node 上做。
#
# ── 三个已实测踩过的坑（本脚本都已处理）────────────────────────────────
#  1) `jupyter labextension build` 在 JL 4.6 已废弃且会崩 →
#     改用 `jupyter-builder build`（jupyterlab 4.6 自带 jupyter_builder）
#  2) Windows 中文 locale 下 jupyter-builder 读 package.json 会撞 GBK codec →
#     全程强制 PYTHONUTF8=1
#  3) Windows 上 builder 生成的 jupyterlab._build.load 是反斜杠路径 →
#     必须过 fix_build_paths.py 规范化，否则麒麟上 404 白屏
# ============================================================================
set -euo pipefail

FRESH=0
MAKE_VENV=1
for arg in "$@"; do
  case "$arg" in
    --fresh)   FRESH=1 ;;
    --no-venv) MAKE_VENV=0 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
LABEXT="$HERE/labextension"
PKG="$HERE/cube_studio_dataset"
BUILT="$PKG/labextension"
VENV="$HERE/.venv"
OUT="$HERE/out"
PKG_TGZ="$ROOT/fix/jupyter-jl4-pack.tgz"
JL_REQ='jupyterlab>=4.2,<5'

echo "=========================================="
echo "  JupyterLab 4 数据集扩展 — 行外构建"
echo "  workspace: $HERE"
echo "  产物:      $PKG_TGZ"
echo "=========================================="

# ── 0. 工具自检 ────────────────────────────────────────────────────────────
echo ""
echo "=== [0/7] 工具自检 ==="
command -v node >/dev/null 2>&1 || { echo "!! 缺 node（需 >= 18）"; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "!! 缺 npm"; exit 1; }
echo "node: $(node -v)   npm: $(npm -v)"

# ── venv（提供 jupyterlab 与 jupyter-builder 的 CLI）─────────────────────────
if [ ! -x "$VENV/Scripts/python.exe" ] && [ ! -x "$VENV/bin/python" ]; then
  echo "--- 创建 venv 并安装 jupyterlab（首次约 1-2 分钟）---"
  python -m venv "$VENV"
  if [ -x "$VENV/Scripts/python.exe" ]; then PY="$VENV/Scripts/python.exe"; else PY="$VENV/bin/python"; fi
  PYTHONUTF8=1 "$PY" -m pip install --quiet --upgrade pip setuptools wheel build
  PYTHONUTF8=1 "$PY" -m pip install --quiet "$JL_REQ"
else
  if [ -x "$VENV/Scripts/python.exe" ]; then PY="$VENV/Scripts/python.exe"; else PY="$VENV/bin/python"; fi
fi
if [ -x "$VENV/Scripts" ]; then JBIN="$VENV/Scripts"; else JBIN="$VENV/bin"; fi

command -v node >/dev/null
JL_VER="$(PYTHONUTF8=1 "$PY" -c 'import jupyterlab;print(jupyterlab.__version__)')"
echo "jupyterlab: $JL_VER"
"$JBIN/jupyter-builder" --help >/dev/null 2>&1 || "$JBIN/jupyter-builder.exe" --help >/dev/null 2>&1 \
  || { echo "!! venv 里没有 jupyter-builder，请确认 jupyterlab>=4"; exit 1; }

# jupyter-builder 的可执行文件（Windows 带 .exe）
BUILDER=""
for c in "$JBIN/jupyter-builder" "$JBIN/jupyter-builder.exe"; do
  [ -x "$c" ] && { BUILDER="$c"; break; }
done
[ -n "$BUILDER" ] || { echo "!! 找不到 jupyter-builder"; exit 1; }

# jupyterlab core 包位置（builder 需要，Windows/POSIX 路径统一成正斜杠给 python）
CORE_DIR="$(PYTHONUTF8=1 "$PY" -c '
import pathlib, jupyterlab
p = pathlib.Path(jupyterlab.__file__).parent / "staging"
print(p.as_posix())
')"
echo "core: $CORE_DIR"

# ── 清理 ───────────────────────────────────────────────────────────────────
if [ "$FRESH" = "1" ]; then
  echo "--- --fresh：清理 node_modules / lib / 构建产物 ---"
  rm -rf "$LABEXT/node_modules" "$LABEXT/lib" "$LABEXT/tsconfig.tsbuildinfo" "$BUILT" "$OUT" "$HERE/dist" "$HERE/build"
fi

# ── 1. 前端依赖 ────────────────────────────────────────────────────────────
echo ""
echo "=== [1/7] npm install（JL4 依赖树，首次约 1 分钟） ==="
cd "$LABEXT"
npm install --no-audit --no-fund

# ── 2. TypeScript 编译（先类型检查，早失败）───────────────────────────────
echo ""
echo "=== [2/7] tsc 编译 + 类型检查 ==="
npx tsc
[ -f "$LABEXT/lib/index.js" ] || { echo "!! tsc 未产出 lib/index.js"; exit 1; }
echo "lib/index.js OK"

# ── 3. 打出 JupyterLab 4 预构建产物 ────────────────────────────────────────
echo ""
echo "=== [3/7] jupyter-builder build（生成 static/remoteEntry） ==="
cd "$LABEXT"
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
  "$BUILDER" build . --core-path "$CORE_DIR"

[ -d "$BUILT/static" ] || { echo "!! 未生成 $BUILT/static"; exit 1; }
ls "$BUILT/static"/remoteEntry*.js >/dev/null 2>&1 \
  || { echo "!! 缺 remoteEntry*.js —— 检查 package.json 的 jupyterlab.outputDir"; exit 1; }
echo "--- 预构建产物 ---"
ls -lh "$BUILT/static"

# ── 4. ★ 规范化 Windows 反斜杠路径 ─────────────────────────────────────────
echo ""
echo "=== [4/7] 规范化构建产物路径（Windows → POSIX） ==="
cd "$HERE"
PYTHONUTF8=1 "$PY" fix_build_paths.py "$BUILT"

# 复验：_build.load 必须不含反斜杠
if grep -q '\\\\' "$BUILT/package.json"; then
  echo "!! package.json 里仍有反斜杠路径，麒麟上会 404"; exit 1
fi
echo "OK: 路径已规范"

# ── 5. 打包 wheel ──────────────────────────────────────────────────────────
echo ""
echo "=== [5/7] 构建 wheel ==="
cd "$HERE"
rm -rf dist build ./*.egg-info 2>/dev/null || true
PYTHONUTF8=1 "$PY" -m build --wheel --no-isolation 2>&1 | tail -3

WHEEL="$(ls -t "$HERE"/dist/*.whl 2>/dev/null | head -1)"
[ -n "$WHEEL" ] || { echo "!! wheel 未产出"; exit 1; }
echo "wheel: $(basename "$WHEEL")"

echo "--- wheel 内容核验（两处都必须有）---"
# 注意：路径必须作为**独立参数**传进去，不能嵌进 -c 的代码字符串——
# git bash(MSYS) 只对独立参数做 POSIX→Windows 路径转换，嵌在字符串里会原样传给
# 原生 Windows Python，导致 FileNotFoundError。这里用相对路径最稳。
PYTHONUTF8=1 "$PY" - "dist/$(basename "$WHEEL")" <<'PYEOF'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
# ① JupyterLab 4 运行时真正读的位置（jupyterlab_server/config.py:40）
runtime = [n for n in names if 'share/jupyter/labextensions/' in n and 'remoteEntry' in n]
# ② 包内副本（供 status() 自检 / JL3 兼容）
inpkg = [n for n in names if n.startswith('cube_studio_dataset/labextension/') and 'remoteEntry' in n]
print('  总条目     :', len(names))
print('  JL4 运行时 :', runtime)
print('  包内副本   :', inpkg)
ok = True
if not runtime:
    print('!! 缺 share/jupyter/labextensions/*/static/remoteEntry*.js —— JL4 不会加载'); ok = False
if not inpkg:
    print('!! 缺包内 labextension/static/remoteEntry*.js —— status() 自检会失败'); ok = False
print('OK: wheel 自带前端产物（两处齐全）' if ok else '!! wheel 不完整')
sys.exit(0 if ok else 1)
PYEOF

# ── 6. 汇总产物 ────────────────────────────────────────────────────────────
echo ""
echo "=== [6/7] 汇总到 out/ ==="
rm -rf "$OUT"; mkdir -p "$OUT/labextension-dist" "$OUT/jupyter-p312-build"

cp "$WHEEL" "$OUT/"
cp "$HERE/jupyter-requirements.txt" "$OUT/"

# 原始 labextension-dist：给「不走 pip、直接挂路径」的备选装配方式
cp -r "$BUILT/static"     "$OUT/labextension-dist/static"
cp "$BUILT/package.json"  "$OUT/labextension-dist/package.json"
[ -f "$BUILT/install.json" ] && cp "$BUILT/install.json" "$OUT/labextension-dist/"
[ -d "$BUILT/schemas" ]  && cp -r "$BUILT/schemas" "$OUT/labextension-dist/"

# 纯 Python 的数据集落地件（与 JL 版本无关，务必一起发）
for f in dataset_helper.py sitecustomize.py; do
  [ -f "$ROOT/fix/交接/jupyter/$f" ] && cp "$ROOT/fix/交接/jupyter/$f" "$OUT/"
done

# ★ Dockerfile + 现成的 build context —— 同事不用自己拼目录，进去就能 docker build
cp "$HERE/Dockerfile.notebook-p312" "$OUT/jupyter-p312-build/"
cp "$WHEEL"                          "$OUT/jupyter-p312-build/"
cp "$HERE/jupyter-requirements.txt"  "$OUT/jupyter-p312-build/"
cp "$HERE/init.sh"                   "$OUT/jupyter-p312-build/"
[ -f "$ROOT/fix/交接/jupyter/dataset_helper.py" ] && \
  cp "$ROOT/fix/交接/jupyter/dataset_helper.py" "$OUT/jupyter-p312-build/"
chmod +x "$OUT/jupyter-p312-build/init.sh"

cd "$OUT"
sha256sum ./* 2>/dev/null > SHA256SUMS.txt || true
ls -lh
echo "--- jupyter-p312-build/ （可直接 docker build 的 context）---"
ls -lh "$OUT/jupyter-p312-build/"

# ── 7. 总打包 ──────────────────────────────────────────────────────────────
echo ""
echo "=== [7/7] 打包 $PKG_TGZ ==="
cd "$HERE"
tar czf "$PKG_TGZ" \
  -C "$HERE" out README-给装配同事.md README.md \
             Dockerfile.notebook-p312 init.sh \
             jupyter-requirements.txt build_jupyter_ext.sh fix_build_paths.py
ls -lh "$PKG_TGZ"

echo ""
echo "=========================================="
echo "  完成"
echo "=========================================="
echo "交付物: $PKG_TGZ"
echo ""
echo "  README-给装配同事.md            ← ★ 同事先看这个"
echo "  out/jupyter-p312-build/         ← ★ 现成 build context，进去就能 docker build"
echo "      Dockerfile.notebook-p312"
echo "      cube_studio_dataset-*.whl"
echo "      jupyter-requirements.txt"
echo "      dataset_helper.py"
echo "      init.sh"
echo "  out/cube_studio_dataset-*.whl   ← M3 材料 2（JL4 适配版，自带前端产物）"
echo "  out/labextension-dist/          ← M3 材料 3（JL4 预构建前端包）"
echo "  out/jupyter-requirements.txt    ← M3 材料 1"
echo "  README.md                       ← 完整技术说明（含排查表）"
