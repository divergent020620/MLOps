# Cube Studio 全国产化容器基座迁移 — 研究方案

> **Superpowers Phase 1: Brainstorming / Design**
> 状态：待评审
> 日期：2026-07-30

---

## 1. 背景与目标

### 1.1 当前状态

Cube Studio 所有前后端 Pod 的容器基座均为 **Ubuntu**（22.04 / 20.04），包括：

| 镜像 | 当前基座 | 用途 |
|------|----------|------|
| `kubeflow-dashboard:base-python3.9` | `ubuntu:22.04` | 后端基础镜像（Python 3.9 + Node 16 + Supervisor） |
| `kubeflow-dashboard:2026xxxx` | 继承 base | 后端生产镜像（Flask + Celery + HDFS） |
| `kubeflow-dashboard-frontend:2026xxxx` | ubuntu（nginx） | 前端镜像 |
| Notebook 系列（jupyter/vscode/rstudio 等） | ubuntu:20.04 / ubuntu:22.04 | Jupyter 开发环境 |
| Job Template × 14 | ubuntu:22.04 / python:3.9 / ray | 训练/数据处理任务 |

### 1.2 目标

将所有容器基座从 **Ubuntu** 迁移到 **麒麟 v10 SP3 (Kylin v10 SP3)**，实现全国产化。

### 1.3 前置条件

- 构建机器上有离线镜像：`cube-studio/kylin:v10-sp3-240`（实际 tag 为 `v10-sp3-2403`）
- 已有成功的 Jupyter 国产化改造参考：`domestic-jupyter/Dockerfile.hdfs`、`domestic-jupyter/Dockerfile.spark`
- 麒麟系统已知缺陷：缺少 gcc/gcc-c++/make 等编译工具链（需在 Dockerfile 中补充）

---

## 2. 基座差异分析（Ubuntu 22.04 → Kylin v10 SP3）

### 2.1 包管理器

| 维度 | Ubuntu | Kylin v10 SP3 |
|------|--------|---------------|
| 包管理器 | `apt-get` | `yum` / `dnf` |
| 源配置 | `sources.list` | `/etc/yum.repos.d/*.repo` |
| 更新命令 | `apt-get update` | `yum makecache`（离线构建：`--nogpgcheck`） |

### 2.2 系统工具包名映射

| 功能 | Ubuntu 包名 | Kylin 包名 | 备注 |
|------|------------|-----------|------|
| 编辑器 | `vim` | `vim` | 同名 |
| 下载工具 | `wget curl` | `wget curl` | 同名 |
| Git | `git` | `git` | 同名 |
| 解压缩 | `zip unzip` | `zip unzip` | 同名 |
| 进程管理 | `procps` | `procps-ng` | **名称不同** |
| 网络工具 | `net-tools dnsutils iputils-ping` | `net-tools bind-utils iputils` | `dnsutils` → `bind-utils` |
| 进程查看 | `lsof` | `lsof` | 同名 |
| 证书 | `ca-certificates ca-certificates-java` | `ca-certificates` | Java 证书需另查 |
| 数据库客户端 | `mysql-client` | `mariadb` 或 `mysql` | **需验证** |
| JSON 处理 | `jq` | `jq` | 同名 |
| 字体 | `fonts-wqy-microhei ttf-wqy-zenhei xfonts-wqy` | `wqy-microhei-fonts` | zenhei/xfonts 需另查 |
| 中文本地化 | `locales` + `locale-gen` | `glibc-locale-source` 或系统自带 | **机制不同** |
| SSH 服务 | `openssh-server` | `openssh-server` | 同名 |
| 编译工具 | `build-essential` | `gcc gcc-c++ make` | **需显式安装** |
| Python 依赖 | `python3-pip python3.9-distutils` | `python39-pip python39-devel`（麒麟系统自带 Python 3.9） | 同名 RPM 包，机制一致 |
| HDFS/Kerberos | `krb5-user libkrb5-dev` | `krb5-workstation krb5-libs krb5-devel` | 参考 domestic-jupyter |
| SASL | `libsasl2-dev` | `cyrus-sasl-devel cyrus-sasl` | 参考 domestic-jupyter |
| PostgreSQL | `libpq-dev` | `libpq-devel` | 同名但后缀不同 |
| Supervisor | `supervisor` (apt) | `supervisor` (pip) | **apt 源中可能无此包，改 pip 安装** |
| systemd | systemd 系列 | systemd 系列 | Kylin 自带 |

