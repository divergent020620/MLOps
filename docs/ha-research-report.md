# Cube Studio 高可用（HA）调研报告

> 调研日期：2026-07-17
> 调研范围：前端 → 后端 → Worker → Schedule → Watch 全链路
> 结论先行：**前端和 Backend 做 HA 门槛很低，Worker 天然支持，Schedule 和 Watch 需要特殊处理。**

---

## 零、前言：Cube Studio 前端架构特性

在讨论 HA 之前，先明确几个对 HA 至关重要的架构事实：

### 0.1 三个前端 SPA + 一个静态应用

Cube Studio 有 **4 个独立的前端应用**，通过不同方式服务：

| 应用 | 路径 | 路由模式 | 嵌入方式 |
|------|------|---------|---------|
| **主前端** | `myapp/frontend/` | BrowserRouter (`basename=/frontend/`) | 直接访问 `/frontend/` |
| **Vision Pipeline Editor** | `myapp/vision/` | HashRouter | iframe 嵌入到主前端 |
| **VisionPlus ETL Editor** | `myapp/visionPlus/` | HashRouter | iframe 嵌入到主前端 |
| **ChatGPT Web** | `myapp/chatgpt-web/` | - | 静态文件 |

其中 Vision 和 VisionPlus 通过 `IframeTemplate.tsx` 以 `<iframe>` 方式嵌入主前端，URL 指向后端 Flask 的静态文件路径：`/static/appbuilder/vison/index.html` 和 `/static/appbuilder/visonPlus/index.html`。

**HA 影响：** iframe 内的页面与主页面同源（same-origin），Cookie 自然共享，无需特殊处理。

### 0.2 无 WebSocket — 全部是 HTTP REST + 轮询

- SocketIO/WebSocket 在服务端**全部注释掉**（`myapp/__init__.py:144`、`myapp/views/view_k8s.py:66-100`）
- 实时数据通过 **HTTP 轮询** 实现：DataSearch 每 5 秒轮询、HDFS Download 每 2 秒轮询
- **不需要粘性会话（Sticky Session）**，K8s Service 默认 round-robin 完全适用

### 0.3 Cookie 认证 — 天然跨 Pod 工作

- 认证使用 `myapp_username` Cookie + Flask Session（签名 Cookie）
- 前端 axios 拦截器检查 Cookie 是否存在，无则跳转登录
- 401 响应自动触发重新登录
- SECRET_KEY 在两个 config.py 中一致 → 任意 Backend Pod 都能解密 Session
- `COOKIE_DOMAIN` 配置项支持跨子域共享

### 0.4 所有 API 调用使用相对路径

- 前端 axios 实例**不设置 `baseURL`**，所有请求用相对路径（如 `/myapp/menu`、`/pipeline_modelview/api/`）
- API 请求的目标是 `window.location.origin`（即用户访问的同一个域名）
- 这意味着前端本身不存在"连接哪个后端"的问题 — DNS/LB 决定流量到哪个 Pod

### 0.5 健康检查端点

三个端点都在 `myapp/views/route.py` 中定义：
- `/health` — 已在 auth 豁免列表中 ✅ **用于 K8s 探针**
- `/healthcheck` — 未在豁免列表 ❌
- `/ping` — 未在豁免列表 ❌

---

## 一、当前架构概览

### 1.1 完整流量链路

