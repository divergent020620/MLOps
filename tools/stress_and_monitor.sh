#!/bin/bash
# 压测 + 监控一体化脚本
# 用法: bash stress_and_monitor.sh http://192.168.11.11 [并发数]

set -e
URL="${1:-http://192.168.11.11}"
CONCURRENT="${2:-100}"

echo "=========================================="
echo "  Cube Studio 压测 + 资源监控"
echo "  URL: $URL  并发: $CONCURRENT"
echo "=========================================="

# 后台启动资源监控
MONITOR_LOG="/tmp/stress_monitor_$(date +%H%M%S).log"
echo ">>> 开始资源监控，日志: $MONITOR_LOG"

monitor_nodes() {
    while true; do
        echo "--- $(date +%H:%M:%S) ---" >> "$MONITOR_LOG"
        kubectl top nodes 2>/dev/null >> "$MONITOR_LOG" || echo "metrics unavailable" >> "$MONITOR_LOG"
        kubectl top pods -n infra 2>/dev/null >> "$MONITOR_LOG" || true
        kubectl top pods -n istio-system 2>/dev/null >> "$MONITOR_LOG" || true
        kubectl top pods -n monitoring --no-headers 2>/dev/null >> "$MONITOR_LOG" || true
        sleep 10
    done
}

monitor_nodes &
MONITOR_PID=$!

# 执行压测
echo ""
echo ">>> 开始压测..."
python3 /bdm/share_bdm/cube-studio-master/tools/stress_test.py "$URL" --concurrent "$CONCURRENT"
EXIT_CODE=$?

# 多采一轮
sleep 10

# 停止监控
kill $MONITOR_PID 2>/dev/null
wait $MONITOR_PID 2>/dev/null

echo ""
echo ">>> 压测期间资源峰值:"
echo "--- 按节点 ---"
grep -A10 'NAME.*CPU.*MEMORY' "$MONITOR_LOG" | grep -v '^--$' | sort | uniq -c | sort -rn | head -30

echo ""
echo "--- 按 Pod (infra) ---"
grep -A20 'infra' "$MONITOR_LOG" | grep -v '^--$' | sort | uniq -c | sort -rn | head -20

echo ""
echo "完整监控日志: $MONITOR_LOG"