### 2.3 Python 安装路径差异

| 维度 | Ubuntu 方案 | Kylin 方案 |
|------|------------|-----------|
| Python 来源 | `deadsnakes PPA` → `apt install python3.9` | **麒麟系统自带 Python 3.9** |
| pip | `python3-pip` apt 包 | `python3-pip` yum 包 或 `ensurepip` |
| 版本管理 | apt 版本固定 | 系统 RPM 管理 |

**结论**：无需 Miniconda（domestic-jupyter 用 Miniconda 是因为需要 Python 3.7 兼容 JupyterLab 3.4.8，不是麒麟缺少 Python）。base 镜像直接用麒麟系统自带的 Python 3.9。

### 2.4 Node.js 安装

| 维度 | Ubuntu 方案 | Kylin 方案 |
|------|------------|-----------|
| 安装方式 | `curl -fsSL deb.nodesource.com/setup_16.x \| bash` + apt | yum install nodejs npm（版本可能较老，如 12.x / 14.x） 或 二进制包 |

**风险**：Kylin yum 源中的 Node.js 版本可能不满足前端构建要求（需要 Node 16+）。可参考 domestic-jupyter 中直接 `yum install nodejs npm` 的做法，但需验证版本。

### 2.5 Locale / 中文支持

Ubuntu：`locale-gen zh_CN.utf8`
Kylin：系统已自带中文 locale，直接设置环境变量即可（参考 domestic-jupyter 做法）：
```dockerfile
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8
ENV LANGUAGE=zh_CN.UTF-8
```

---

## 3. 迁移范围与分层策略

### 3.1 分层模型

```
Layer 0: kylin:v10-sp3-240                    ← 已有离线镜像，不动
         │
Layer 1: base-python3.9-kylin                 ← ★ 核心改造：Dockerfile-base.kylin
         │  ├── yum 系统依赖（gcc, vim, curl, git, 字体...）
         │  ├── 麒麟系统 Python 3.9（yum python39）
         │  ├── Node.js 16+
         │  ├── Supervisor（pip 安装）
         │  └── pip install -r requirements.txt
         │
Layer 2: kubeflow-dashboard-kylin             ← Dockerfile.kylin
         │  ├── HDFS/Kerberos 系统包
         │  ├── aihub 资源
         │  ├── myapp 源码
         │  └── entrypoint.sh
         │
Layer 3: frontend-kylin                       ← dockerFrontend/Dockerfile.kylin
         │  └── nginx + 前端构建产物
         │
Layer 4: notebook-kylin-*                     ← ★ 已有参考：domestic-jupyter/
         │  ├── jupyter-kylin-hdfs ✓ (已完成)
         │  ├── jupyter-kylin-spark ✓ (已完成)
         │  └── vscode-kylin, rstudio-kylin (后续)
         │
Layer 5: job-template-*-kylin                 ← 14 个模板逐步迁移
```

### 3.2 迁移清单

#### 必做项（核心服务）

| # | 文件 | 当前基座 | 目标基座 | 优先级 |
|---|------|----------|----------|--------|
| 1 | `install/docker/Dockerfile-base` | `ubuntu:22.04` | `cube-studio/kylin:v10-sp3-2403` | **P0** |
| 2 | `install/docker/Dockerfile` | base ubuntu | base kylin | **P0** |
| 3 | `install/docker/dockerFrontend/Dockerfile` | frontend ubuntu | frontend kylin | **P0** |
| 4 | `install/kubernetes/cube/base/*.yaml` (5个) | 更新镜像 tag | **P0** |
| 5 | `install/docker/config.py` (NOTEBOOK_IMAGES) | 更新镜像列表 | **P0** |

#### 配套项（Notebook 环境）

| # | 文件 | 当前基座 | 目标基座 | 优先级 |
|---|------|----------|----------|--------|
| 6 | `install/docker/notebook-hdfs-build/Dockerfile` | `ubuntu:20.04` | `cube-studio/kylin:v10-sp3-2403` | **P1** |
| 7 | vscode-notebook Dockerfile（如有） | ubuntu | kylin | P2 |
| 8 | rstudio-notebook Dockerfile（如有） | ubuntu | kylin | P2 |
| 9 | enterprise-* notebooks | ubuntu | kylin | P3 |

#### 扩散项（Job Templates）

