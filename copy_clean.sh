#!/bin/bash
# 清理并复制 Cube Studio 代码到 /bdm/share_bdm/cube-studio-bos
# 移除: 文档、构建产物、我们的工具脚本、环境敏感文件
set -e

SRC=/bdm/share_bdm/cube-studio-master
DST=/bdm/share_bdm/cube-studio-bos

echo "============================================"
echo "  Cube Studio 代码清理复制"
echo "  源: $SRC"
echo "  目标: $DST"
echo "============================================"

# 1. 清空目标目录
rm -rf "$DST"
mkdir -p "$DST"

# 2. 复制所有内容（保留属性）
echo ">>> 1/3 复制代码..."
cp -a "$SRC"/. "$DST"/

# 3. 删除不需要的目录和文件
echo ">>> 2/3 清理构建产物和文档..."

cd "$DST"

# === 构建产物 ===
rm -rf myapp/frontend/node_modules        # React 依赖 (991MB)
rm -rf myapp/vision/node_modules          # Vision 依赖（如有）
rm -rf myapp/visionPlus/node_modules      # VisionPlus 依赖（如有）
rm -rf myapp/static/appbuilder/frontend   # 前端 build 产物
rm -rf myapp/static/appbuilder/vison      # Vision build 产物
rm -rf myapp/static/appbuilder/visonPlus  # VisionPlus build 产物
rm -rf myapp/chatgpt-web/distChat         # ChatGPT 前端 build

# demo-spark 二进制包
rm -f demo-spark/pyspark_env.tar.gz       # 531MB
rm -f demo-spark/spark-2.4.8-bin-without-hadoop.tgz  # 225MB

# === Python 缓存 ===
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete

# === 我们的分析文档 & 工具 ===
rm -rf files/                             # 所有分析 md/xlsx
rm -rf tools/                             # 压测/资源分析工具
rm -f  CLAUDE.md                          # Claude Code 配置
rm -f  build_backend.sh                   # 增量构建脚本
rm -f  build_frontend.sh                  # 增量构建脚本
rm -f  gen_xlsx_v6.py
rm -f  test-script.py
rm -f  update_excel.py
rm -f  pull_pack_clean.sh
rm -f  proxy.py

# === GitHub Wiki（文档，非代码）===
rm -rf cube-studio.wiki/

# === 环境敏感文件 ===
rm -f  ai_general.keytab
rm -f  krb5.conf

# === 运行时数据 ===
rm -rf myapp/static/file/uploads
rm -rf install/docker/data
rm -rf install/docker/file
rm -rf install/docker/kubeconfig
rm -rf install/docker/project

# === 避免复制 .git ===
rm -rf .git 2>/dev/null

# 4. 确保必要目录存在
echo ">>> 3/3 创建必要的空目录..."
mkdir -p myapp/static/file/uploads
mkdir -p install/docker/data
mkdir -p myapp/frontend/node_modules/.gitkeep 2>/dev/null
touch myapp/static/file/uploads/.gitkeep

echo ""
echo "============================================"
echo "  复制完成！"
echo "============================================"

# 大小统计
echo ""
echo "=== 原始大小 ==="
du -sh "$SRC" --exclude=node_modules --exclude=__pycache__ 2>/dev/null
echo ""
echo "=== 清理后大小 ==="
du -sh "$DST" 2>/dev/null
echo ""
echo "=== 顶层结构 ==="
ls -la "$DST"/
echo ""
echo "=== 目录数 ==="
find "$DST" -type d | wc -l
echo "=== 文件数 ==="
find "$DST" -type f | wc -l
