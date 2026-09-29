#!/bin/bash
# ============================================================
# Cube Studio HA 停机测试 - 完整版（无 VIP，NodePort 多入口）
# ============================================================
# 适用：无 VIP 方案，前端通过 NodePort 30080 从多节点访问
# 用法：
#   bash ha_full_test.sh                    # 默认测所有 master 的 30080
#   bash ha_full_test.sh 192.168.11.11 30080  # 指定单节点
# ============================================================

# 节点列表（3 master + 2 worker，任一节点 30080 都可访问前端）
NODES=("192.168.11.11" "192.168.11.12" "192.168.11.13")
PORT="30080"
USER="admin"
PASS="admin"
# 虚拟域名：用 --resolve 让不同节点 IP 都解析成同一域名，
# 这样 Cookie 能跨节点复用（模拟浏览器用同一域名访问的真实场景）
VHOST="cubestudio.local"
LOGFILE="/tmp/ha_full_test_$(date +%Y%m%d_%H%M%S).log"

# 支持参数指定单节点
if [ -n "$1" ]; then
    NODES=("$1")
fi
if [ -n "$2" ]; then
    PORT="$2"
fi

echo "测试开始: $(date)" | tee "$LOGFILE"
echo "节点入口: ${NODES[*]}" | tee -a "$LOGFILE"
echo "端口: ${PORT}" | tee -a "$LOGFILE"
echo "日志: ${LOGFILE}" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# ============================================================
# 0. 前置检查 — NodePort 状态 + Pod 分布
# ============================================================
echo "========== 前置检查 ==========" | tee -a "$LOGFILE"
echo "--- istio-ingressgateway 类型 ---" | tee -a "$LOGFILE"
kubectl get svc -n istio-system istio-ingressgateway 2>&1 | tee -a "$LOGFILE"

echo "--- frontend Pod 分布 ---" | tee -a "$LOGFILE"
kubectl get pods -n infra kubeflow-dashboard-frontend -o wide 2>&1 | tee -a "$LOGFILE"

echo "--- backend Pod 分布 ---" | tee -a "$LOGFILE"
kubectl get pods -n infra kubeflow-dashboard -o wide 2>&1 | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# ============================================================
# 1. 获取登录 Cookie（用第一个节点，通过虚拟域名访问）
# ============================================================
PRIMARY="${NODES[0]}"
echo "========== 获取登录 Cookie (via ${PRIMARY}) ==========" | tee -a "$LOGFILE"

CSRF=$(curl -s -c /tmp/ha_cookies.txt \
  --resolve "${VHOST}:${PORT}:${PRIMARY}" \
  "http://${VHOST}:${PORT}/login/" 2>&1 | grep -oP 'csrf_token.*?value="\K[^"]+' | head -1)

LOGIN_RESP=$(curl -s -c /tmp/ha_cookies.txt -b /tmp/ha_cookies.txt \
  -X POST "http://${VHOST}:${PORT}/login/" \
  --resolve "${VHOST}:${PORT}:${PRIMARY}" \
  -d "username=${USER}&password=${PASS}" \
  -w "\n%{http_code}" 2>&1)

LOGIN_CODE=$(echo "$LOGIN_RESP" | tail -1)
if [ "$LOGIN_CODE" = "302" ] || [ "$LOGIN_CODE" = "200" ]; then
    echo "[PASS] 登录成功 (HTTP ${LOGIN_CODE})" | tee -a "$LOGFILE"
else
    echo "[WARN] 登录返回 HTTP ${LOGIN_CODE}（menu/pipeline 测试可能失败）" | tee -a "$LOGFILE"
fi
echo "" | tee -a "$LOGFILE"

# ============================================================
# 2. 持续监控 — 5 维度 × 多入口
# ============================================================
echo "========== 启动持续监控 ==========" | tee -a "$LOGFILE"

