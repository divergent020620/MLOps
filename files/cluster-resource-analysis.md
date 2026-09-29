# Cube Studio 集群资源分析（空载实际占用）

> 采集时间：2026-07-15 | 数据源：metrics-server / kubelet stats

---

## 一、各节点实际占用

### k8s-master1 — CPU=0.15C, MEM=6.8Gi, /bdm 100G(17%)

| Pod | CPU | 内存 |
|-----|-----|------|
| kubeflow-dashboard | 5m | 4003Mi |
| prometheus-k8s | 20m | 1043Mi |
| kube-apiserver | 67m | 909Mi |
| kubeflow-watch | 5m | 394Mi |
| etcd | 34m | 243Mi |
| dashboard-frontend | 0m | 175Mi |
| node-exporter | 1m | 42Mi |
| kube-scheduler | 3m | 33Mi |
| kube-controller-manager | 2m | 31Mi |
| kube-proxy | 1m | 27Mi |
| flannel | 5m | 20Mi |
| redis | 5m | 8Mi |

### k8s-master2 — CPU=0.15C, MEM=1.3Gi, /bdm 100G(30% = Harbor 镜像)

| Pod | CPU | 内存 |
|-----|-----|------|
| kube-apiserver | 67m | 692Mi |
| etcd | 38m | 242Mi |
| kube-controller-manager | 19m | 102Mi |
| istio-ingressgateway | 8m | 69Mi |
| istiod | 3m | 69Mi |
| kube-scheduler | 4m | 51Mi |
| node-exporter | 1m | 32Mi |
| kube-proxy | 1m | 26Mi |
| flannel | 5m | 18Mi |

### k8s-master3 — CPU=0.13C, MEM=3.4Gi, /bdm 100G(7%)

| Pod | CPU | 内存 |
|-----|-----|------|
| dashboard-worker | 2m | 2122Mi |
| kube-apiserver | 53m | 678Mi |
| dashboard-schedule | 16m | 199Mi |
| etcd | 31m | 185Mi |
| grafana | 2m | 84Mi |
| node-exporter | 1m | 44Mi |
| volcano-scheduler | 11m | 36Mi |
| kube-scheduler | 3m | 35Mi |
| kube-controller-manager | 2m | 32Mi |
| prometheus-operator | 2m | 28Mi |
| kube-proxy | 1m | 25Mi |
| volcano-controllers | 1m | 24Mi |
| flannel | 4m | 18Mi |


---

## 二、汇总

| 节点 | CPU | 内存 | 系统盘 | 数据盘 | 主要占用 |
|------|-----|------|--------|--------|---------|
| k8s-master1 | 0.15C | **6.8Gi** | / 50G (20%) | /bdm 100G (17%) | 源码 + 镜像 + NFS 共享导出 |
| k8s-master2 | 0.15C | 1.3Gi | / 50G (16%) | /bdm 100G (30%) | Harbor 镜像仓库 (30G) |
| k8s-master3 | 0.13C | 3.4Gi | / 50G (14%) | /bdm 100G (7%) | 少量数据 |
| k8s-worker1 | 0.02C | 0.4Gi | / 50G | /bdm 100G | PV hostPath 数据 |
| k8s-worker2 | 0.01C | 0.3Gi | / 50G | /bdm 100G | MySQL 数据 (/bdm/mysql) |
| **合计** | **0.45C** | **12.1Gi** | | | |

### 100 并发 API 压测

| 指标 | 值 |
|------|-----|
| QPS | 146 |
| p50 | 0.06s |
| p95 | 0.18s |
| p99 | 0.38s |
| CPU 增量 | +~0.5C（dashboard 进程） |
| 内存增量 | 几乎无 |

---