```
  外部流量
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  Istio Gateway (kubeflow/kubeflow-gateway, port 80)      │
│  selector: istio=ingressgateway                          │
│  hosts: "*"                                              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Istio VirtualService (infra-kubeflow-dashboard)         │
│  路由: * → kubeflow-dashboard-frontend.infra:80          │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │  (备选: Nginx Ingress       │
          │   infra-kubeflow-dashboard  │
          │   直接→backend Service)      │
          └─────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  kubeflow-dashboard-frontend Service (ClusterIP:80)      │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Nginx Pod (1 replica)                            │   │
│  │  - 静态文件: /frontend/ → /data/web/frontend/     │   │
│  │  - API 代理: / → http://kubeflow-dashboard.infra/ │   │
│  │  - WebSocket 穿透头已配置（SocketIO 已注释）        │   │
│  │  - 无探针、无 HPA、无 PDB                          │   │
│  └──────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────┘
                         │ proxy_pass
                         ▼
┌─────────────────────────────────────────────────────────┐
│  kubeflow-dashboard Service (ClusterIP:80)               │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Gunicorn + Flask Pod (1 replica)                 │   │
│  │  - 20 gevent workers, privileged 容器              │   │
│  │  - /health 探针 (liveness + readiness)            │   │
│  │  - 无 HPA、无 PDB                                  │   │
│  └──────────────────┬───────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────┘
                      │
      ┌───────────────┼────────────────┐
      │               │                │
      ▼               ▼                ▼
┌──────────┐  ┌────────────┐  ┌──────────────┐
│  Redis   │  │   MySQL    │  │  PVC         │
│  master  │  │  单节点     │  │  infra-      │
│  单节点   │  │  192.168.. │  │  kubeflow    │
└──────────┘  └────────────┘  │  (RWO?)      │
                              └──────────────┘

┌────────────────┐ ┌──────────────────┐ ┌─────────────────────┐
│ Worker (1 pod) │ │ Schedule (1 pod) │ │ Watch (1 pod)       │
│ celery worker  │ │ celery beat      │ │ supervisord 管理:    │
│ prefork/20并发  │ │ 定时任务调度      │ │ - watch_workflow.py │
│ 无探针          │ │ readiness 探针   │ │ - watch_service.py  │
└────────────────┘ └──────────────────┘ └─────────────────────┘
```

### 1.2 关键发现

- **所有组件均为 1 个副本**，任何 Pod 故障都会导致服务中断
- **流量入口有两套方案**：Istio VirtualService（主）+ Nginx Ingress（备）
- **Istio VirtualService** `infra-kubeflow-dashboard` 将全部流量路由到 `kubeflow-dashboard-frontend.infra.svc.cluster.local:80`
- **Nginx Ingress** `infra-kubeflow-dashboard` 直接路由到后端 `kubeflow-dashboard` Service（绕过前端 Pod），带 CORS 和 script 注入
- **SocketIO/WebSocket 已注释掉**，无实时连接需求，无需粘性会话
- **Istio Gateway** 监听在 `istio=ingressgateway` 的 Pod 上，本身可以多副本

---

## 二、各组件 HA 可行性分析

### 2.1 前端 Nginx — 难度：★☆☆☆☆（极易）

**当前状态：**
- `replicas: 1`，无探针，无 HPA
- Nginx 纯静态文件服务 + 反向代理，完全无状态

**HA 障碍：无**

Nginx 容器内做的事：
1. 服务 `/data/web/frontend/` 下的静态文件（React 构建产物）
2. 将 `/` 的请求 proxy_pass 到 `http://kubeflow-dashboard.infra/`

两者都不依赖本地状态，直接增加副本数即可。K8s Service 自带的 iptables/ipvs 负载均衡会自动在多个 Pod 之间分发请求。

**现有流量入口 (Istio) 已支持多副本：**
- Istio Gateway + VirtualService 是主要的流量入口
- Istio Gateway 通过 selector `istio=ingressgateway` 选择 Pod，ingressgateway 本身可配置多副本
- VirtualService 路由到 K8s Service（非直接到 Pod），Service 自动负载均衡
- **Istio 自带**：重试、超时、熔断、故障注入、流量镜像等高级 HA 能力

**HA 改造方案：**

```yaml
# 最小改动
spec:
  replicas: 2  # 从 1 改为 2

# 推荐改动
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # 滚动更新时不中断服务
  template:
    spec:
      # Pod 反亲和：尽量分布到不同节点
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: kubeflow-dashboard-frontend
              topologyKey: kubernetes.io/hostname
      containers:
      - name: kubeflow-dashboard-frontend
        # 添加健康探针
        livenessProbe:
          httpGet:
            path: /frontend/
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /frontend/
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
```

**负载均衡方式对比：**

| 方案 | 适用场景 | 复杂度 | 是否需要额外组件 |
|------|---------|--------|-----------------|
| **K8s Service ClusterIP + Istio（当前方案）** | 已有 Istio，自动获得 L7 路由 | 零（已部署） | 否 |
| K8s Service ClusterIP（默认） | 集群内部直接访问 | 零 | 否 |
| K8s Service + NodePort | 无 Ingress 的外部访问 | 低 | 否 |
| Nginx Ingress Controller | 需要统一域名、TLS、多服务路由 | 中 | 是 |
| 外部 LB（云厂商/硬件） | 生产环境推荐，TLS 终结 | 取决于基础设施 | 是 |

