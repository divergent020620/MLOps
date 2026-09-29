#!/bin/bash
# ============================================================
# Cube Studio 3 节点 HA 停机测试脚本
# 测试目标：停掉任意一台 master，用户无感知
# 入口 IP：192.168.11.100（MetalLB VIP）
# ============================================================
set -e

VIP="192.168.11.100"
NAMESPACE="infra"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass()  { echo -e "${GREEN}[PASS]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; }
info()  { echo -e "${YELLOW}[INFO]${NC} $*"; }

# ============================================================
# 1. 测试前检查
# ============================================================
preflight() {
    info "========== 测试前检查 =========="

    # 节点数
    NODES=$(kubectl get nodes -l kubeflow-dashboard=true --no-headers | wc -l)
    if [ "$NODES" -ge 3 ]; then
        pass "可调度节点数: $NODES"
    else
        fail "可调度节点数不足: $NODES (需要 >= 3)"
        exit 1
    fi

    # 前端 Pod 分布
    FRONTEND_NODES=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard-frontend -o jsonpath='{.items[*].spec.nodeName}')
    FRONTEND_COUNT=$(echo "$FRONTEND_NODES" | wc -w)
    FRONTEND_UNIQUE=$(echo "$FRONTEND_NODES" | tr ' ' '\n' | sort -u | wc -l)
    if [ "$FRONTEND_COUNT" -ge 2 ] && [ "$FRONTEND_UNIQUE" -ge 2 ]; then
        pass "前端: ${FRONTEND_COUNT} 个 Pod, ${FRONTEND_UNIQUE} 个不同节点"
    else
        fail "前端分布异常: ${FRONTEND_COUNT} Pods / ${FRONTEND_UNIQUE} 节点"
    fi
    kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard-frontend -o wide

    # 后端 Pod 分布
    BACKEND_NODES=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard -o jsonpath='{.items[*].spec.nodeName}')
    BACKEND_COUNT=$(echo "$BACKEND_NODES" | wc -w)
    BACKEND_UNIQUE=$(echo "$BACKEND_NODES" | tr ' ' '\n' | sort -u | wc -l)
    if [ "$BACKEND_COUNT" -ge 2 ] && [ "$BACKEND_UNIQUE" -ge 2 ]; then
        pass "后端: ${BACKEND_COUNT} 个 Pod, ${BACKEND_UNIQUE} 个不同节点"
    else
        fail "后端分布异常: ${BACKEND_COUNT} Pods / ${BACKEND_UNIQUE} 节点"
    fi
    kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard -o wide

    # IngressGateway 分布
    GW_NODES=$(kubectl get pods -n istio-system -l istio=ingressgateway -o jsonpath='{.items[*].spec.nodeName}')
    GW_COUNT=$(echo "$GW_NODES" | wc -w)
    GW_UNIQUE=$(echo "$GW_NODES" | tr ' ' '\n' | sort -u | wc -l)
    if [ "$GW_COUNT" -ge 2 ] && [ "$GW_UNIQUE" -ge 2 ]; then
        pass "IngressGateway: ${GW_COUNT} 个 Pod, ${GW_UNIQUE} 个不同节点"
    else
        fail "IngressGateway 分布异常: ${GW_COUNT} Pods / ${GW_UNIQUE} 节点"
    fi
    kubectl get pods -n istio-system -l istio=ingressgateway -o wide

    # VIP 可达
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${VIP}/frontend/" --connect-timeout 5 || echo "000")
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
        pass "VIP ${VIP} 可达 (HTTP ${HTTP_CODE})"
    else
        fail "VIP ${VIP} 不可达 (HTTP ${HTTP_CODE})"
        exit 1
    fi

    # 所有 Pod Ready
    NOT_READY=$(kubectl get pods -n "$NAMESPACE" --no-headers | grep -v -c 'Running\|Completed' || true)
    if [ "$NOT_READY" -eq 0 ]; then
        pass "所有 Pod 运行正常"
    else
        fail "有 ${NOT_READY} 个 Pod 异常"
        kubectl get pods -n "$NAMESPACE"
    fi
}

