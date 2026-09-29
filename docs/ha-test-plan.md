# Cube Studio 3 节点 HA 容灾测试方案

> 测试目标：3 个 master 节点（已有 label，可调度），任意停掉 1 台，用户完全无感知
> 测试标准：浏览器操作不出现 502/504/连接拒绝/白屏

---

## 一、当前问题：为什么停机 1 台用户就会感知

```
现状：所有 Deployment replicas=1

   node1          node2          node3
  ┌─────────┐   ┌─────────┐   ┌─────────┐
  │ frontend│   │         │   │         │
  │ backend │   │         │   │         │
  │ worker  │   │         │   │         │
  │ schedule│   │         │   │         │
  │ watch   │   │         │   │         │
  └─────────┘   └─────────┘   └─────────┘
       ↑
   停机 node1 → 全部 5 个 Pod 消失 → 服务全挂
```

**虽然 3 个节点都有 label，但 replicas=1 意味着只有 1 个 Pod，始终只占 1 个节点。**

## 二、需要的改动（5 个核心项 + 2 个增强项）

### 核心 1：前端 + 后端 replicas=2，加 podAntiAffinity

| 文件 | 改动 |
|------|------|
| `deploy-frontend.yaml` | replicas: 1→2, 加 `requiredDuringScheduling` podAntiAffinity, 加探针 |
| `deploy-backend.yaml` | replicas: 1→2, 加 `requiredDuringScheduling` podAntiAffinity, 加快探针周期 |

```yaml
# 关键配置：requiredDuringScheduling — 强制分布到不同节点，不能同节点
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          app: kubeflow-dashboard-frontend  # 或 kubeflow-dashboard
      topologyKey: kubernetes.io/hostname
```

效果：2 个 Pod 强制分布到 2 个不同节点，任意停 1 台至少剩 1 个。

### 核心 2：Istio IngressGateway 多副本

```bash
kubectl get deploy istio-ingressgateway -n istio-system
```

如果 replicas=1，扩容到 2+，同样加 podAntiAffinity。**入口本身就是单点的话，后面搞再多副本也没用。**

### 核心 3：前端加健康探针

当前前端 Deployment **完全没有探针**。停机时 K8s 不知道 Nginx 挂了，继续把流量往死的 Pod 发。

```yaml
livenessProbe:
  httpGet:
    path: /frontend/
    port: 80
  periodSeconds: 10        # 每 10s 检查
  failureThreshold: 2      # 连续 2 次失败 → 重启

readinessProbe:
  httpGet:
    path: /frontend/
    port: 80
  periodSeconds: 5         # 每 5s 检查
  failureThreshold: 2      # 连续 2 次失败 → 摘除流量
```

### 核心 4：后端探针提速

当前后端探针 `periodSeconds: 60` — 要等 60 秒才检测一次。节点突然宕机，K8s 要等 `node-monitor-grace-period`（默认 40s）+ 探针周期才能发现。

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: http
  periodSeconds: 5         # 原来是 60 ← 关键改动
  failureThreshold: 2

livenessProbe:
  httpGet:
    path: /health
    port: http
  periodSeconds: 10        # 原来是 60
  failureThreshold: 3
```

### 核心 5：Istio VirtualService 加重试

节点宕机瞬间，正在飞的请求会失败。Istio retry 自动把请求重试到另一个 Pod，用户无感知。

```yaml
# 修改 install/kubernetes/virtual.yaml 中的 infra-kubeflow-dashboard
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: infra-kubeflow-dashboard
  namespace: infra
spec:
  gateways:
  - kubeflow/kubeflow-gateway
  hosts:
  - "*"
  http:
  - retries:                              # ← 新增
      attempts: 2
      perTryTimeout: 30s
      retryOn: "5xx,reset,connect-failure,refused-stream,unavailable"
    timeout: 300s
    route:
    - destination:
        host: kubeflow-dashboard-frontend.infra.svc.cluster.local
        port:
          number: 80
```

### 增强 1（可选）：Worker 多副本

Worker 挂了不影响用户访问页面，只影响异步任务。如果测试要求严格，同样 replicas=2 + podAntiAffinity + 探针。

### 增强 2（可选）：PodDisruptionBudget

防止维护操作时误把所有 Pod 同时驱逐。

---

## 三、部署步骤

### Step 1：直接改 YAML 后 apply

```bash
cd install/kubernetes/cube/base