monitor() {
    local COOKIE_FILE="/tmp/ha_cookies.txt"
    local count=0
    local node_idx=0
    local num_nodes=${#NODES[@]}

    while true; do
        count=$((count + 1))
        TS=$(date +%H:%M:%S)
        # 轮询访问不同节点，测试多入口都可用
        NODE="${NODES[$((count % num_nodes))]}"
        echo -n "[$TS] #${count} ${NODE} " | tee -a "$LOGFILE"

        # 测试 1: 静态页面
        R1=$(curl -s -o /dev/null -w "%{http_code}" \
          --resolve "${VHOST}:${PORT}:${NODE}" \
          "http://${VHOST}:${PORT}/frontend/" --connect-timeout 5 2>/dev/null || echo "000")
        echo -n "frontend:${R1} " | tee -a "$LOGFILE"

        # 测试 2: 健康检查
        R2=$(curl -s -o /dev/null -w "%{http_code}" \
          --resolve "${VHOST}:${PORT}:${NODE}" \
          "http://${VHOST}:${PORT}/health" --connect-timeout 5 2>/dev/null || echo "000")
        echo -n "health:${R2} " | tee -a "$LOGFILE"

        # 测试 3: 登录 API（测试后端处理能力）
        R3=$(curl -s -o /dev/null -w "%{http_code}" \
          --resolve "${VHOST}:${PORT}:${NODE}" \
          -X POST "http://${VHOST}:${PORT}/login/" \
          -d "username=${USER}&password=${PASS}" \
          --connect-timeout 5 2>/dev/null || echo "000")
        echo -n "login:${R3} " | tee -a "$LOGFILE"

        # 测试 4: 菜单 API（需认证 + 查数据库，通过虚拟域名让 Cookie 跨节点复用）
        R4=$(curl -s -o /dev/null -w "%{http_code}" \
          -b "$COOKIE_FILE" \
          --resolve "${VHOST}:${PORT}:${NODE}" \
          "http://${VHOST}:${PORT}/myapp/menu" \
          --connect-timeout 5 2>/dev/null || echo "000")
        echo -n "menu:${R4} " | tee -a "$LOGFILE"

        # 测试 5: Pipeline API（需认证 + 查数据库）
        R5=$(curl -s -o /dev/null -w "%{http_code}" \
          -b "$COOKIE_FILE" \
          --resolve "${VHOST}:${PORT}:${NODE}" \
          "http://${VHOST}:${PORT}/pipeline_modelview/api/" \
          --connect-timeout 5 2>/dev/null || echo "000")
        echo "pipeline:${R5}" | tee -a "$LOGFILE"

        sleep 0.5
    done
}

monitor &
MONITOR_PID=$!

echo "监控 PID: ${MONITOR_PID}" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

# ============================================================
# 测试流程提示
# ============================================================
cat << EOF

============================================
  监控已启动，每轮轮询访问不同节点:
    ${NODES[*]}

  测试 5 个维度:
  1. frontend  — 静态页面 (Nginx)
  2. health    — 后端存活 (Gunicorn)
  3. login     — 登录认证 (Flask + DB)
  4. menu      — 菜单 API (需认证 + 查 DB)
  5. pipeline  — Pipeline API (需认证 + 查 DB)

  现在可以测试 HA：
============================================

第一轮：停 master2 的 kubelet
  SSH 到 192.168.11.12: systemctl stop kubelet
  观察输出，确认无持续 5xx → systemctl start kubelet

第二轮：停 master3 的 kubelet
  SSH 到 192.168.11.13: systemctl stop kubelet
  观察输出 → systemctl start kubelet

第三轮：停 master1 的 apiserver（不能停 kubelet，否则 kubectl 失效）
  mv /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/
  观察输出 → mv /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/

============================================
测试完后 Ctrl+C 停止监控，然后执行:
  kill $MONITOR_PID 2>/dev/null
  echo "=== 测试结果 ==="
  grep -cE "FAIL|000|5[0-9][0-9]" $LOGFILE
  echo "完整日志: $LOGFILE"
EOF

wait $MONITOR_PID 2>/dev/null
