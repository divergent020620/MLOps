# Cube Studio 重启自恢复升级

> **范围限定：** 仅包含断电自启 / 服务依赖等待 / 持久化存储，不包含 HA（多副本 / VIP / MetalLB / 证书）。

---

## 一、升级内容

### 1.1 节点层 — 停电恢复自启动（P0）

每台节点执行一次：

```bash
bash restart/k8s-node-autostart.sh
```

效果：
- `systemctl enable docker containerd`
- `systemctl enable kubelet`
- Harbor 节点（10.240.125.39）容器设 `restart=always`

**停电恢复启动链：**
```
BIOS Power On → docker/containerd → kubelet → static pods(etcd,apiserver)
→ DaemonSet(flannel,kube-proxy) → mysql → redis → backend → worker → schedule → watch → frontend
```

### 1.2 应用层 — 启动依赖等待（P1）

Deployment 已内置 initContainer：

| 组件 | 等待顺序 | 效果 |
|------|---------|------|
| backend | wait-for-mysql → wait-for-redis | MySQL + Redis 就绪后才启动 |
| worker | wait-for-mysql → wait-for-redis | 同上 |
| schedule | wait-for-mysql → wait-for-redis | 同上 |
| watch | wait-for-mysql → wait-for-redis | 同上 |
| frontend | wait-for-backend | Backend 健康检查通过后才启动 |

entrypoint.sh 所有 `db upgrade` 等非关键操作已加 `|| true`，不会因初始失败 CrashLoopBackOff。

### 1.3 数据层 — 持久化存储（P2）

当前 Redis/MySQL 用 emptyDir，Pod 重启数据丢失（Redis 缓存丢没事，但 MySQL 不能丢）。

**如果 MySQL 还在 Pod 里运行**，需要先部署 PV/PVC：

```bash
# 在有 redis=true 标签的节点上创建目录
REDIS_NODE=$(kubectl get nodes -l redis=true -o jsonpath='{.items[0].metadata.name}')
# SSH 到 ${REDIS_NODE}: mkdir -p /data/k8s/infra/redis
```

**如果已经切到裸金属 MySQL**（如开发集群 k8s-worker2 上的 3306），MySQL PV/PVC 不需要部署。

```bash
# Redis 持久化
kubectl apply -f restart/redis-pv-pvc-hostpath.yaml

# MySQL 持久化（仅 Pod 模式需要）
kubectl apply -f restart/mysql-pv-pvc-hostpath.yaml
```

---

## 二、部署步骤

```bash
# 1. 每台节点执行（需要 root）
bash restart/k8s-node-autostart.sh

# 2. 创建 Redis 数据目录（在目标节点上）
mkdir -p /data/k8s/infra/redis

# 3. 部署 PV/PVC
kubectl apply -f restart/redis-pv-pvc-hostpath.yaml

# 4. 如果 MySQL 还在 Pod 里，同样部署
kubectl apply -f restart/mysql-pv-pvc-hostpath.yaml

# 5. 重启各 Deployment（让 initContainer 生效）
kubectl rollout restart deployment -n infra
```

---

## 三、验证

```bash
# 节点自启动状态
systemctl is-enabled docker kubelet
# 应返回 enabled

# Redis 持久化
kubectl get pvc -n infra infra-redis-pvc
# STATUS 应为 Bound

# Pod 全部 Running
kubectl get pods -n infra
```

---

## 四、文件清单

| 文件 | 说明 |
|------|------|
| `k8s-node-autostart.sh` | 节点自启动配置脚本（每台执行） |
| `redis-pv-pvc-hostpath.yaml` | Redis 持久化存储 |
| `mysql-pv-pvc-hostpath.yaml` | MySQL 持久化存储（Pod 模式） |


cat > /etc/haproxy/haproxy.cfg << 'EOF'
global
    log /dev/log local0
    maxconn 4096
    daemon

defaults
    mode tcp
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend k8s-api
    bind 127.0.0.1:6443
    default_backend k8s-masters

backend k8s-masters
    balance roundrobin
    option tcp-check
    server master1 192.168.11.11:6443 check inter 3s fall 2 rise 2
    server master2 192.168.11.12:6443 check inter 3s fall 2 rise 2
    server master3 192.168.11.13:6443 check inter 3s fall 2 rise 2
EOF


