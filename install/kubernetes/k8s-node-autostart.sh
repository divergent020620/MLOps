#!/bin/bash
# =============================================================================
# Cube Studio — K8s 节点停电自启动配置脚本
# =============================================================================
# 用途：确保停电恢复后 K8s 节点自动启动所有基础服务。
# 使用方法：在每台 K8s 节点上以 root 执行
#   chmod +x k8s-node-autostart.sh
#   sudo ./k8s-node-autostart.sh
# =============================================================================

set -e

echo "================================================"
echo " Cube Studio — 节点自启动配置"
echo "================================================"

# ---- 1. 容器运行时 ----
# Docker
if command -v docker &>/dev/null; then
    systemctl enable docker --now
    echo "[OK] docker enabled"
fi

# Containerd (如果使用)
if systemctl list-unit-files containerd.service &>/dev/null; then
    systemctl enable containerd --now
    echo "[OK] containerd enabled"
fi

# ---- 2. Kubelet ----
if command -v kubelet &>/dev/null; then
    systemctl enable kubelet --now
    echo "[OK] kubelet enabled"
else
    echo "[WARN] kubelet not found, skip"
fi

# ---- 3. K8s 基础组件 DaemonSet 确保自启 ----
# kube-proxy、flannel/calico 等通常以 DaemonSet 或 static pod 运行，
# kubelet 启动后会自动拉起来，无需额外配置。
# 以下仅处理以 systemd 运行的特殊情况。

# Calico
if systemctl list-unit-files calico-node.service &>/dev/null 2>&1; then
    systemctl enable calico-node --now
    echo "[OK] calico-node enabled"
fi

# ---- 4. 验证 ----
echo ""
echo "================================================"
echo " 自启动状态检查"
echo "================================================"

check_service() {
    local svc=$1
    if systemctl is-enabled "$svc" &>/dev/null; then
        echo "  [OK] $svc"
    else
        echo "  [MISS] $svc"
    fi
}

check_service docker 2>/dev/null || check_service containerd 2>/dev/null
check_service kubelet

echo ""
echo "================================================"
echo " 完成！"
echo ""
echo " 停电恢复后的启动顺序："
echo "   1. 物理机开机"
echo "   2. systemd → docker/containerd"
echo "   3. systemd → kubelet"
echo "   4. kubelet → static pods (etcd, apiserver 等)"
echo "   5. kubelet → kube-proxy, CNI (DaemonSet)"
echo "   6. K8s scheduler → mysql, redis (Deployment)"
echo "   7. K8s scheduler → backend, worker, schedule, watch (Deployment)"
echo "   8. K8s scheduler → frontend (Deployment)"
echo ""
echo " 请确认服务器 BIOS 已设置 'Restore on AC Power Loss' 为 Power On"
echo "================================================"
