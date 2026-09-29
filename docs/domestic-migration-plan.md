# Cube Studio 国产化迁移 — 实施计划

> **Superpowers Phase 3: Implementation Planning**
> 基于: `docs/domestic-migration-design.md`
> 日期: 2026-07-30
> 范围: x86_64 only | CPU only | 核心服务 only

---

## 构建顺序与依赖

```
联网环境（有外网）:
  T1: Dockerfile-base.kylin         ← ★ 所有联网操作（yum/pip/wget）
  T3: dockerFrontend/Dockerfile-base.kylin ← yum install nginx

离线环境（纯内网）:
  T2: Dockerfile.kylin              ← 纯 COPY，零联网
  T4: build_frontend.sh             ← 纯 COPY 前端产物

配置更新（不依赖构建）:
  T5: config.py
  T6: K8s YAML
```

> **关键原则**：联网操作 100% 收敛到 base 镜像中，生产镜像只做 COPY。两个网络各构建一次即可。

---

## T0: 环境验证（构建机器上执行）

### T0.1 确认麒麟基座可用

```bash
docker images | grep kylin
# 预期: cube-studio/kylin  v10-sp3-2403  ...
```

### T0.2 验证 Python 版本

```bash
docker run --rm cube-studio/kylin:v10-sp3-2403 python3 --version
# 预期: Python 3.9.x
```

### T0.3 验证关键 yum 包

```bash
docker run --rm cube-studio/kylin:v10-sp3-2403 bash -c "
  echo '=== nodejs ===' && yum info nodejs 2>/dev/null | grep -E '^Version|^Release'
  echo '=== nginx ===' && yum info nginx 2>/dev/null | grep -E '^Version|^Release'
  echo '=== gcc ===' && yum info gcc 2>/dev/null | grep -E '^Version|^Release'
  echo '=== mariadb ===' && yum info mariadb 2>/dev/null | grep -E '^Version|^Release'
"
```

**判定**: Node.js ≥ 16 则走 yum 路线；< 16 则需二进制包方案（见 T1-fallback）。

---

## T1: Dockerfile-base.kylin（联网环境构建 — 所有下载操作集中在此）

**文件**: `install/docker/Dockerfile-base.kylin`（新建）
**构建网络**: 有外网（或能访问 yum 源 + OSS + pypi 镜像）
**产物**: `192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin`

### T1.1 完整 Dockerfile