**推荐：保持现有 Istio 方案**。当前 `Istio Gateway → VirtualService → K8s Service → Nginx Pods` 的链路已经是最佳实践。只需要：
1. 增加 Nginx Pod 副本数
2. 确保 Istio ingressgateway 也是多副本（`kubectl get deploy -n istio-system istio-ingressgateway`）

---

### 2.2 Backend Flask/Gunicorn — 难度：★★☆☆☆（较易）

**当前状态：**
- `replicas: 1`，有 `/health` 探针，无 HPA
- Gunicorn 20 gevent workers，单 Pod 内已有多进程

**HA 障碍分析：**

| 障碍 | 状态 | 说明 |
|------|------|------|
| Session 共享 | ✅ 无问题 | Flask 使用签名 Cookie（`SECRET_KEY` 签名），不存服务端。两个 config.py 中的 `SECRET_KEY` 相同，无需额外处理 |
| WebSocket 粘性会话 | ✅ 无问题 | SocketIO 已注释掉（`myapp/__init__.py:144-147`），当前无 WebSocket |
| Cache 共享 | ✅ 无问题 | 使用 Redis 缓存（`CACHE_CONFIG.CACHE_TYPE: redis`），天然跨 Pod |
| Celery 任务分发 | ✅ 无问题 | 通过 Redis broker，与 Backend Pod 无关 |
| 数据库连接池 | ⚠️ 需调整 | 多 Pod 叠加连接池会增大 MySQL 压力。当前 `POOL_SIZE=300, MAX_OVERFLOW=800`，如果 3 个 Backend Pod 就是 900~3300 连接。需按比例缩小或保持不变 |
| X-Forwarded-For | ⚠️ 需关注 | 当前 `ENABLE_PROXY_FIX = False`，多级代理时需要开启以正确获取客户端 IP |
| PVC 共享 | ⚠️ 需验证 | Backend 挂载了 `infra-kubeflow` PVC (`ReadWriteOnce`)，如果 PVC 不支持 `ReadWriteMany`，多 Pod 调度到不同节点会挂载失败 |

**HA 改造方案：**

```yaml
# 关键改动
spec:
  replicas: 2  # 改为 2+

  template:
    spec:
      # ⚠️ CRITICAL: PVC ReadWriteOnce 问题
      # 如果 infra-kubeflow 是 RWO，要么：
      # 方案A: 改为 ReadWriteMany 存储（如 NFS/CephFS）
      # 方案B: 所有 Backend Pod 强制调度到同一节点（不推荐）
      # 方案C: 使用 topologySpreadConstraints 限制

      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: kubeflow-dashboard
              topologyKey: kubernetes.io/hostname

      containers:
      - name: kubeflow-dashboard
        env:
        # 如需多级代理，开启此配置
        # 在 config.py 中设置 ENABLE_PROXY_FIX = True
```

**Config.py 需改动的配置：**

```python
# 如果前端 Nginx 和 K8s Service 都在代理，建议开启
ENABLE_PROXY_FIX = True

# 数据库连接池 — 如果 3 副本，建议缩小
SQLALCHEMY_POOL_SIZE = 100   # 原来 300
SQLALCHEMY_MAX_OVERFLOW = 300  # 原来 800

# Session — 确保所有 Pod 用相同的 Key（已满足）
SECRET_KEY = "\2\1thisismyscretkey\1\2\e\y\y\h"
```

---

### 2.3 Celery Worker — 难度：★☆☆☆☆（极易）

**当前状态：**
- `replicas: 1`
- Celery worker prefork 模式，`-c 20`（20 并发进程）
- 注释掉的 liveness probe

**HA 障碍：无**

Celery Workers 天生支持水平扩展。多个 Worker Pod 从同一个 Redis broker 取任务，Celery 自带任务确认机制（`task_acks_late=True`），即使一个 Worker 宕机，任务会被重新分发给其他 Worker。

**HA 改造方案：**

```yaml
spec:
  replicas: 2  # 增加副本

  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: kubeflow-dashboard-worker
              topologyKey: kubernetes.io/hostname

      containers:
      - name: kubeflow-dashboard-worker
        # 取消注释并改进 liveness probe
        livenessProbe:
          exec:
            command:
            - bash
            - -c
            - celery -A myapp.tasks.celery_app:celery_app inspect ping -d celery@$HOSTNAME 2>/dev/null || exit 1
          initialDelaySeconds: 120
          periodSeconds: 60
          timeoutSeconds: 30
          failureThreshold: 3
```

