#!/bin/bash
# ============================================================================
# Cube Studio Notebook — Spark 初始化脚本
# 根据 Pod 环境变量配置 Spark Driver 端口和地址
# ============================================================================

set -e

echo "[SparkInit] 配置 Spark 环境..."

# ─── Spark 默认配置 ──────────────────────────────────────────
if [ -n "${SPARK_HOME}" ] && [ -d "${SPARK_HOME}/conf" ]; then
    SPARK_CONF="${SPARK_HOME}/conf/spark-defaults.conf"

    # 禁用 Spark UI (notebook 场景不需要)
    echo "spark.ui.enabled=false" >> ${SPARK_CONF}

    # Driver 端口 (平台分配)
    if [ -n "${PORT1}" ]; then
        echo "spark.driver.port=${PORT1}" >> ${SPARK_CONF}
    fi
    if [ -n "${PORT2}" ]; then
        echo "spark.blockManager.port=${PORT2}" >> ${SPARK_CONF}
    fi

    # Driver 绑定地址 & 对外地址
    echo "spark.driver.bindAddress=0.0.0.0" >> ${SPARK_CONF}
    if [ -n "${SERVICE_EXTERNAL_IP}" ]; then
        echo "spark.driver.host=${SERVICE_EXTERNAL_IP}" >> ${SPARK_CONF}
    fi

    # Kerberos (如果配置了)
    if [ -f "/home/ai_general/ai_general.keytab" ]; then
        echo "[SparkInit] 检测到 Kerberos keytab，执行 kinit..."
        kinit -kt /home/ai_general/ai_general.keytab ai_general || \
            echo "[SparkInit] 警告: kinit 失败，请检查 keytab 和 krb5.conf"
    fi

    echo "[SparkInit] Spark 配置完成:"
    cat ${SPARK_CONF}
else
    echo "[SparkInit] 警告: SPARK_HOME 未设置或不存在"
fi

echo "[SparkInit] 初始化完成"