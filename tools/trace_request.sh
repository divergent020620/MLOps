#!/bin/bash
# ============================================================
# Cube Studio 请求路由抓包脚本
# 用途：追踪外部请求 → VIP → 节点 → iptables → Pod 的完整路径
#
# 用法：
#   bash trace_request.sh                    # 持续抓包，Ctrl+C 停止
#   bash trace_request.sh --port 30080       # 指定端口（默认 80）
#   bash trace_request.sh --src 10.240.125.100  # 指定 VIP
# ============================================================

VIP="${VIP:-10.240.125.100}"
PORT="${1:-80}"
SRC_FILTER="${2:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Cube Studio 请求路由追踪${NC}"
echo -e "${CYAN}  VIP: ${VIP}  Port: ${PORT}${NC}"
echo -e "${CYAN}  $(date)${NC}"
echo -e "${CYAN}============================================================${NC}"

# ============================================================
# 1. 当前拓扑概览
# ============================================================
echo -e "\n${YELLOW}[1] 节点拓扑${NC}"
kubectl get nodes -o custom-columns="NAME:.metadata.name,IP:.status.addresses[?(@.type=='InternalIP')].address,ROLE:.metadata.labels['node-role\.kubernetes\.io/control-plane'],METALLB_SPEAKER:.metadata.labels['metallb\.io/speaker']" 2>/dev/null

echo -e "\n${YELLOW}[2] LoadBalancer Service${NC}"
kubectl get svc -A --field-selector spec.type=LoadBalancer 2>/dev/null

echo -e "\n${YELLOW}[3] istio-ingressgateway 的 Endpoints${NC}"
kubectl get endpoints -n istio-system istio-ingressgateway -o wide 2>/dev/null

echo -e "\n${YELLOW}[4] 目标 Pod 分布${NC}"
kubectl get pods -n infra kubeflow-dashboard-frontend -o wide 2>/dev/null

# ============================================================
# 2. iptables 规则追踪
# ============================================================
echo -e "\n${YELLOW}[5] iptables NAT 链路（简化）${NC}"
echo -e "${BLUE}--- PREROUTING → KUBE-SERVICES ---${NC}"
iptables -t nat -L PREROUTING 2>/dev/null | grep -iE "KUBE|${PORT}" | head -20

echo -e "\n${BLUE}--- KUBE-SERVICES → istio-ingressgateway ---${NC}"
# 找 istio-ingressgateway 的 ClusterIP
ISIO_SVC_IP=$(kubectl get svc -n istio-system istio-ingressgateway -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
if [ -n "$ISIO_SVC_IP" ]; then
    echo "  istio-ingressgateway ClusterIP: ${ISIO_SVC_IP}"
    echo "  匹配的 KUBE-SVC 链:"
    iptables -t nat -L KUBE-SERVICES 2>/dev/null | grep -A3 "$ISIO_SVC_IP" | head -10
fi

echo -e "\n${BLUE}--- KUBE-SVC → KUBE-SEP (Pod 选择) ---${NC}"
iptables -t nat -L KUBE-SERVICES 2>/dev/null | grep -E "KUBE-SVC-|KUBE-SEP-" | head -20

# ============================================================
# 3. ARP 表检查（VIP 被谁劫持）
# ============================================================
echo -e "\n${YELLOW}[6] ARP 表（VIP 对应哪个 MAC / 节点）${NC}"
arp -a 2>/dev/null | grep -iE "$(echo $VIP | cut -d. -f4)" || ip neigh show | grep "$VIP"

echo -e "\n${YELLOW}[7] 本机 IP 地址（VIP 是否在本机）${NC}"
ip addr show | grep -A2 -E "${VIP}|inet " | grep -B1 "inet "

# ============================================================
# 4. 实时抓包
# ============================================================
echo -e "\n${YELLOW}[8] 实时抓包（Ctrl+C 停止）${NC}"
echo -e "  监听目标: ${VIP} 端口 ${PORT}"
echo -e "  出站看 OUTPUT，入站看所有接口"
echo ""

# 构建 tcpdump 过滤条件
FILTER="host ${VIP} and port ${PORT}"
if [ -n "$SRC_FILTER" ]; then
    FILTER="${FILTER} and host ${SRC_FILTER}"
fi

# 抓包 + 时间戳 + 来源接口
tcpdump -nn -i any -tttt -v "$FILTER" 2>/dev/null || \
tcpdump -nn -i any -tttt "$FILTER" 2>/dev/null || {
    echo -e "${RED}tcpdump 不可用，尝试简化抓包...${NC}"

    # 找主要网卡
    IFACE=$(ip route get "$VIP" 2>/dev/null | grep -oP 'dev \K\S+' || echo "eth0")
    echo "  使用网卡: ${IFACE}"
    tcpdump -nn -i "$IFACE" -tttt "$FILTER" 2>/dev/null
}
