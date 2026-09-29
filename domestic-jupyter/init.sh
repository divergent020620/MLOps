#!/bin/bash
# ============================================================================
# Cube Studio Notebook — 通用初始化脚本
# 在 Pod 启动时由 (nohup sh /init.sh > /notebook_init.log 2>&1 &) 调用
# ============================================================================

set -e

# ─── SSH 配置 ────────────────────────────────────────────────
echo "Port ${SSH_PORT}" >> /etc/ssh/sshd_config
sed -i "s/#PermitRootLogin yes/PermitRootLogin yes/" /etc/ssh/sshd_config
sed -i "s/#PermitRootLogin prohibit-password/PermitRootLogin yes/" /etc/ssh/sshd_config
echo "root:cube-studio" | chpasswd

# 启动 SSH 服务
/usr/sbin/sshd 2>/dev/null || service ssh restart 2>/dev/null || true

echo "[Init] SSH 已配置，端口: ${SSH_PORT}"
echo "[Init] SSH 连接命令: ssh -p ${SSH_PORT} root@${SERVICE_EXTERNAL_IP}"

# ─── 示例文件软链接 ──────────────────────────────────────────
if [ -d "/examples" ] && [ -n "${USERNAME}" ]; then
    ln -sf /examples /mnt/${USERNAME}/examples 2>/dev/null || true
    echo "[Init] 示例文件已链接到 /mnt/${USERNAME}/examples"
fi

# ─── 用户自定义初始化 ────────────────────────────────────────
if [ -f "/mnt/${USERNAME}/init.sh" ]; then
    echo "[Init] 执行用户自定义初始化脚本: /mnt/${USERNAME}/init.sh"
    bash /mnt/${USERNAME}/init.sh || echo "[Init] 警告: 用户 init.sh 执行失败"
fi

echo "[Init] 初始化完成"