| # | 模板 | 当前基座 | 优先级 |
|---|------|----------|--------|
| 10 | `job-template/job/datax/Dockerfile` | `ubuntu:22.04` | P2 |
| 11 | `job-template/job/pytorch/Dockerfile` | `${BASE_IMAGE}` 变量 | P2 |
| 12 | `job-template/job/tf/Dockerfile` | 待确认 | P2 |
| 13 | 其余 11 个模板 | 各种基座 | P3 |

---

## 4. 核心技术方案：Dockerfile-base.kylin

### 4.1 设计原则

1. **离线优先**：构建机器无法访问外网，所有依赖需预下载或使用离线 yum 源
2. **镜像体积**：尽量 `yum clean all && rm -rf /var/cache/yum/*`
3. **幂等性**：重复构建产出相同镜像
4. **可维护性**：保持与 `Dockerfile-base` 结构对应，注释说明差异

### 4.2 方案内容

```dockerfile
# ============================================================================
# Cube Studio — 麒麟信创 后端基础镜像
# 对应原: install/docker/Dockerfile-base (ubuntu:22.04)
#
# 构建:
#   docker build --network=host \
#     -t 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin \
#     -f install/docker/Dockerfile-base.kylin .
# ============================================================================

FROM cube-studio/kylin:v10-sp3-2403

ENV TZ=Asia/Shanghai
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8
ENV LANGUAGE=zh_CN.UTF-8

# ── 1. 系统依赖 ────────────────────────────────────────────
# 对照原 Dockerfile-base: apt install → yum install
# ★ 添加 gcc/gcc-c++/make — 麒麟缺少编译环境
RUN yum install -y --nogpgcheck \
        # 编译工具（麒麟缺少）
        gcc gcc-c++ make \
        # Python 3.9 + 开发头文件（麒麟系统自带）
        python39 python39-devel python39-pip \
        # 运维工具
        vim wget curl git unzip zip lsof procps-ng net-tools \
        bind-utils iputils \
        # 证书
        ca-certificates \
        # 数据库客户端
        mariadb \
        # JSON 处理
        jq \
        # 字体 + 中文
        fontconfig wqy-microhei-fonts \
        # SSH / 远程
        openssh-server \
        # SASL（pyhive/thrift 依赖）
        cyrus-sasl-devel cyrus-sasl \
        # PostgreSQL 客户端（psycopg2 编译依赖）
        libpq-devel \
        # Python C 扩展编译依赖
        openssl-devel libffi-devel libev-devel \
        bzip2-devel zlib-devel \
        # Node.js
        nodejs npm \
        # Kerberos
        krb5-workstation krb5-libs krb5-devel \
        # 其他
        bzip2 iproute rsync \
    && yum clean all && rm -rf /var/cache/yum/*

# ── 2. Python 符号链接（兼容原 Dockerfile-base）────────────
# 麒麟系统自带 Python 3.9，直接建立软链接即可
RUN ln -sf /usr/bin/python3.9 /usr/bin/python && \
    ln -sf /usr/bin/python3.9 /usr/bin/python3 && \
    ln -sf /usr/bin/pip3.9 /usr/bin/pip && \
    ln -sf /usr/bin/pip3.9 /usr/bin/pip3

# ── 3. Supervisor ──────────────────────────────────────────
# Kylin yum 源中无 supervisor，改用 pip 安装
RUN pip install --no-cache-dir supervisor && \
    mkdir -p /var/log/supervisor

# ── 4. Python 依赖 ─────────────────────────────────────────
COPY install/docker/requirements.txt /requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /requirements.txt && \
    pip install --no-cache-dir \
        requests_kerberos krbcontext \
    && rm -rf /root/.cache/pip

# ── 5. kubectl（仅 x86_64）──────────────────────────────────
RUN wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl \
        -O /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl

# ── 6. AI Hub 模型市场数据（wget）───────────────────────────
RUN wget -q https://cube-studio.oss-cn-hangzhou.aliyuncs.com/aihub/deeplearning/aihub.zip && \
    mkdir -p /cube-studio/aihub && \
    unzip -q aihub.zip -d /cube-studio/aihub/ && \
    rm aihub.zip

# ── 7. 便捷配置 ────────────────────────────────────────────
RUN echo "alias ll='ls -alF'" >> ~/.bashrc && \
    echo "alias la='ls -A'" >> ~/.bashrc && \
    echo "alias vi='vim'" >> ~/.bashrc

WORKDIR /home/myapp
USER root
EXPOSE 80
```

