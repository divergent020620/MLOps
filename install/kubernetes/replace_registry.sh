#!/bin/bash
# 批量替换镜像仓库地址
# 用法:
#   bash replace_registry.sh <新仓库地址>               # 替换默认的 192.168.11.12/cube-studio
#   bash replace_registry.sh <旧地址> <新地址>           # 自定义新旧地址
#   bash replace_registry.sh --dry-run <新地址>          # 预览模式，不实际修改
#
# 示例:
#   bash replace_registry.sh harbor.mycompany.com/cube-studio
#   bash replace_registry.sh 192.168.11.12/cube-studio harbor.mycompany.com/cube-studio
#   bash replace_registry.sh --dry-run harbor.mycompany.com/cube-studio

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}"

DRY_RUN=false
OLD_REGISTRY=""
NEW_REGISTRY=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            if [ -z "$OLD_REGISTRY" ] && [ $# -eq 1 ]; then
                # 只有一个参数: 只传了新地址，用默认旧地址
                NEW_REGISTRY="$1"
                OLD_REGISTRY="192.168.11.12/cube-studio"
                break
            elif [ -z "$OLD_REGISTRY" ]; then
                OLD_REGISTRY="$1"
            elif [ -z "$NEW_REGISTRY" ]; then
                NEW_REGISTRY="$2"
                break
            fi
            shift
            ;;
    esac
done

if [ -z "$OLD_REGISTRY" ] || [ -z "$NEW_REGISTRY" ]; then
    echo "用法:"
    echo "  bash $0 <新仓库地址>"
    echo "  bash $0 <旧地址> <新地址>"
    echo "  bash $0 --dry-run <新地址>"
    echo ""
    echo "示例:"
    echo "  bash $0 harbor.mycompany.com/cube-studio"
    echo "  bash $0 192.168.11.12/cube-studio harbor.mycompany.com/cube-studio"
    exit 1
fi

echo "=========================================="
echo "  镜像仓库地址替换"
echo "=========================================="
echo "  旧地址: ${OLD_REGISTRY}"
echo "  新地址: ${NEW_REGISTRY}"
if [ "$DRY_RUN" = true ]; then
    echo "  模式:   DRY-RUN (预览，不修改文件)"
fi
echo "=========================================="
echo ""

# 需要替换的文件列表
FILES=$(grep -rl "${OLD_REGISTRY}" "${TARGET_DIR}" --include='*.yaml' --include='*.yml' --include='*.sh' 2>/dev/null || true)

if [ -z "$FILES" ]; then
    echo "未找到包含 ${OLD_REGISTRY} 的文件"
    exit 0
fi

COUNT=0
for file in $FILES; do
    # 跳过脚本自身
    if [ "$(basename "$file")" = "replace_registry.sh" ]; then
        continue
    fi

    MATCHES=$(grep -c "${OLD_REGISTRY}" "$file" 2>/dev/null || true)
    rel_path="${file#${TARGET_DIR}/}"

    if [ "$DRY_RUN" = true ]; then
        echo "  [预览] ${rel_path} (${MATCHES} 处)"
        grep -n "${OLD_REGISTRY}" "$file" | while read line; do
            echo "    $line"
        done
    else
        sed -i "s|${OLD_REGISTRY}|${NEW_REGISTRY}|g" "$file"
        echo "  [已替换] ${rel_path} (${MATCHES} 处)"
    fi
    COUNT=$((COUNT + 1))
done

echo ""
echo "完成: 共处理 ${COUNT} 个文件"

# 特别提醒：kustomization.yml 的 images 字段也需要手动确认
if [ -f "${TARGET_DIR}/cube/overlays/kustomization.yml" ]; then
    echo ""
    echo "⚠️  注意: cube/overlays/kustomization.yml 中的 images 字段可能需要单独确认"
    echo "  当前内容:"
    grep -A 3 'images:' "${TARGET_DIR}/cube/overlays/kustomization.yml" | head -10
fi