# ============================================================
# 2. 选择要停机的节点（避开 frontend+backend 都有的节点）
# ============================================================
select_target_node() {
    info "========== 选择停机节点 =========="

    # 列出每个节点上的关键 Pod
    for node in $(kubectl get nodes -l kubeflow-dashboard=true -o jsonpath='{.items[*].metadata.name}'); do
        FE=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard-frontend --field-selector spec.nodeName="$node" --no-headers 2>/dev/null | wc -l)
        BE=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard --field-selector spec.nodeName="$node" --no-headers 2>/dev/null | wc -l)
        GW=$(kubectl get pods -n istio-system -l istio=ingressgateway --field-selector spec.nodeName="$node" --no-headers 2>/dev/null | wc -l)
        echo "  $node : frontend=$FE  backend=$BE  ingressgateway=$GW"
    done

    # 选一台同时没有 frontend 和 backend 的节点（如果有的话）
    TARGET=""
    for node in $(kubectl get nodes -l kubeflow-dashboard=true -o jsonpath='{.items[*].metadata.name}'); do
        FE=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard-frontend --field-selector spec.nodeName="$node" --no-headers 2>/dev/null | wc -l)
        BE=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard --field-selector spec.nodeName="$node" --no-headers 2>/dev/null | wc -l)
        if [ "$FE" -eq 0 ] && [ "$BE" -eq 0 ]; then
            TARGET="$node"
            break
        fi
    done

    # 如果每台节点都有 frontend 或 backend，选一台只有其中之一的
    if [ -z "$TARGET" ]; then
        for node in $(kubectl get nodes -l kubeflow-dashboard=true -o jsonpath='{.items[*].metadata.name}'); do
            FE=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard-frontend --field-selector spec.nodeName="$node" --no-headers 2>/dev/null | wc -l)
            if [ "$FE" -eq 0 ]; then
                TARGET="$node"
                break
            fi
        done
    fi

    # 实在不行就选第一个 master
    if [ -z "$TARGET" ]; then
        TARGET=$(kubectl get nodes -l kubeflow-dashboard=true -o jsonpath='{.items[0].metadata.name}')
    fi

    info "停机目标节点: ${TARGET}"
    echo "$TARGET"
}

# ============================================================
# 3. 开始监控（后台运行）
# ============================================================
start_monitor() {
    local LOGFILE="$1"
    info "启动监控，日志: ${LOGFILE}"

    # 监控 1: 前端页面
    (
        local count=0 fail_count=0
        while true; do
            count=$((count + 1))
            RESULT=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" "http://${VIP}/frontend/" --connect-timeout 5 2>&1 || echo "000 0")
            CODE=$(echo "$RESULT" | awk '{print $1}')
            TIME=$(echo "$RESULT" | awk '{print $2}')
            TS=$(date +%H:%M:%S)
            if [ "$CODE" = "200" ] || [ "$CODE" = "302" ]; then
                echo "[$TS] #${count} frontend: ${CODE} (${TIME}s)"
            else
                fail_count=$((fail_count + 1))
                echo "[$TS] #${count} frontend: ${CODE} (${TIME}s)  <<< FAIL #${fail_count}"
            fi
            sleep 0.5
        done
    ) > "${LOGFILE}.frontend" 2>&1 &
    MON_FRONTEND_PID=$!

    # 监控 2: 后端健康检查
    (
        local count=0 fail_count=0
        while true; do
            count=$((count + 1))
            RESULT=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" "http://${VIP}/health" --connect-timeout 5 2>&1 || echo "000 0")
            CODE=$(echo "$RESULT" | awk '{print $1}')
            TIME=$(echo "$RESULT" | awk '{print $2}')
            TS=$(date +%H:%M:%S)
            if [ "$CODE" = "200" ]; then
                echo "[$TS] #${count} health: ${CODE} (${TIME}s)"
            else
                fail_count=$((fail_count + 1))
                echo "[$TS] #${count} health: ${CODE} (${TIME}s)  <<< FAIL #${fail_count}"
            fi
            sleep 0.5
        done
    ) > "${LOGFILE}.health" 2>&1 &
    MON_HEALTH_PID=$!

    # 监控 3: Pod 状态变化
    (
        while true; do
            TS=$(date +%H:%M:%S)
            kubectl get pods -n "$NAMESPACE" -o wide --no-headers 2>/dev/null | while read line; do
                echo "[$TS] $line"
            done
            sleep 3
        done
    ) > "${LOGFILE}.pods" 2>&1 &
    MON_PODS_PID=$!

    info "监控 PID: frontend=$MON_FRONTEND_PID  health=$MON_HEALTH_PID  pods=$MON_PODS_PID"
}