```dockerfile
# ============================================================================
# Cube Studio — 麒麟信创 后端基础镜像
# ★ 此 Dockerfile 包含所有联网操作（yum/pip/wget）
# ★ 构建在联网环境执行一次，产物镜像 push 到内网 registry
# ★ 后续 Dockerfile.kylin 只做 COPY，无需联网
#
# 构建:
#   docker build --network=host \
#     -t 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin \
#     -f install/docker/Dockerfile-base.kylin .
#   docker push 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin
# ============================================================================

FROM cube-studio/kylin:v10-sp3-2403

ENV TZ=Asia/Shanghai
ENV LANG=zh_CN.UTF-8
ENV LC_ALL=zh_CN.UTF-8
ENV LANGUAGE=zh_CN.UTF-8

# ═══════════════════════════════════════════════════════════════
# 以下全部是联网操作，离线构建不需要执行这一层
# ═══════════════════════════════════════════════════════════════

# ── 1. 系统依赖（yum install）────────────────────────────────
# ★ gcc/gcc-c++/make — 麒麟缺少编译环境（domestic-jupyter 已验证）
RUN yum install -y --nogpgcheck \
        # 编译工具（麒麟缺少）
        gcc gcc-c++ make \
        # Python 3.9 + 开发头文件
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
        # SASL（pyhive/thrift-sasl 编译依赖）
        cyrus-sasl-devel cyrus-sasl \
        # PostgreSQL（psycopg2 编译依赖）
        libpq-devel \
        # Python C 扩展编译依赖（cryptography/cffi/gevent/gmssl）
        openssl-devel libffi-devel libev-devel \
        bzip2-devel zlib-devel \
        # Node.js
        nodejs npm \
        # Kerberos（HDFS 认证）
        krb5-workstation krb5-libs krb5-devel \
        # 其他
        bzip2 iproute rsync \
    && yum clean all && rm -rf /var/cache/yum/*

# ── 2. Python 符号链接 ─────────────────────────────────────
RUN ln -sf /usr/bin/python3.9 /usr/bin/python && \
    ln -sf /usr/bin/python3.9 /usr/bin/python3 && \
    ln -sf /usr/bin/pip3.9 /usr/bin/pip && \
    ln -sf /usr/bin/pip3.9 /usr/bin/pip3

# ── 3. Supervisor（pip install）────────────────────────────
RUN pip3.9 install --no-cache-dir supervisor && \
    mkdir -p /var/log/supervisor

# ── 4. Python 依赖（pip install）───────────────────────────
# 包括 requirements.txt 全部 + HDFS 额外包
COPY install/docker/requirements.txt /requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /requirements.txt && \
    pip install --no-cache-dir \
        requests_kerberos krbcontext \
    && rm -rf /root/.cache/pip

# ── 5. kubectl（wget）──────────────────────────────────────
RUN wget -q https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl \
        -O /usr/local/bin/kubectl && \
    chmod +x /usr/local/bin/kubectl

# ── 6. AI Hub 模型市场数据（wget）──────────────────────────
RUN wget -q https://cube-studio.oss-cn-hangzhou.aliyuncs.com/aihub/deeplearning/aihub.zip && \
    mkdir -p /cube-studio/aihub && \
    unzip -q aihub.zip -d /cube-studio/aihub/ && \
    rm aihub.zip

# ═══════════════════════════════════════════════════════════════
# 联网操作到此结束。以下无网络访问
# ═══════════════════════════════════════════════════════════════

# ── 7. 便捷配置 ────────────────────────────────────────────
RUN echo "alias ll='ls -alF'" >> ~/.bashrc && \
    echo "alias la='ls -A'" >> ~/.bashrc && \
    echo "alias vi='vim'" >> ~/.bashrc

WORKDIR /home/myapp
USER root
EXPOSE 80
```

**验证步骤**:
```bash
# 构建
docker build --network=host \
  -t 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin \
  -f install/docker/Dockerfile-base.kylin .

# 验证基础环境
docker run --rm 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin \
  bash -c "
    echo '=== Python ===' && python --version && pip --version
    echo '=== Node ===' && node --version && npm --version
    echo '=== GCC ===' && gcc --version | head -1
    echo '=== Supervisor ===' && supervisord -v
    echo '=== kubectl ===' && kubectl version --client
    echo '=== Fonts ===' && fc-list :lang=zh | head -3
    echo '=== pip packages ===' && pip list | wc -l
    echo '=== aihub ===' && ls /cube-studio/aihub/ | head -3
    echo '=== HDFS pip ===' && pip list | grep -E 'hdfs|kerberos|krbcontext|pyarrow'
  "

# 推送到内网 registry（供离线环境使用）
docker push 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin
```

### T1-fallback: Node.js 版本不够时的替代方案

如果 T0.3 验证发现麒麟 yum 的 Node.js < 16：

```dockerfile
# 替代 Dockerfile-base.kylin 中 nodejs npm 这两行，改为二进制方式：
# （在 yum install 中去掉 nodejs npm，改为以下）

# Node.js 16 二进制包（需提前下载放到 packages/ 目录）
COPY install/docker/packages/node-v16.20.2-linux-x64.tar.xz /tmp/
RUN tar xf /tmp/node-v16.20.2-linux-x64.tar.xz -C /usr/local/ && \
    mv /usr/local/node-v16.20.2-linux-x64 /usr/local/node && \
    ln -sf /usr/local/node/bin/node /usr/bin/node && \
    ln -sf /usr/local/node/bin/npm /usr/bin/npm && \
    ln -sf /usr/local/node/bin/npx /usr/bin/npx && \
    rm /tmp/node-v16.20.2-linux-x64.tar.xz
```

---

## T2: Dockerfile.kylin（离线环境构建 — 纯 COPY，零联网）

