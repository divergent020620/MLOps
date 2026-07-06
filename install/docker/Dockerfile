# docker build -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.03.01 -f install/docker/Dockerfile .
# docker buildx build --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.03.01 -f install/docker/Dockerfile . --push

FROM ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9-20260301

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY=localhost,127.0.0.1,.aliyun.com
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY} no_proxy=${NO_PROXY}

# HDFS / Kerberos 系统依赖
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends krb5-user libkrb5-dev && \
    rm -rf /var/lib/apt/lists/*

# HDFS 客户端 + Parquet 支持
RUN pip install --no-cache-dir hdfs==2.7.3 requests_kerberos krbcontext pyarrow>=14.0.0

RUN wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/aihub/deeplearning/aihub.zip && mkdir -p /cube-studio/aihub && unzip aihub.zip -d /cube-studio/aihub/ && rm aihub.zip


COPY myapp /home/myapp/myapp
COPY myapp/static/appbuilder/frontend /data/web/frontend
COPY aihub /cube-studio/aihub

# HDFS Kerberos 认证文件
COPY ai_general.keytab /home/myapp/ai_general.keytab
COPY krb5.conf /etc/krb5.conf
# HDFS NameNode hosts 映射 — 构建时 /etc/hosts 只读，请在 K8s deployment 中配置 hostAliases
# 示例:
#   hostAliases:
#   - ip: "10.240.97.120"
#     hostnames:
#     - "zjdsjt26.shbankpp.com"
ENV PATH=/home/myapp/myapp/bin:${PATH:-}
ENV PYTHONPATH=/home/myapp:${PYTHONPATH:-}
COPY install/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /home/myapp/myapp/bin/myapp /entrypoint.sh

# 清除 build 时临时使用的代理，不残留到运行时环境
ENV HTTP_PROXY="" HTTPS_PROXY="" http_proxy="" https_proxy="" NO_PROXY="" no_proxy=""

# ENTRYPOINT ["bash","/entrypoint.sh"]

# HEALTHCHECK CMD ["curl", "-f", "http://localhost:80/health"]