stop_monitor() {
    info "停止监控..."
    kill $MON_FRONTEND_PID $MON_HEALTH_PID $MON_PODS_PID 2>/dev/null || true
    wait $MON_FRONTEND_PID $MON_HEALTH_PID $MON_PODS_PID 2>/dev/null || true
}

# ============================================================
# 4. 执行停机
# ============================================================
shutdown_node() {
    local NODE="$1"
    info "========== 停掉节点: ${NODE} =========="
    echo "执行时间: $(date)"
    echo ""
    echo "方式 1 - 停止 kubelet（在目标节点上执行）:"
    echo "  ssh ${NODE} 'systemctl stop kubelet'"
    echo ""
    echo "方式 2 - cordon + drain（在任意 master 上执行）:"
    echo "  kubectl cordon ${NODE}"
    echo "  kubectl drain ${NODE} --ignore-daemonsets --delete-emptydir-data --force --grace-period=30"
    echo ""
    echo "方式 3 - 直接关机（在目标节点上执行）:"
    echo "  ssh ${NODE} 'shutdown -h now'"
    echo ""
    info "推荐测试流程:"
    echo "  1. 启动监控脚本（另开终端）"
    echo "  2. 执行 kubectl cordon ${NODE}"
    echo "  3. 执行 kubectl drain ${NODE} --ignore-daemonsets --delete-emptydir-data --force"
    echo "  4. 观察监控输出，确认无 5xx 错误"
    echo "  5. 等待 Pod 在其他节点重建完毕"
    echo "  6. 恢复节点"

    # 提示用户手动操作（停机太危险，需要人工确认）
    info "请手动执行停机操作。脚本只做监控和检查。"
}

# ============================================================
# 5. 等待集群恢复
# ============================================================
wait_recovery() {
    info "========== 等待集群恢复 =========="
    local MAX_WAIT=300  # 最多等 5 分钟
    local START=$(date +%s)

    while true; do
        local NOW=$(date +%s)
        local ELAPSED=$((NOW - START))

        if [ $ELAPSED -ge $MAX_WAIT ]; then
            fail "等待超时 (${MAX_WAIT}s)"
            break
        fi

        # 检查前端
        FE_READY=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard-frontend --no-headers 2>/dev/null | grep -c 'Running\|Completed' || echo 0)
        BE_READY=$(kubectl get pods -n "$NAMESPACE" -l app=kubeflow-dashboard --no-headers 2>/dev/null | grep -c 'Running\|Completed' || echo 0)

        if [ "$FE_READY" -ge 2 ] && [ "$BE_READY" -ge 2 ]; then
            pass "所有 Pod 恢复完毕 (${ELAPSED}s)"
            kubectl get pods -n "$NAMESPACE" -o wide
            break
        fi

        echo "[${ELAPSED}s] frontend=${FE_READY}/2  backend=${BE_READY}/2"
        sleep 5
    done
}

# ============================================================
# 6. 恢复节点
# ============================================================
recover_node() {
    local NODE="$1"
    info "========== 恢复节点: ${NODE} =========="

    echo "在目标节点上执行:"
    echo "  systemctl start kubelet"
    echo ""
    echo "然后在 master 上执行:"
    echo "  kubectl uncordon ${NODE}"
    echo ""
    echo "验证节点恢复:"
    echo "  kubectl get nodes"
    echo ""
}