**文件**: `install/docker/Dockerfile.kylin`（新建）
**构建网络**: 纯内网（仅需能拉取 base 镜像）
**前置**: T1 产物已推送到内网 registry
**产物**: `192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730`

### T2.1 完整 Dockerfile

```dockerfile
# ============================================================================
# Cube Studio — 麒麟信创 后端生产镜像
# ★ 零联网操作 — 所有下载已在 Dockerfile-base.kylin 中完成
# ★ 仅做 COPY + ENV + chmod
#
# 构建:
#   docker build --network=none \
#     -t 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730 \
#     -f install/docker/Dockerfile.kylin .
# ============================================================================

FROM 192.168.11.12/cube-studio/kubeflow-dashboard:base-python3.9-kylin

# ── 源码 ──────────────────────────────────────────────────
COPY myapp /home/myapp/myapp
COPY myapp/static/appbuilder/frontend /data/web/frontend

# ── AI Hub 模型数据（已预装在 base 镜像 /cube-studio/aihub/）
# 如果有本地更新，可以覆盖:
# COPY aihub /cube-studio/aihub

# ── HDFS Kerberos 认证文件 ────────────────────────────────
COPY ai_general.keytab /home/myapp/ai_general.keytab
COPY krb5.conf /etc/krb5.conf

# ── 环境变量 ──────────────────────────────────────────────
ENV PATH=/home/myapp/myapp/bin:${PATH:-}
ENV PYTHONPATH=/home/myapp:${PYTHONPATH:-}

# ── 启动脚本 ──────────────────────────────────────────────
COPY install/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /home/myapp/myapp/bin/myapp /entrypoint.sh
```

### T2.2 联网操作清单 — 已全部收敛到 T1

| 操作 | 原位置 (Dockerfile.kylin) | 现位置 (Dockerfile-base.kylin) |
|------|--------------------------|-------------------------------|
| `apt install krb5-user libkrb5-dev` | apt (Ubuntu) | yum krb5-workstation krb5-libs krb5-devel |
| `pip install hdfs requests_kerberos krbcontext pyarrow` | Dockerfile 内 pip | base 第4步（pip install 阶段） |
| `wget aihub.zip` | Dockerfile 内 wget | base 第6步 |
| `pip install -r requirements.txt` | 分散 | base 第4步 |

**结论**: `Dockerfile.kylin` 中没有 `pip install`、没有 `wget`、没有 `apt/yum`。100% COPY。

**验证步骤**:
```bash
# ★ 用 --network=none 构建，证明零联网
docker build --network=none \
  -t 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730 \
  -f install/docker/Dockerfile.kylin .

# 模拟 dev 模式启动
docker run --rm \
  -e STAGE=dev \
  192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730 \
  python -c "from myapp import app; print('Flask app loaded OK')"
```

---

## T3: dockerFrontend/Dockerfile-base.kylin（前端 nginx 基础镜像）

**文件**: `install/docker/dockerFrontend/Dockerfile-base.kylin`（新建）

### T3.1 创建文件

```dockerfile
# ============================================================================
# Cube Studio — 麒麟信创 前端 nginx 基础镜像
# 替代原 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:20260630v1
#
# 构建:
#   docker build --network=host \
#     -t 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-base \
#     -f install/docker/dockerFrontend/Dockerfile-base.kylin .
# ============================================================================

FROM cube-studio/kylin:v10-sp3-2403

ENV TZ=Asia/Shanghai
ENV LANG=zh_CN.UTF-8

# nginx — 麒麟 yum 源自带
RUN yum install -y --nogpgcheck nginx && \
    yum clean all && rm -rf /var/cache/yum/*

# nginx 配置（直接用现有文件）
COPY install/docker/dockerFrontend/nginx.conf /etc/nginx/nginx.conf
COPY install/docker/dockerFrontend/nginx.80.conf /etc/nginx/conf.d/default.conf

# 启动脚本
COPY install/docker/dockerFrontend/start.sh /start.sh
RUN chmod +x /start.sh

# 前端静态文件目录（构建时由 build_frontend.sh 的 Dockerfile 填充）
RUN mkdir -p /data/web/frontend

EXPOSE 80
CMD ["/start.sh"]
```

