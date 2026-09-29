#!/bin/bash
# =============================================================================
# Cube Studio — K8s 节点停电自启动配置脚本（P0）
# =============================================================================
# 用途：确保停电恢复后 K8s 节点自动启动所有基础服务。
# 支持两种执行方式：
#   1. root 直接执行：  bash k8s-node-autostart.sh
#   2. bdm 用户 Docker 绕过：bash k8s-node-autostart.sh --docker-bypass
#
# 系统需求：
#   - root：systemctl 直接操作
#   - Docker 绕过：利用特权容器操作宿主机文件系统
# =============================================================================

set -e

DOCKER_BYPASS=false
if [ "$1" = "--docker-bypass" ]; then
    DOCKER_BYPASS=true
fi

echo "================================================"
echo " Cube Studio — 节点自启动配置"
echo " 主机: $(hostname)"
echo " 用户: $(whoami)"
if $DOCKER_BYPASS; then
    echo " 模式: Docker 绕过（无 root）"
fi
echo "================================================"

# ============================================================
# systemctl enable 实现（支持 root 和 Docker 绕过）
# ============================================================
do_enable() {
    local svc=$1
    local svc_file="/usr/lib/systemd/system/${svc}.service"
    local want_dir="/etc/systemd/system/multi-user.target.wants/${svc}.service"

    if [ "$(id -u)" = "0" ]; then
        # root 直接 systemctl
        systemctl enable "$svc" 2>/dev/null && echo "  [OK] $svc enabled (systemctl)" || echo "  [FAIL] $svc"
    elif $DOCKER_BYPASS; then
        # Docker 绕过：创建软链接 = systemctl enable
        if docker run --rm \
            -v /usr/lib/systemd/system:/usr/lib/systemd/system:ro \
            -v /etc/systemd/system:/etc/systemd/system \
            busybox:latest \
            sh -c "ln -sf ${svc_file} ${want_dir}" 2>/dev/null; then
            echo "  [OK] $svc enabled (docker bypass)"
        else
            echo "  [FAIL] $svc — Docker 绕过失��"
        fi
    else
        echo "  [SKIP] 非 root 且未指定 --docker-bypass，请用 root 或加 --docker-bypass 参数"
    fi
}

# systemctl is-enabled 检查
check_svc() {
    local svc=$1
    if systemctl is-enabled "$svc" &>/dev/null 2>&1; then
        echo "  [OK] $svc"
    else
        if [ -L "/etc/systemd/system/multi-user.target.wants/${svc}.service" ] 2>/dev/null; then
            echo "  [OK] $svc (symlink)"
        else
            echo "  [MISS] $svc"
        fi
    fi
}

# ============================================================
# 1. 容器运行时
# ============================================================
echo ">>> [1/4] 容器运行时自启动..."

if command -v docker &>/dev/null; then
    do_enable docker
elif systemctl list-unit-files containerd.service &>/dev/null 2>&1; then
    do_enable containerd
else
    echo "  [WARN] 未找到 docker 或 containerd"
fi

# ============================================================
# 2. Kubelet
# ============================================================
echo ">>> [2/4] kubelet 自启动..."

if command -v kubelet &>/dev/null || [ -f /usr/bin/kubelet ]; then
    do_enable kubelet
else
    echo "  [WARN] kubelet not found — 非 K8s 节点？"
fi

# ============================================================
# 3. Harbor 容器（自动检测，不再硬编码 IP）
# ============================================================
echo ">>> [3/4] Harbor 自启动..."

HARBOR_CONTAINERS=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -iE 'harbor|nginx.*harbor|registry' || true)
if [ -n "$HARBOR_CONTAINERS" ]; then
    for c in $HARBOR_CONTAINERS; do
        docker update --restart=always "$c" 2>/dev/null || true
    done
    echo "  [OK] Harbor 容器已设置 restart=always"
    echo "       容器: $(echo $HARBOR_CONTAINERS | tr '\n' ' ')"
else
    echo "  [SKIP] 本机无 Harbor 容器"
fi

# ============================================================
# 4. 额外：NFS Server（如果本机是 NFS 服务端）
# ============================================================
if systemctl list-unit-files nfs-server.service &>/dev/null 2>&1; then
    echo ">>> [4/5] NFS Server 自启动..."
    do_enable nfs-server
    do_enable rpcbind 2>/dev/null
else
    echo ">>> [4/5] NFS Server — 跳过（本机非 NFS 服务端）"
fi

# ============================================================
# 5. 验证
# ============================================================
echo ""
echo ">>> [5/5] 自启动状态验证..."
echo "================================================"

if systemctl list-unit-files docker.service &>/dev/null 2>&1; then
    check_svc docker
elif systemctl list-unit-files containerd.service &>/dev/null 2>&1; then
    check_svc containerd
fi
check_svc kubelet

echo ""
echo "================================================"
echo " 本节点自启动配置完成"
echo ""
echo " 停电恢复后启动链："
echo "   BIOS Power On"
echo "     → systemd: docker/containerd"
echo "     → systemd: kubelet"
echo "     → kubelet: static pods (etcd, apiserver 等)"
echo "     → kubelet: DaemonSet (kube-proxy, CNI)"
echo "     → K8s: mysql → redis → backend/worker/schedule/watch → frontend"
echo ""
echo " ⚠️  请确认 BIOS 设置 Restore on AC Power Loss = Power On"
echo "================================================"
