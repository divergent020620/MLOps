#!/bin/bash
# ============================================================================
# Cube Studio Notebook — 容器启动初始化（JupyterLab 4 / py3.12 版）
#
# 谁调用它：
#   Cube Studio 后端在创建 notebook pod 时注入 pre_command，原样如下
#   （myapp/views/view_notebook.py:499 与 :628）：
#
#     pre_command = '(nohup sh /init.sh > /notebook_init.log 2>&1 &) ;
#                     (nohup sh /mnt/<user>/init.sh > /init.log 2>&1 &) ; '
#
#   所以 /init.sh 由平台拉起；用户自己的 /mnt/<user>/init.sh 由平台另外拉起，
#   本脚本**不**重复调用它（重复跑会有副作用执行两次的问题）。
#
# ★ 本文件是两个脚本的合并版（这是必修的一个 bug）：
#
#   参照版 install/docker/notebook-hdfs-build/Dockerfile:81
#       COPY dataset_init.sh /init.sh          ← dataset_init.sh 就是 /init.sh
#
#   而 domestic-jupyter/Dockerfile.hdfs:68,80
#       COPY dataset_init.sh /init-dataset.sh  ← 放成了别的名字
#       COPY init.sh         /init.sh          ← /init.sh 是 SSH 那个
#       ⇒ /init-dataset.sh **没有任何调用方**（pre_command 只跑 /init.sh）
#       ⇒ dataset_helper.py 从没被拷进 /mnt/<user>/
#       ⇒ notebook 里 `from dataset_helper import ...` 必然 ImportError
#
#   本版把两边合并：SSH 配置 + 数据集目录/helper 落地，都写在 /init.sh 里，
#   一次执行全部完成，不再有孤儿脚本。
# ============================================================================

# 注意：故意**不**用 `set -e`。
# 这是容器启动钩子，任何一个可选项失败都不该让整个初始化中断
# （例如基座里没有 sshd 时，后面数据集相关的步骤仍然必须执行）。
set -u

echo "[Init] === Cube Studio Notebook 初始化开始 $(date) ==="

# ─── 1. SSH（保留原行为；基座没有 sshd 时只告警不中断）───────────────
if [ -f /etc/ssh/sshd_config ]; then
    [ -n "${SSH_PORT:-}" ] && echo "Port ${SSH_PORT}" >> /etc/ssh/sshd_config
    sed -i "s/#PermitRootLogin yes/PermitRootLogin yes/" /etc/ssh/sshd_config 2>/dev/null || true
    sed -i "s/#PermitRootLogin prohibit-password/PermitRootLogin yes/" /etc/ssh/sshd_config 2>/dev/null || true
    echo "root:cube-studio" | chpasswd 2>/dev/null || true

    /usr/sbin/sshd 2>/dev/null || service ssh restart 2>/dev/null || true
    echo "[Init] SSH 已配置，端口: ${SSH_PORT:-未设置}"
else
    echo "[Init] 跳过 SSH：基座无 /etc/ssh/sshd_config"
fi

# ─── 2. 数据集目录链接 + helper 落地 ─────────────────────────────────
# 来自 dataset_init.sh。DATASET_SAVEPATH 由部署侧环境变量决定，
# 默认与 Cube Studio 的约定一致。
USERNAME="${USERNAME:-default}"
NOTEBOOK_DIR="/mnt/${USERNAME}"
DATASET_HELPER="/opt/dataset_helper.py"
DATASET_SAVEPATH="${DATASET_SAVEPATH:-/mnt/${USERNAME}/datasets}"

mkdir -p "${NOTEBOOK_DIR}" 2>/dev/null || true

if [ -d "${DATASET_SAVEPATH}" ]; then
    if [ ! -L "${NOTEBOOK_DIR}/datasets" ] && [ ! -d "${NOTEBOOK_DIR}/datasets" ]; then
        ln -sf "${DATASET_SAVEPATH}" "${NOTEBOOK_DIR}/datasets" 2>/dev/null \
            && echo "[Init] 数据集目录已链接: ${NOTEBOOK_DIR}/datasets -> ${DATASET_SAVEPATH}"
    else
        echo "[Init] 数据集目录已存在，跳过链接"
    fi
else
    echo "[Init] 警告：${DATASET_SAVEPATH} 不存在（数据集可能尚未下载，或挂载未生效）"
fi

if [ -f "${DATASET_HELPER}" ]; then
    cp -f "${DATASET_HELPER}" "${NOTEBOOK_DIR}/dataset_helper.py" 2>/dev/null \
        && echo "[Init] dataset_helper.py 已复制到 ${NOTEBOOK_DIR}/"
else
    echo "[Init] 警告：${DATASET_HELPER} 不存在，notebook 里将无法 import dataset_helper"
fi

# ─── 3. 示例文件软链（保留原行为）────────────────────────────────────
if [ -d "/examples" ] && [ -n "${USERNAME:-}" ]; then
    ln -sf /examples "${NOTEBOOK_DIR}/examples" 2>/dev/null || true
    echo "[Init] 示例文件已链接到 ${NOTEBOOK_DIR}/examples"
fi

# ─── 4. 自检汇总（面板不显示时，第一个该看的就是这几行）───────────────
echo "[Init] --- 自检 ---"
if command -v jupyter >/dev/null 2>&1; then
    echo "[Init] jupyter: $(jupyter --version 2>/dev/null | grep -i 'jupyterlab' || echo '未知')"
else
    echo "[Init] 警告：PATH 里没有 jupyter"
fi
if [ -d /opt/nbenv/share/jupyter/labextensions/cube-studio-dataset/static ]; then
    echo "[Init] 数据集面板产物: $(ls /opt/nbenv/share/jupyter/labextensions/cube-studio-dataset/static/remoteEntry*.js 2>/dev/null | xargs -r basename | tr '\n' ' ')"
else
    echo "[Init] 警告：找不到数据集面板产物，侧边栏不会有「数据集」Tab"
fi

echo "[Init] === 初始化完成 $(date) ==="