**注意事项：**
- 当前配置 `worker_max_tasks_per_child = 12000`：每个 worker 进程执行 12000 个任务后自动重启，防止内存泄漏。这是 Celery 推荐实践，无需改动。
- `worker_prefetch_multiplier = 10`：每个 worker 预取 10 个任务。多 Pod 时自动均衡。

---

### 2.4 Celery Beat (Schedule) — 难度：★★★☆☆（需特殊处理）

**当前状态：**
- `replicas: 1`
- Celery beat 单实例运行定时任务调度（crontab 定时器）
- readiness 探针：`check_celery.py`

**HA 障碍：Celery Beat 必须单实例！**

如果运行多个 Celery Beat Pod，会导致：
- 同一个定时任务被多次触发
- 数据库中出现重复的 workflow 调度
- 例如 `task_make_timerun_config`（每 5 分钟）会被执行 N 次

**HA 改造方案：**

| 方案 | 原理 | 复杂度 | 推荐 |
|------|------|--------|------|
| **A. K8s Leader Election**（推荐） | 用 K8s Lease 实现选主，只有 Leader 运行 Beat | 中 | ⭐⭐⭐ |
| **B. RedBeat** | Celery Beat 的 Redis 锁实现，需要额外依赖 | 低 | ⭐⭐ |
| **C. 单副本 + PDB** | 保持 1 副本，加 PDB 保证不误驱逐 | 低 | ⭐ |
| **D. celery-singleton** | 每个任务用 Redis 锁去重 | 低 | ⭐ |

**方案 A（推荐）：K8s 原生 Leader Election**

```yaml
# 使用 Kubernetes Python client 的 leaderelection
# 在 entrypoint.sh 启动 celery beat 前加选主逻辑
# 或者使用 sidecar 容器实现选主
```

或者更简单的方式：

```yaml
# 使用 k8s Lease 资源 + initContainer
# 如果不想改代码，最简单的做法是：
spec:
  replicas: 1  # 保持 1

  # 添加 PDB 防止维护时被意外驱逐
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kubeflow-dashboard-schedule-pdb
  namespace: infra
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: kubeflow-dashboard-schedule
```

**方案 B：RedBeat（推荐，最简单）**

```python
# 在 config.py 的 CeleryConfig 中添加
from redbeat import RedBeatScheduler

class CeleryConfig(object):
    # ... 现有配置 ...
    redbeat_redis_url = 'redis://...'  # 使用 Redis 锁
    beat_scheduler = 'redbeat.RedBeatScheduler'
```

```
# requirements.txt 添加
celery-redbeat==2.0.0
```

---

### 2.5 Watch — 难度：★★☆☆☆（需特殊处理）

**当前状态：**
- `replicas: 1`，supervisord 管理 2 个 watcher 进程
- `watch_workflow.py`：监听 K8s Workflow CRD 变化，推送微信消息
- `watch_service.py`：监听 Service Pod 状态变化，推送消息
- liveness probe：每天凌晨 3 点重启

**HA 障碍：多 Pod 会导致重复推送通知！**

两个 watcher 都使用 K8s Watch API 监听资源变化。如果多个 Pod 运行：
- 同一个 Pod 重启事件会被多个 watcher 捕捉
- 用户收到重复的微信/通知消息
- 但不会造成数据错误（只读监听，不写数据）

**HA 改造方案：**

| 方案 | 原理 | 复杂度 |
|------|------|--------|
| **A. 分区 Watch** | 按 cluster 分片，每个 Pod 只 watch 特定集群 | 低 |
| **B. Redis 锁去重** | 推送前用 Redis 锁检查是否已推送 | 中 |
| **C. K8s Leader Election** | 同 Schedule，只有 Leader 运行 watch | 中 |
| **D. 职责分离** | watch_workflow 和 watch_service 拆分到不同 Pod | 低 |

**方案 A + D（推荐组合）：**

```yaml
# 将 watch_workflow 和 watch_service 拆分
# 各自独立部署，每类保持 1 个副本
# 如果将来需要多集群，watch_workflow 可以按集群分片

# deploy-watch-workflow.yaml
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: watch-workflow
        command: ["python", "myapp/tools/watch_workflow.py"]

# deploy-watch-service.yaml
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: watch-service
        command: ["python", "myapp/tools/watch_service.py"]
```

---

## 三、Cube Studio 自身 HA 功能评估

**结论：Cube Studio 当前没有自带的 HA 功能。**

经过全面代码审查：