### 4.3 关键待验证项

| 序号 | 验证项 | 风险等级 | 验证方法 |
|------|--------|----------|----------|
| V1 | Kylin yum 源中 `nodejs` 版本 ≥ 16 | **高** | `yum info nodejs` 或在容器中 `node -v` |
| V2 | `mariadb` 替代 `mysql-client` 可行性 | 中 | `mysql -h` 命令可用性 |
| V3 | Supervisor pip 安装后功能完整性 | 中 | `supervisord -c /etc/supervisord.conf` 启动测试 |
| V4 | `libpq-devel` + psycopg2 编译成功 | 中 | pip install psycopg2-binary 无报错 |
| V5 | `wqy-microhei-fonts` 覆盖所有中文字体需求 | 低 | 检查 `fc-list :lang=zh` 输出 |
| V6 | `bind-utils` 替代 `dnsutils`（nslookup/dig） | 低 | `nslookup` 命令可用 |
| V7 | `cyrus-sasl-devel` 满足 pyhive/thrift-sasl 编译 | 中 | pip install thrift-sasl sasl 无报错 |
| V8 | Kylin 内核兼容性（glibc 版本等） | 中 | `ldd --version` 确认 |
| V9 | entrypoint.sh 中 `npm install && npm run build` | **高** | 前端构建通过（STAGE=build 模式） |

---

## 5. Dockerfile.kylin（后端生产镜像 — 纯 COPY，零联网）

相对于原 `Dockerfile`，所有联网操作（yum/pip/wget）已收敛到 `Dockerfile-base.kylin`，生产镜像仅做源码 COPY：

```dockerfile
# docker build --network=none \
#   -t 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730 \
#   -f install/docker/Dockerfile.kylin .

FROM 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin

# 源码
COPY myapp /home/myapp/myapp
COPY myapp/static/appbuilder/frontend /data/web/frontend

# HDFS Kerberos 认证文件
COPY ai_general.keytab /home/myapp/ai_general.keytab
COPY krb5.conf /etc/krb5.conf

ENV PATH=/home/myapp/myapp/bin:${PATH:-}
ENV PYTHONPATH=/home/myapp:${PYTHONPATH:-}

COPY install/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /home/myapp/myapp/bin/myapp /entrypoint.sh
```

**联网操作收敛清单**：

| 操作 | 原在 Dockerfile | 现已移到 Dockerfile-base.kylin |
|------|----------------|------------------------------|
| `pip install hdfs requests_kerberos krbcontext pyarrow` | Dockerfile | base 第4步 |
| `wget aihub.zip` | Dockerfile | base 第6步 |
| `apt install krb5-user libkrb5-dev` | Dockerfile (Ubuntu) | base 第1步 (yum krb5-*) |

---

## 6. 前端镜像改造

### 6.1 调查结论

通过分析 `build_frontend.sh`、`dockerFrontend/Dockerfile`、`dockerFrontend/start.sh` 和 nginx 配置文件，确认前端镜像结构：

```
Layer 0: kubeflow-dashboard-frontend:20260630v1 (基础镜像)
         ├── nginx (已安装配置好)
         ├── /etc/nginx/nginx.conf
         ├── /etc/nginx/conf.d/default.conf
         ├── /data/web/frontend/ (空目录，预留给构建产物)
         └── start.sh → nginx -g "daemon off;"

Layer 1: dockerFrontend/Dockerfile
         └── COPY ./myapp/static/appbuilder/frontend → /data/web/frontend
```

**关键发现**：`kubeflow-dashboard-frontend:20260630v1` 是一个预构建的 nginx 基础镜像，`build_frontend.sh` 每次只构建最上层（COPY 前端静态文件），不重新构建 nginx 层。

### 6.2 国产化方案

需要一个 **麒麟 + nginx** 的前端基础镜像，替代 `kubeflow-dashboard-frontend:20260630v1`：