**验证步骤**:
```bash
# 构建
docker build --network=host \
  -t 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-base \
  -f install/docker/dockerFrontend/Dockerfile-base.kylin .

# 验证 nginx 可启动
docker run -d --rm --name test-nginx \
  192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-base
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:80
# 预期: 200 (nginx 默认页) 或 404 (无前端文件)
docker stop test-nginx
```

---

## T4: build_frontend.sh 更新

**文件**: `build_frontend.sh`（修改 1 行）

### T4.1 修改 BASE_IMAGE

**原行 12**:
```bash
BASE_IMAGE="192.168.11.12/cube-studio/kubeflow-dashboard-frontend:20260630v1"
```

**改为**:
```bash
BASE_IMAGE="192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-base"
```

**验证**: 执行 `bash build_frontend.sh <TAG>` 构建成功后 push 并部署。

---

## T5: config.py 更新

**文件**: `install/docker/config.py`（修改约第 744 行 NOTEBOOK_IMAGES 列表）

### T5.1 在 NOTEBOOK_IMAGES 列表首部插入麒麟镜像

找到 `NOTEBOOK_IMAGES` 列表（约第 744 行），在第一个元素前插入：

```python
NOTEBOOK_IMAGES=[
    # ★ 麒麟信创镜像
    ['192.168.11.12/cube-studio/notebook:jupyter-kylin-hdfs', 'jupyter-kylin（hdfs）'],
    ['192.168.11.12/cube-studio/notebook:jupyter-kylin-spark', 'jupyter-kylin（spark）'],
    # 以下为原 ubuntu 镜像（过渡期保留）
    ['192.168.11.12/cube-studio/notebook:vscode-ubuntu-cpu-base', 'vscode（cpu）'],
    ...
]
```

> **注意**: 麒麟 notebook 镜像来自 `domestic-jupyter/` 的成品，只需 push 到 192.168.11.12 registry 即可，无需重新构建。

### T5.2 确认 USER_IMAGE 保持不变

`USER_IMAGE`（约第 738 行）保留 ubuntu-gpu，GPU 场景后续单独评估：

```python
USER_IMAGE = '192.168.11.12/cube-studio/ubuntu-gpu:cuda11.8.0-cudnn8-python3.9'  # GPU 暂不国产化
```

**验证**: `python -c "from install.docker.config import NOTEBOOK_IMAGES; print(NOTEBOOK_IMAGES[:3])"`

---

## T6: K8s 部署 YAML 更新

**文件**: `install/kubernetes/cube/base/` 下的 5 个 Deployment YAML

### T6.1 deploy-backend.yaml

找到 `image:` 行，改为：
```yaml
image: 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730
```

### T6.2 deploy-schedule.yaml

同上，改为：
```yaml
image: 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730
```

### T6.3 deploy-worker.yaml

同上，改为：
```yaml
image: 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730
```

### T6.4 deploy-watch.yaml

同上，改为：
```yaml
image: 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730
```

### T6.5 deploy-frontend.yaml

找到 `image:` 行，改为：
```yaml
image: 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-20260730
```

**验证步骤**:
```bash
# 检查所有 image 引用一致
grep -h "image:" install/kubernetes/cube/base/deploy-*.yaml | sort -u
# 预期输出:
#   image: 192.168.11.12/cube-studio/busybox:1.36.0
#   image: 192.168.11.12/cube-studio/kubeflow-dashboard:kylin-20260730
#   image: 192.168.11.12/cube-studio/kubeflow-dashboard-frontend:kylin-20260730

# 部署
kubectl apply -f install/kubernetes/cube/base/

# 等待就绪
kubectl rollout status deployment/kubeflow-dashboard -n infra --timeout=120s
kubectl rollout status deployment/kubeflow-dashboard-frontend -n infra --timeout=60s
kubectl rollout status deployment/kubeflow-dashboard-schedule -n infra --timeout=60s
kubectl rollout status deployment/kubeflow-dashboard-worker -n infra --timeout=60s
kubectl rollout status deployment/kubeflow-dashboard-watch -n infra --timeout=60s
```

---

## T7: 冒烟测试清单

部署完成后执行：

