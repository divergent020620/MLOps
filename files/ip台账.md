# 集群 IP 台账

## 集群一：生产环境（10.240.x.x 网段）

> OS: Kylin Linux Advanced Server V10 (Halberd) | K8s: v1.28.2 | Runtime: containerd 1.7.16

### 节点规格总览

| 节点 | IP | CPU | 内存 | 磁盘 | 角色 |
|------|-----|-----|------|------|------|
| k8s-master1 | 10.240.125.39 | 16C | 30.7Gi | 15Gi | control-plane |
| k8s-master2 | 10.240.125.48 | 16C | 30.7Gi | 15Gi | control-plane |
| k8s-master3 | 10.240.125.77 | 16C | 30.7Gi | 15Gi | control-plane |
| k8s-worker1 | 10.240.125.80 | 16C | 30.7Gi | 15Gi | worker |
| k8s-worker2 | 10.240.125.82 | 16C | 30.7Gi | 15Gi | worker |
| k8s-worker3 | 10.240.125.83 | 16C | 30.7Gi | 15Gi | worker |

### 各节点部署明细

**k8s-master1** `10.240.125.39` — 主管理节点

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| etcd / apiserver / controller-manager / scheduler | kube-system | 控制面 |
| kubeflow-dashboard | infra | 后端 |
| kubeflow-dashboard-frontend | infra | 前端 nginx |
| kubeflow-dashboard-schedule | infra | Celery beat |
| kubeflow-dashboard-worker | infra | Celery worker |
| mysql | infra | 数据库 |
| redis | infra | 缓存 |
| grafana | monitoring | 监控面板 |
| prometheus-operator | monitoring | 监控 Operator |
| prometheus-k8s | monitoring | Prometheus 实例 |
| node-exporter / flannel | - | 监控 + 网络 |

**k8s-master2** `10.240.125.48` — 网关 + 调度

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| etcd / apiserver / controller-manager / scheduler | kube-system | 控制面 |
| istio-ingressgateway | istio-system | 入口网关 |
| istiod | istio-system | 服务网格 |
| volcano-controllers / volcano-scheduler | kubeflow | 批调度器 |
| workflow-controller | kubeflow | Argo 工作流 |
| node-exporter / flannel | - | 监控 + 网络 |

**k8s-master3** `10.240.125.77` — 轻量控制面

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| etcd / apiserver / controller-manager / scheduler | kube-system | 控制面 |
| coredns | kube-system | DNS |
| node-exporter / flannel | - | 监控 + 网络 |

**k8s-worker1** `10.240.125.80` — 核心业务

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| coredns | kube-system | DNS |
| kubernetes-dashboard (集群版+用户版) | kube-system | K8s 管理面板 |
| metrics-server | kube-system | 指标采集 |
| minio | kubeflow | 对象存储 |
| node-exporter / flannel | - | 监控 + 网络 |

**k8s-worker2** `10.240.125.82` — Jupyter Notebook

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| notebook-spark | infra | Jupyter Notebook (Spark) |
| node-exporter / flannel | - | 监控 + 网络 |

**k8s-worker3** `10.240.125.83` — 训练 + 测试

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| training-operator | kubeflow | TF/PyTorch 训练 Job |
| batch-test / server-test | infra | 批处理 + 服务测试 |
| node-exporter / flannel | - | 监控 + 网络 |

### Pod 分布统计

| 节点 | Pod 数 |
|------|--------|
| k8s-master1 | 13 |
| k8s-master2 | 9 |
| k8s-master3 | 8 |
| k8s-worker1 | 10 |
| k8s-worker2 | 4 |
| k8s-worker3 | 6 |

---

## 集群二：开发环境（192.168.11.x 网段）

> OS: Kylin Linux Advanced Server V10 (Tercel) | K8s: v1.28.2 | Runtime: containerd 1.7.16

### 节点规格总览

| 节点 | IP | CPU | 内存 | 磁盘 | 角色 |
|------|-----|-----|------|------|------|
| k8s-master1 | 192.168.11.11 | 12C | 31Gi | 50Gi | control-plane |
| k8s-master2 | 192.168.11.12 | 12C | 31Gi | 50Gi | control-plane |
| k8s-master3 | 192.168.11.13 | 12C | 31Gi | 50Gi | control-plane |
| k8s-worker1 | 192.168.11.14 | 12C | 31Gi | 50Gi | worker |
| k8s-worker2 | 192.168.11.15 | 12C | 31Gi | 50Gi | worker |

### 各节点部署明细

**k8s-master1** `192.168.11.11`

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| etcd / apiserver / kube-proxy | kube-system | 控制面 |
| flannel | kube-flannel | CNI 网络 |
| kubeflow-dashboard | infra | 后端 |
| kubeflow-dashboard-frontend | infra | 前端 nginx |
| kubeflow-dashboard-schedule | infra | Celery beat |
| kubeflow-dashboard-worker | infra | Celery worker |
| kubeflow-watch | infra | K8s 资源监控 |

**k8s-master2** `192.168.11.12`

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| etcd / apiserver / controller-manager / scheduler | kube-system | 控制面（主） |
| istio-ingressgateway | istio-system | 入口网关 |
| istiod | istio-system | 服务网格控制面 |
| grafana | monitoring | 监控面板 |
| flannel / kube-proxy | - | 网络 |

**k8s-master3** `192.168.11.13`

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| etcd / apiserver / controller-manager / scheduler | kube-system | 控制面 |
| redis | infra | 缓存 |
| volcano (controllers + scheduler) | kubeflow | 批调度器 |
| prometheus-operator | monitoring | 监控 Operator |
| flannel / kube-proxy | - | 网络 |

**k8s-worker1** `192.168.11.14` — 计算节点

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| mysql | infra | 数据库 |
| minio | kubeflow | 对象存储 |
| workflow-controller | kubeflow | Argo 工作流 |
| coredns | kube-system | DNS |
| kubernetes-dashboard (集群版+用户版) | kube-system | K8s 管理面板 |

**k8s-worker2** `192.168.11.15` — 计算节点

| 服务 | 命名空间 | 说明 |
|------|---------|------|
| training-operator | kubeflow | TF/PyTorch 训练 Job |
| coredns | kube-system | DNS |
| flannel / kube-proxy | - | 网络 |

### Pod 分布统计

| 节点 | Pod 数 |
|------|--------|
| k8s-master1 | 10 |
| k8s-master2 | 10 |
| k8s-master3 | 11 |
| k8s-worker1 | 11 |
| k8s-worker2 | 5 |

### 标签分配

| 标签 | 节点 |
|------|------|
| `kubeflow-dashboard=true` | master1 |
| `train/cpu/notebook/service=true` | master1, worker1, worker2 |
| `mysql=true` | master1, master2, master3 |
| `redis=true` | master1, master2, master3 |
| `istio/monitoring/kubeflow=true` | master1, master2, master3 |