```dockerfile
# install/docker/dockerFrontend/Dockerfile-base.kylin
# 构建: docker build -t 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-base \
#   -f install/docker/dockerFrontend/Dockerfile-base.kylin .

FROM cube-studio/kylin:v10-sp3-2403

# nginx — 麒麟 yum 源自带
RUN yum install -y --nogpgcheck nginx && \
    yum clean all && rm -rf /var/cache/yum/*

# nginx 配置
COPY install/docker/dockerFrontend/nginx.conf /etc/nginx/nginx.conf
COPY install/docker/dockerFrontend/nginx.80.conf /etc/nginx/conf.d/default.conf

# 启动脚本
COPY install/docker/dockerFrontend/start.sh /start.sh
RUN chmod +x /start.sh

# 前端文件目录
RUN mkdir -p /data/web/frontend

EXPOSE 80
CMD ["/start.sh"]
```

**风险**：Kylin yum 源中的 nginx 版本可能较老（如 1.14.x vs 最新 1.26.x），但功能满足需求。

---

## 7. Config.py 修改

```python
# install/docker/config.py
# 修改前（示例）：
NOTEBOOK_IMAGES = [
    ['192.168.11.12/cube-studio/notebook:jupyter-ubuntu22.04', 'jupyter（cpu）'],
    ...
]

# 修改后：添加麒麟版本镜像，保留原版作为回退
NOTEBOOK_IMAGES = [
    ['192.168.11.12/cube-studio/notebook:jupyter-kylin-hdfs', 'jupyter-kylin（cpu）'],
    ['192.168.11.12/cube-studio/notebook:jupyter-kylin-spark', 'jupyter-kylin（spark）'],
    # 以下保留原 ubuntu 镜像作为过渡
    ['192.168.11.12/cube-studio/notebook:jupyter-ubuntu22.04', 'jupyter-ubuntu（cpu）'],
    ...
]

# 默认用户镜像
USER_IMAGE = '192.168.11.12/cube-studio/kylin-gpu:cuda11.8.0-cudnn8-python3.9'
# ↑ GPU 镜像需要另外构建，短期可以保持 ubuntu-gpu
```

---

## 8. K8s 部署 YAML 修改

`install/kubernetes/cube/base/` 下的 5 个 Deployment YAML 需要更新 image 字段：

| 文件 | 原 image | 新 image |
|------|----------|----------|
| deploy-backend.yaml | `kubeflow-dashboard:20260703` | `kubeflow-dashboard:kylin-20260730` |
| deploy-schedule.yaml | `kubeflow-dashboard:20260703` | `kubeflow-dashboard:kylin-20260730` |
| deploy-worker.yaml | `kubeflow-dashboard:20260703` | `kubeflow-dashboard:kylin-20260730` |
| deploy-watch.yaml | `kubeflow-dashboard:2026070` | `kubeflow-dashboard:kylin-20260730` |
| deploy-frontend.yaml | `kubeflow-dashboard-frontend:20260630v1` | `kubeflow-dashboard-frontend:kylin-20260730` |

> **注意**：frontend 需要先构建麒麟 nginx 基础镜像（见第 6 节），然后 `build_frontend.sh` 中 `BASE_IMAGE` 改为麒麟版。

---

## 9. 风险矩阵

| 风险 | 严重程度 | 发生概率 | 缓解措施 |
|------|----------|----------|----------|
| **yum 源缺少关键包**（如 nodejs 16, mariadb） | **高** | 中 | 预下载 RPM 包离线安装；或使用二进制 + Miniconda 路线 |
| **pip 依赖编译失败**（cffi, cryptography, psycopg2, sasl, thrift-sasl, gevent, gmssl 等需 C 编译） | **高** | **高** | 麒麟已补 gcc/gcc-c++/make；确保对应的 -devel 包齐全（openssl-devel, libffi-devel, cyrus-sasl-devel, libpq-devel） |
| **glibc 版本不兼容** | 中 | 低 | Kylin v10 SP3 基于 glibc 2.28，与 Ubuntu 22.04 (glibc 2.35) 有一定差距 |
| **entrypoint.sh 中 npm build 失败** | **高** | 中 | Node 版本需 ≥ 16；npm 需配置离线 registry |
| **Supervisor 功能差异** | 低 | 低 | pip 安装的 supervisor 与 apt 安装的功能等同 |
| **GPU 镜像无法国产化** | 低 | — | 已决策：先 CPU 后 GPU，GPU 短期保留 ubuntu-gpu，本次不纳入迁移范围 |
| **Job Template 兼容性** | 低 | — | 已决策：先核心后模板，模板后续按需迁移，不影响本次交付 |
| **entrypoint.sh 中 `myapp fab create-admin` 兼容性** | 中 | 低 | Flask-AppBuilder 使用 Python 接口，操作系统依赖低 |
| **kubectl 二进制兼容性** | 低 | 低 | kubectl 是静态编译的 Go 二进制，不依赖系统库 |