| # | 测试项 | 操作 | 通过标准 |
|---|--------|------|----------|
| S1 | 平台登录 | 浏览器打开 frontend 地址 | 登录页正常显示，admin/admin 登录成功 |
| S2 | 首页仪表盘 | 登录后查看首页 | 数据正常加载，无 500 错误 |
| S3 | 训练任务创建 | 训练 → 任务模板 → 新建 | 页面正常，模板列表加载 |
| S4 | Notebook 创建 | 在线开发 → 新建 notebook | 可选镜像列表含 kylin 条目 |
| S5 | Pipeline 编辑 | 训练 → Pipeline → 新建 | Vision 编辑器正常加载 |
| S6 | 数据管理 | 数据管理 → 数据集 | 页面正常 |
| S7 | AI Hub | AI Hub 页面 | 模型列表加载 |
| S8 | Celery worker | `kubectl logs deploy/kubeflow-dashboard-worker -n infra --tail=20` | 无连接错误 |
| S9 | Celery beat | `kubectl logs deploy/kubeflow-dashboard-schedule -n infra --tail=20` | 定时任务正常调度 |
| S10 | 后端健康 | `curl http://backend:80/health` | 返回 200 |

---

## 回滚方案

如果 Kylin 镜像部署后出现问题：

```bash
# 1. 回滚 K8s deployment（假设原镜像 tag 已知）
kubectl set image deployment/kubeflow-dashboard -n infra \
  kubeflow-dashboard=192.168.11.12/cube-studio/kubeflow-dashboard:20260703
kubectl set image deployment/kubeflow-dashboard-schedule -n infra \
  kubeflow-dashboard=192.168.11.12/cube-studio/kubeflow-dashboard:20260703
kubectl set image deployment/kubeflow-dashboard-worker -n infra \
  kubeflow-dashboard=192.168.11.12/cube-studio/kubeflow-dashboard:20260703
kubectl set image deployment/kubeflow-dashboard-watch -n infra \
  kubeflow-dashboard=192.168.11.12/cube-studio/kubeflow-dashboard:2026070
kubectl set image deployment/kubeflow-dashboard-frontend -n infra \
  kubeflow-dashboard-frontend=192.168.11.12/cube-studio/kubeflow-dashboard-frontend:20260630v1

# 2. 等待 rollout
kubectl rollout status deployment -n infra --all --timeout=120s

# 3. 验证恢复
curl -s http://frontend-ip/ | head -5
```

---

## 任务汇总

### 联网环境（构建一次，推送到内网 registry）

| Task | 文件 | 操作 | 产物 |
|------|------|------|------|
| T0 | — | 环境验证 | 确认 kylin 镜像、Python/Node 版本 |
| T1 | `install/docker/Dockerfile-base.kylin` | **新建**（~100 行）→ build → push | `base-python3.9-kylin` |
| T3 | `install/docker/dockerFrontend/Dockerfile-base.kylin` | **新建**（~30 行）→ build → push | `frontend:kylin-base` |

### 离线环境（纯 COPY，`--network=none` 可构建）

| Task | 文件 | 操作 | 产物 |
|------|------|------|------|
| T2 | `install/docker/Dockerfile.kylin` | **新建**（~25 行）→ build | `kubeflow-dashboard:kylin-xxx` |
| T4 | `build_frontend.sh` | **修改 1 行** → bash build_frontend.sh | `frontend:kylin-xxx` |

### 配置更新（不依赖构建）

| Task | 文件 | 改动 |
|------|------|------|
| T5 | `install/docker/config.py` | NOTEBOOK_IMAGES 加 kylin 条目 |
| T6 | `install/kubernetes/cube/base/*.yaml` × 5 | 改 image tag |

### 联网操作 100% 收敛验证

| Dockerfile | yum | pip | wget | curl | 网络需求 |
|------------|-----|-----|------|------|----------|
| `Dockerfile-base.kylin` | ✅ | ✅ | ✅ | — | **需联网** |
| `Dockerfile.kylin` | — | — | — | — | **零联网** |
| `dockerFrontend/Dockerfile-base.kylin` | ✅ | — | — | — | **需联网** |