| 功能 | 是否存在 | 位置/说明 |
|------|---------|----------|
| 多副本部署 | ❌ | 所有 deployment 的 `replicas: 1` |
| PodDisruptionBudget | ❌ | 无 |
| HorizontalPodAutoscaler | ❌ | 无 |
| Pod 反亲和性 | ❌ | 只有 nodeAffinity（固定到某类节点） |
| Leader Election | ❌ | 无 |
| 健康探针 | ⚠️ 部分 | Backend 有 `/health`；Schedule 有 readiness；Worker 和 Frontend 无 |
| 优雅关闭 | ⚠️ 部分 | Gunicorn 有，Celery 有 `task_acks_late` |
| Redis 高可用 | ❌ | 使用单节点 Redis（`redis-master.infra`） |
| MySQL 高可用 | ❌ | 单节点 MySQL |

**但 Cube Studio 的架构设计天然支持水平扩展：**
1. 无 WebSocket（SocketIO 已注释），无粘性会话需求
2. Flask 使用签名 Cookie，无服务端 Session
3. Redis 作为中间件解耦了 Backend 和 Worker
4. Celery 天然支持多 Worker

---

## 四、K8s 原生 HA 策略适配性

### 4.1 K8s Service 负载均衡

✅ **完全适用。** Cube Studio 的 Service 定义已经是 ClusterIP 模式：

```yaml
# kubeflow-dashboard-frontend Service (已存在)
spec:
  ports:
  - port: 80
    targetPort: 80
  selector:
    app: kubeflow-dashboard-frontend
```

当 `replicas: N` (N>1) 时，K8s 自动在 N 个 Pod 之间做 L4 负载均衡：
- **iptables 模式**：随机选择（默认）
- **ipvs 模式**：支持 rr/wrr/lc/wlc 等算法（配置中 `K8S_NETWORK_MODE = 'iptables'` 可改为 `ipvs`）

### 4.2 K8s HPA（水平自动伸缩）

✅ **完全适用。** 可以对 Frontend 和 Backend 创建 HPA：

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kubeflow-dashboard-frontend-hpa
  namespace: infra
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kubeflow-dashboard-frontend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 4.3 K8s PodDisruptionBudget

✅ **完全适用。** 保证主动驱逐时（节点维护等）最少可用 Pod 数：

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kubeflow-dashboard-pdb
  namespace: infra
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: kubeflow-dashboard
```

### 4.4 K8s TopologySpreadConstraints

✅ **完全适用。** 比 podAntiAffinity 更灵活地控制 Pod 分布：

```yaml
spec:
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: kubeflow-dashboard-frontend
```

### 4.5 kube-nginx / Nginx Ingress Controller

✅ **完全适用。** 如果外部流量通过 Ingress 进入，可以使用：
- **Nginx Ingress Controller**：提供 L7 负载均衡、TLS 终结、路径重写
- **kube-nginx**：如果用的是集群内部的 nginx 代理

当前架构中，前端 Nginx Pod 已经做了反向代理。如果用 Ingress 代替，可以减少一层代理。

---

## 五、推荐 HA 实施方案（分级）

### 第一阶段：最小可行 HA（1-2 天）

**改动范围：仅 YAML 配置**

| 组件 | 改动 | 副本数 |
|------|------|--------|
| Frontend | replicas: 2, 加探针, 加 podAntiAffinity | 2 |
| Backend | replicas: 2, 加 podAntiAffinity, 减小 DB 连接池 | 2 |
| Worker | replicas: 2, 加探针 | 2 |
| Schedule | 加 PDB, 保持 1 副本 | 1 |
| Watch | 拆分 workflow/service，加 PDB | 1+1 |

**PVC 问题需优先解决：**
```bash
# 检查 PVC 的 accessModes
kubectl get pvc infra-kubeflow -n infra -o yaml | grep accessModes
# 如果是 ReadWriteOnce，需要：
# 1. 改为 ReadWriteMany 存储类
# 2. 或所有 Backend Pod 调度到同一节点（使用 requiredDuringScheduling podAffinity）
```

### 第二阶段：生产级 HA（1 周）

在阶段一基础上：

| 新增项目 | 说明 |
|---------|------|
| HPA (Frontend + Backend + Worker) | 基于 CPU/Memory 自动伸缩 |
| Ingress 统一入口 | 替代前端 Nginx Service |
| Redis Sentinel/Cluster | Redis 自身高可用 |
| MySQL 主从/集群 | 数据库高可用 |
| RedBeat (Schedule) | Celery Beat 高可用 |
| Watch 按集群分片 | 去重通知 |

### 第三阶段：金融级 HA（按需）

| 新增项目 | 说明 |
|---------|------|
| 多集群部署 + 全局负载均衡 | 跨 AZ/Region |
| Istio Service Mesh | 灰度发布、熔断、限流 |
| 分布式链路追踪 | Jaeger/Zipkin |
| 混沌工程测试 | 验证 HA 有效性 |

---

## 六、具体配置文件改动（第一阶段）

### 6.1 deploy-frontend.yaml 改动

```yaml
# 改动 1: replicas
spec:
  replicas: 2  # 原来是 1