---

## 10. Python 依赖编译风险专项

`requirements.txt` 中以下包涉及 C 扩展编译，需验证麒麟下是否可用：

| 包 | 编译依赖 | Kylin 对应包 | 风险 |
|----|----------|-------------|------|
| `cryptography==43.0.0` | libffi, openssl | `libffi-devel openssl-devel` | 中 |
| `cffi==1.16.0` | libffi | `libffi-devel` | 低 |
| `psycopg2-binary==2.9.8` | libpq | `libpq-devel` | 中 |
| `sasl==0.3.1` | cyrus-sasl | `cyrus-sasl-devel` | **高** |
| `thrift-sasl==0.4.3` | cyrus-sasl | `cyrus-sasl-devel` | **高** |
| `gevent==25.5.1` | libev | `libev-devel` | 中 |
| `gmssl==3.2.2` | openssl | `openssl-devel` | 中 |
| `thrift==0.20.0` | boost? (纯 Python 可能 OK) | - | 低 |
| `kubernetes==25.3.0` | 无（纯 Python） | - | 无 |
| `pyarrow>=14.0.0` | 需 Arrow C++ 库 | - | 中（推荐 pip 安装预编译 wheel） |

**注意**：`sasl==0.3.1` 和 `thrift-sasl==0.4.3` 在麒麟下是最容易出问题的包，domestic-jupyter 中已成功安装，说明 `cyrus-sasl-devel` 补上后可编译通过。

---

## 11. 缺失的 -devel 包补充清单

对照 domestic-jupyter 的成功经验，需在 Dockerfile-base.kylin 中额外补充：

```dockerfile
# Python C 扩展编译所需的 -devel 包（麒麟默认不安装）
RUN yum install -y --nogpgcheck \
        openssl-devel \       # cryptography, gmssl
        libffi-devel \        # cffi, cryptography
        cyrus-sasl-devel \    # sasl, thrift-sasl
        libpq-devel \         # psycopg2 (或直接用 psycopg2-binary)
        libev-devel \         # gevent
        bzip2-devel \         # Python 部分包
        zlib-devel \          # 通用
    && yum clean all
```

---

## 12. 构建流程

### 12.1 前置准备

```bash
# 1. 确认离线镜像可用
docker images | grep kylin
# 预期输出: cube-studio/kylin  v10-sp3-2403  ...

# 2. 验证麒麟自带 Python 版本
docker run --rm cube-studio/kylin:v10-sp3-2403 python3 --version
# 预期: Python 3.9.x

# 3. 验证 yum 关键包可用性（可选）
docker run --rm cube-studio/kylin:v10-sp3-2403 yum list available \
    python39 python39-devel python39-pip nodejs npm nginx supervisor
```

### 12.2 构建顺序

```
Step 1: Dockerfile-base.kylin      → base-python3.9-kylin (预计 30min)
Step 2: Dockerfile.kylin           → kubeflow-dashboard:kylin-xxx (10min)
Step 3: dockerFrontend/Dockerfile-base.kylin → frontend:kylin-base (10min)
Step 4: K8s YAML 更新              → 部署到测试集群
Step 5: 功能验证                   → 冒烟测试
```

### 12.3 验证测试

| 测试项 | 方法 | 通过标准 |
|--------|------|----------|
| 容器启动 | `docker run -it --rm <image> bash` | 进入 bash 无报错 |
| Python 版本 | `python --version` | Python 3.9.x |
| Node 版本 | `node --version` | ≥ v16.0.0 |
| pip 依赖 | `pip list \| wc -l` | 所有 requirements.txt 包已安装 |
| kubectl | `kubectl version --client` | 正常输出版本 |
| Supervisor | `supervisord -v` | 正常输出版本 |
| 中文字体 | `fc-list :lang=zh` | 输出中文字体列表 |
| Flask 启动 | `flask --app myapp:app run` | 监听 80 端口 |
| 前端构建 | `cd frontend && npm run build` | 构建成功 |

---

## 13. 实施计划

> **范围确认**：
> - ✅ x86_64 only（无需考虑 ARM/鲲鹏/飞腾）
> - ✅ 先 CPU 后 GPU（GPU 镜像后续单独评估，短期保留 ubuntu-gpu）
> - ✅ 先核心后模板（14 个 Job Template 后续按需迁移）