# 改 deploy-frontend.yaml: replicas=2, podAntiAffinity, 探针
# 改 deploy-backend.yaml: replicas=2, podAntiAffinity, 探针周期缩短
# （具体改动见上面第二节）

cd /bdm/share_bdm/cube-studio-master
kubectl apply -k install/kubernetes/cube/overlays
```

### Step 2：改 virtual.yaml 加重试

```bash
# 编辑 install/kubernetes/virtual.yaml，加 retries 配置
kubectl apply -f install/kubernetes/virtual.yaml
```

### Step 3：确认 IngressGateway 多副本

```bash
kubectl scale deploy istio-ingressgateway -n istio-system --replicas=2
```

验证 patch 反亲和：
```bash
kubectl patch deploy istio-ingressgateway -n istio-system -p '{
  "spec": {"template": {"spec": {"affinity": {
    "podAntiAffinity": {
      "requiredDuringSchedulingIgnoredDuringExecution": [{
        "labelSelector": {"matchLabels": {"istio": "ingressgateway"}},
        "topologyKey": "kubernetes.io/hostname"
      }]
    }
  }}}}
}'
```

### Step 4：验证分布

```bash
kubectl get pods -n infra -o wide -l app=kubeflow-dashboard-frontend
kubectl get pods -n infra -o wide -l app=kubeflow-dashboard
kubectl get pods -n istio-system -o wide -l istio=ingressgateway
```

预期：每个组件至少 2 个 Pod，且在不同节点的 HOSTNAME 上。

---

## 四、停机测试

### 持续监控（3 个终端）

```bash
# 终端 1：前端页面
while true; do
  curl -s -o /dev/null -w "frontend: %{http_code} %{time_total}s\n" http://192.168.11.11/frontend/
  sleep 0.5
done

# 终端 2：后端 API
while true; do
  curl -s -o /dev/null -w "backend: %{http_code} %{time_total}s\n" http://192.168.11.11/health
  sleep 0.5
done

# 终端 3：浏览器打开 http://192.168.11.11，登录，操作
```

### 测试步骤

```bash
# 1. 找到某个 Pod 所在的节点
NODE=$(kubectl get pod -n infra -l app=kubeflow-dashboard-frontend -o jsonpath='{.items[0].spec.nodeName}')
echo "将停机节点: $NODE"

# 2. 模拟节点宕机
ssh $NODE "sudo systemctl stop kubelet"
# 或者：在 K8s 层面 cordon + drain
# kubectl cordon $NODE
# kubectl drain $NODE --ignore-daemonsets --delete-emptydir-data --force

# 3. 观察 3 个终端：curl 输出不应出现 5xx 或 timeout

# 4. 恢复
ssh $NODE "sudo systemctl start kubelet"
kubectl uncordon $NODE
```

### 判断标准

| 指标 | 通过 | 失败 |
|------|------|------|
| HTTP 5xx | 0 个 | ≥1 个 |
| Connection refused/timeout | 0 个 | ≥1 个 |
| 浏览器页面 | 不白屏，操作可继续 | 白屏/报错 |
| 最大抖动 | < 3s（Istio retry 重连） | > 10s |

---

## 五、如果测试失败了

| 现象 | 原因 | 修法 |
|------|------|------|
| 出现 5xx | Istio 重试没生效或旧连接没重试 | 检查 `virtual.yaml` 的 retry 配置，确认 `retryOn` 包含了 `5xx` |
| 出现 Connection refused | K8s Service 还在路由流量到死 Pod | 加快 readiness probe period（3s），让 K8s 更快摘除端点 |
| 浏览器白屏 | 前端 Pod 全在停机的节点上 | 确认 podAntiAffinity 是 **required** 不是 preferred |
| 登录后跳转 | 请求被路由到未登录的 Backend Pod | 检查 SECRET_KEY 一致（已知一致），检查 Redis 缓存 |

---

## 六、不改的部分

| 组件 | 不改的原因 |
|------|-----------|
| Schedule (Celery Beat) | 挂了影响定时任务触发，不影响用户使用页面和 API |
| Watch | 挂了影响通知推送，不影响功能 |
| Redis | 如果 Redis 也是单节点，停机那台 Redis 也挂，但这是基础设施层的 HA，不在本次范围 |
| MySQL | 同上，外部数据库，假设已 HA |
