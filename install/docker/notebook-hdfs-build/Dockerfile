# Cube Studio Notebook — HDFS + Dataset Panel
# 参考官方 images/jupyter-notebook/Dockerfile-ubuntu-conda 构建
# Python 3.7.4 + pip 20.1.1 + JupyterLab 3.4.8 + HDFS + Dataset 扩展
#
# build: docker build --network=host --build-arg HTTP_PROXY=http://x.x.x.x:port -t <镜像名> -f Dockerfile .

FROM ubuntu:20.04

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY=localhost,127.0.0.1,.aliyun.com,.ubuntu.com
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY}
ENV http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY} no_proxy=${NO_PROXY}

ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive

# ─── apt 阿里云镜像 ──────────────────────────────────────
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# ─── 基础工具 ───────────────────────────────────────────
RUN apt update -y && \
    apt install -y -f --no-install-recommends \
        vim wget curl git dnsutils iputils-ping net-tools \
        mysql-client locales zip unzip lsof ca-certificates \
        fonts-wqy-microhei ttf-wqy-zenhei xfonts-wqy && \
    locale-gen zh_CN && locale-gen zh_CN.utf8 && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8
ENV LANGUAGE=zh_CN.UTF-8

# ─── Miniconda + Python 3.7 ────────────────────────────
RUN wget -q https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-4.7.12.1-Linux-x86_64.sh && \
    bash Miniconda3-4.7.12.1-Linux-x86_64.sh -b && \
    rm -f Miniconda3-4.7.12.1-Linux-x86_64.sh

ENV PATH=/root/miniconda3/bin:${PATH:-}
RUN conda create -y -n python37 python=3.7.4
ENV PATH=/root/miniconda3/envs/python37/bin:${PATH:-}
ENV CONDA_DEFAULT_ENV=python37

# ─── pip 20.1.1 ────────────────────────────────────────
RUN pip install --upgrade pip==20.1.1
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple

# ─── Node.js (JupyterLab build 需要) ───────────────────
RUN curl -sL https://deb.nodesource.com/setup_16.x | bash - && \
    apt-get install -y nodejs && \
    npm config set registry https://registry.npmmirror.com

# ─── JupyterLab + 基础包 ───────────────────────────────
RUN pip install --no-cache-dir \
        jupyterlab==3.4.8 notebook==6.4.12 jupyter_server==1.23.0 \
        tornado==6.2 pandas==1.3.5 numpy==1.21.6 pyarrow==12.0.0 \
        requests==2.28.0 pymysql sqlalchemy==1.4.49 pysnooper \
        ipykernel==6.15.0 && \
    rm -rf /tmp/* /var/tmp/* /root/.cache

# ─── Cube Studio Dataset 服务器扩展 ────────────────────
COPY install/docker/notebook-hdfs-build/cube_studio_dataset /opt/cube_studio_dataset
RUN cd /opt/cube_studio_dataset && \
    pip install . --no-deps && \
    jupyter serverextension enable --py cube_studio_dataset --sys-prefix

# ─── Cube Studio Dataset JupyterLab 扩展 (侧边栏) ──────
COPY install/docker/notebook-hdfs-build/labextension /opt/labextension
RUN cd /opt/labextension && \
    npm install --legacy-peer-deps && \
    npm run build && \
    jupyter labextension install /opt/labextension --no-build

# ─── JupyterLab 完整构建 ───────────────────────────────
RUN jupyter lab build && \
    rm -rf /tmp/* /root/.cache /root/.npm /opt/labextension/node_modules

# ─── Dataset Helper ────────────────────────────────────
COPY install/docker/notebook-hdfs-build/dataset_helper.py /opt/dataset_helper.py
COPY install/docker/notebook-hdfs-build/dataset_init.sh /init.sh
RUN chmod +x /init.sh

# 便捷操作
RUN echo "alias ll='ls -alF'" >> ~/.bashrc && \
    echo "alias la='ls -A'" >> ~/.bashrc && \
    echo "alias vi='vim'" >> ~/.bashrc

# 清除 build 时代理，不残留到运行时
ENV HTTP_PROXY="" HTTPS_PROXY="" http_proxy="" https_proxy="" NO_PROXY="" no_proxy=""

WORKDIR /mnt
EXPOSE 8888 3000