### Phase 1: 基础验证（0.5天）
- [ ] 拉取 `cube-studio/kylin:v10-sp3-2403` 到构建机器
- [ ] 交互式进入容器验证所有 yum 包可用性（第 4.3 节 V1-V9）
- [ ] 验证麒麟自带 Python 3.9 版本及 pip 可用性
- [ ] 确认 Node.js 版本，如不够则预下载 Node 16 二进制包
- [ ] 确认 yum 源中 nginx 版本

### Phase 2: 基础镜像构建（1-2天）
- [ ] 编写 `Dockerfile-base.kylin`
- [ ] 构建并修复编译错误（迭代）
- [ ] 验证 pip install -r requirements.txt 全部通过
- [ ] 验证 Supervisor、Node.js、kubectl

### Phase 3: 前端基础镜像（0.5天）
- [ ] 编写 `dockerFrontend/Dockerfile-base.kylin`（麒麟 + nginx）
- [ ] 构建并验证 nginx 启动
- [ ] 更新 `build_frontend.sh` 中的 `BASE_IMAGE`

### Phase 4: 后端生产镜像（0.5天）
- [ ] 编写 `Dockerfile.kylin`
- [ ] 构建并验证
- [ ] `STAGE=dev` 模式启动，验证 Flask 可访问

### Phase 5: K8s 部署验证（1-2天）
- [ ] 更新 YAML image 字段
- [ ] 部署到测试集群
- [ ] 冒烟测试：登录、创建任务、Notebook 启动
- [ ] Celery worker/schedule/watch 功能验证

### Phase 6: Notebook 镜像（已完成 hdfs/spark，可跳过或微调）
- [ ] 将 domestic-jupyter 成品镜像推送到生产 registry

### Phase 7: Config 更新 & 文档（0.5天）
- [ ] 更新 config.py（NOTEBOOK_IMAGES 增加 kylin 条目）
- [ ] 编写迁移文档和回滚方案

---

## 14. 待澄清问题（已确认 ✅ / 待确认 ❓）

| # | 问题 | 状态 | 结论 |
|---|------|------|------|
| 1 | 前端基座镜像来源？ | ✅ **已确认** | nginx 预构建镜像，需新建 `Dockerfile-base.kylin`（麒麟 + `yum install nginx`），见第 6 节 |
| 2 | 离线 yum 源？ | ❓ **待确认** | 构建机器是否能访问内部 yum 源？还是完全离线（所有 RPM 需预下载）？ |
| 3 | GPU 镜像策略？ | ✅ **已确认** | 先 CPU 后 GPU，GPU 镜像后续单独评估，短期保留 `ubuntu-gpu` |
| 4 | Python 安装方式？ | ✅ **已确认** | 麒麟自带 Python 3.9，直接用系统 Python + yum 安装 `python39-devel python39-pip`，无需 Miniconda |
| 5 | ARM 架构？ | ✅ **已确认** | 仅 x86_64，无需考虑 ARM |
| 6 | Job Template 优先级？ | ✅ **已确认** | 先聚焦平台核心服务（后端/前端/schedule/worker/watch），14 个模板后续按需迁移 |

---

## 15. 参考文件索引

| 文件 | 用途 |
|------|------|
| `install/docker/Dockerfile-base` | 原 Ubuntu 基础镜像（60行） |
| `install/docker/Dockerfile` | 原 Ubuntu 后端生产镜像（52行） |
| `install/docker/requirements.txt` | Python 依赖清单（65个包） |
| `install/docker/config.py` | 平台配置（NOTEBOOK_IMAGES 等） |
| `install/docker/entrypoint.sh` | 容器启动脚本 |
| `install/kubernetes/cube/base/*.yaml` | K8s 部署清单 |
| `domestic-jupyter/Dockerfile.hdfs` | ★ 麒麟 Jupyter HDFS 版（成功案例） |
| `domestic-jupyter/Dockerfile.spark` | ★ 麒麟 Jupyter Spark 版（成功案例） |
| `install/docker/notebook-hdfs-build/Dockerfile` | 原 Ubuntu Jupyter 构建文件 |
| `job-template/job/*/Dockerfile` | 14 个训练模板 Dockerfile |

---

> **下一步**：评审本方案，澄清第 14 节中的待澄清问题，确认后进入 **Phase 2: Implementation Planning**。