# ============================================================
# 7. 测试后报告
# ============================================================
generate_report() {
    local LOGFILE="$1"
    info "========== 测试报告 =========="

    echo ""
    echo "--- 前端监控 ---"
    TOTAL_FE=$(grep -c "frontend:" "${LOGFILE}.frontend" 2>/dev/null || echo 0)
    FAIL_FE=$(grep -c "FAIL" "${LOGFILE}.frontend" 2>/dev/null || echo 0)
    echo "总请求: $TOTAL_FE  失败: $FAIL_FE"
    if [ "$FAIL_FE" -eq 0 ]; then
        pass "前端: 零失败"
    else
        fail "前端: ${FAIL_FE} 次失败"
        grep "FAIL" "${LOGFILE}.frontend" | head -10
    fi

    echo ""
    echo "--- 后端健康检查 ---"
    TOTAL_HL=$(grep -c "health:" "${LOGFILE}.health" 2>/dev/null || echo 0)
    FAIL_HL=$(grep -c "FAIL" "${LOGFILE}.health" 2>/dev/null || echo 0)
    echo "总请求: $TOTAL_HL  失败: $FAIL_HL"
    if [ "$FAIL_HL" -eq 0 ]; then
        pass "后端: 零失败"
    else
        fail "后端: ${FAIL_HL} 次失败"
        grep "FAIL" "${LOGFILE}.health" | head -10
    fi

    echo ""
    echo "--- 延迟分析 ---"
    echo "前端最大延迟:"
    grep "frontend:" "${LOGFILE}.frontend" 2>/dev/null | \
        sed 's/.*(\(.*\)s)/\1/' | sort -rn | head -3
    echo "后端最大延迟:"
    grep "health:" "${LOGFILE}.health" 2>/dev/null | \
        sed 's/.*(\(.*\)s)/\1/' | sort -rn | head -3

    echo ""
    echo "--- 结论 ---"
    if [ "$FAIL_FE" -eq 0 ] && [ "$FAIL_HL" -eq 0 ]; then
        pass "HA 测试通过！停机期间用户无感知。"
    elif [ "$FAIL_FE" -le 3 ] && [ "$FAIL_HL" -le 3 ]; then
        pass "HA 测试基本通过（${FAIL_FE}/${FAIL_HL} 次短暂抖动）。"
    else
        fail "HA 测试未通过，请查看日志: ${LOGFILE}.*"
    fi
}

# ============================================================
# 主流程
# ============================================================
main() {
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOGFILE="/tmp/ha_test_${TIMESTAMP}"

    echo "Cube Studio HA 停机测试"
    echo "VIP: ${VIP}"
    echo "日志: ${LOGFILE}.*"
    echo ""

    # Step 1: 检查
    preflight

    # Step 2: 选目标节点
    TARGET=$(select_target_node)

    # Step 3: 启动监控
    start_monitor "$LOGFILE"

    # Step 4: 提示停机
    echo ""
    info "============================================"
    info "  监控已启动。现在请手动停机: ${TARGET}"
    info "  推荐命令:"
    info "    kubectl cordon ${TARGET}"
    info "    kubectl drain ${TARGET} --ignore-daemonsets --delete-emptydir-data --force"
    info ""
    info "  完成后按 Enter 进入等待恢复阶段..."
    info "============================================"
    read -r

    # Step 5: 等待恢复
    wait_recovery

    # Step 6: 停止监控
    stop_monitor

    # Step 7: 恢复节点提示
    recover_node "$TARGET"

    # Step 8: 生成报告
    generate_report "$LOGFILE"

    echo ""
    info "完整日志: ${LOGFILE}.*"
}

# 如果直接执行，跑主流程；如果 source，只加载函数
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
else
    info "函数已加载: preflight / select_target_node / start_monitor / stop_monitor / wait_recovery / generate_report"
fi