# 改动 2: 添加 podAntiAffinity
spec:
  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: kubeflow-dashboard-frontend
              topologyKey: kubernetes.io/hostname
        # 保留原有 nodeAffinity
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: kubeflow-dashboard
                operator: In
                values:
                - "true"

# 改动 3: 添加探针
      containers:
      - name: kubeflow-dashboard-frontend
        livenessProbe:
          httpGet:
            path: /frontend/
            port: 80
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /frontend/
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
```

### 6.2 deploy-backend.yaml 改动

```yaml
spec:
  replicas: 2  # 原来是 1

  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: kubeflow-dashboard
              topologyKey: kubernetes.io/hostname
        # 保留原有 nodeAffinity
```

### 6.3 config.py 改动

```python
# 开启代理头解析
ENABLE_PROXY_FIX = True  # 原来是 False

# 如果多 Backend Pod，按比例缩小连接池
SQLALCHEMY_POOL_SIZE = 100     # 原来是 300（按 N=3 副本计算）
SQLALCHEMY_MAX_OVERFLOW = 300  # 原来是 800
```

### 6.4 新增 HPA（可选）

```yaml
# 保存为 install/kubernetes/cube/base/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kubeflow-dashboard-frontend-hpa
  namespace: infra
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kubeflow-dashboard-frontend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kubeflow-dashboard-hpa
  namespace: infra
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kubeflow-dashboard
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kubeflow-dashboard-worker-hpa
  namespace: infra
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kubeflow-dashboard-worker
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 6.5 新增 PDB（推荐）

```yaml
# 保存为 install/kubernetes/cube/base/pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kubeflow-dashboard-frontend-pdb
  namespace: infra
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: kubeflow-dashboard-frontend
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kubeflow-dashboard-pdb
  namespace: infra
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: kubeflow-dashboard
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: kubeflow-dashboard-schedule-pdb
  namespace: infra
spec:
  maxUnavailable: 0  # Celery Beat 绝不能中断
  selector:
    matchLabels:
      app: kubeflow-dashboard-schedule
```

---

## 七、关键风险与待确认项

| # | 风险项 | 影响组件 | 优先级 | 确认方式 |
|---|--------|---------|--------|---------|
| 1 | **PVC `infra-kubeflow` 的 accessMode** | Backend | 🔴 高 | `kubectl get pvc -n infra infra-kubeflow` |
| 2 | Redis 单点（`redis-master.infra`） | Backend + Worker + Schedule | 🟡 中 | 检查 Redis 是否有备节点 |
| 3 | MySQL 单点（`192.168.11.15:3306`） | Backend | 🟡 中 | 检查 MySQL 是否有主从 |
| 4 | `SECRET_KEY` 一致性 | Backend | 🟢 已确认 | 两个 config.py 中 `SECRET_KEY` 一致 |
| 5 | 定时任务幂等性（多 Beat 风险） | Schedule | 🟡 中 | 审查每个 crontab 任务是否幂等 |
| 6 | Watch 去重推送 | Watch | 🟢 低 | 当前为"用户体验"影响，非功能影响 |

---

## 八、总结

1. **前端 HA 用 K8s 原生策略完全可行** — 增加副本 + Service 负载均衡即可，无需引入额外组件
2. **Cube Studio 没有自带的 HA 功能** — 但架构设计（签名 Cookie + Redis + Celery）天然支持水平扩展
3. **kube-nginx / Ingress 是可选的增强方案** — 当前 K8s Service 已经足够；Ingress 更适合需要统一域名/TLS/灰度发布的场景
4. **最大阻塞点：PVC `infra-kubeflow` 的 accessMode** — 如果是 RWO，需要先解决存储共享问题
5. **推荐分阶段实施** — 先从前端 2 副本开始（零风险），验证后再扩展 Backend 和 Worker
