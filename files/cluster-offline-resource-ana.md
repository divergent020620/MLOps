# 生产集群资源分析（10.240.x.x 网段）

> 采集时间：2026-07-15 | 6 节点（3 master + 3 worker） | 已运行 42 天

---

## 一、节点总览

| 节点 | IP | 角色 | OS | K8s |
|------|-----|------|-----|-----|
| k8s-master1 | 10.240.125.39 | control-plane | Kylin V10 (Halberd) | v1.28.2 |
| k8s-master2 | 10.240.125.48 | control-plane | Kylin V10 (Halberd) | v1.28.2 |
| k8s-master3 | 10.240.125.77 | control-plane | Kylin V10 (Halberd) | v1.28.2 |
| k8s-worker1 | 10.240.125.80 | worker | Kylin V10 (Halberd) | v1.28.2 |
| k8s-worker2 | 10.240.125.82 | worker | Kylin V10 (Halberd) | v1.28.2 |
| k8s-worker3 | 10.240.125.83 | worker | Kylin V10 (Halberd) | v1.28.2 |

---

## 二、各节点实际占用

### k8s-master1 — CPU=225m, MEM=16.2Gi

| Pod | CPU | 内存 | 说明 |
|-----|-----|------|------|
| kubeflow-dashboard | 3m | 3884Mi | Flask |
| dashboard-worker | 2m | 2016Mi | Celery worker |
| prometheus-k8s | 31m | 1512Mi | 监控 DB（42 天数据积累） |
| **mysql** | 3m | **955Mi** | 数据库（Pod 方式） |
| kube-apiserver | 40m | 810Mi | |
| kubeflow-watch | 1m | 397Mi | |
| dashboard-schedule | 26m | 224Mi | Celery beat |
| dashboard-frontend | 0m | 178Mi | nginx |
| etcd | 27m | 174Mi | |
| grafana | 3m | 135Mi | |
| node-exporter | 1m | 48Mi | |
| prometheus-operator | 1m | 43Mi | |
| kube-controller-manager | 1m | 38Mi | |
| flannel | 5m | 34Mi | |
| kube-scheduler | 2m | 34Mi | |
| kube-proxy | 1m | 33Mi | |
| redis | 4m | 12Mi | |

### k8s-master2 — CPU=157m, MEM=5.5Gi

| Pod | CPU | 内存 | 说明 |
|-----|-----|------|------|
| kube-apiserver | 37m | 765Mi | |
| etcd | 32m | 200Mi | |
| istio-ingressgateway | 7m | 156Mi | |
| istiod | 3m | 82Mi | |
| node-exporter | 1m | 46Mi | |
| volcano-scheduler | 9m | 44Mi | |
| kube-controller-manager | 1m | 36Mi | |
| kube-scheduler | 3m | 35Mi | |
| workflow-controller | 2m | 35Mi | |
| volcano-controllers | 1m | 27Mi | |
| kube-proxy | 1m | 26Mi | |
| flannel | 5m | 21Mi | |

### k8s-master3 — CPU=119m, MEM=5.4Gi

| Pod | CPU | 内存 | 说明 |
|-----|-----|------|------|
| kube-apiserver | 39m | 765Mi | |
| kube-controller-manager | 11m | 90Mi | |
| etcd | 28m | 174Mi | |
| node-exporter | 1m | 45Mi | |
| coredns | 2m | 41Mi | DNS |
| kube-scheduler | 2m | 38Mi | |
| kube-proxy | 1m | 26Mi | |
| flannel | 5m | 23Mi | |

### k8s-worker1 — CPU=57m, MEM=4.5Gi

| Pod | CPU | 内存 |
|-----|-----|------|
| minio | 1m | 112Mi |
| node-exporter | 2m | 47Mi |
| metrics-server | 4m | 37Mi |
| coredns | 2m | 36Mi |
| kubernetes-dashboard-cluster | 1m | 32Mi |
| kube-proxy | 1m | 30Mi |
| dashboard-cluster-metrics-scraper | 1m | 29Mi |
| kubernetes-dashboard-user1 | 1m | 28Mi |
| dashboard-user1-metrics-scraper | 1m | 25Mi |
| flannel | 4m | 21Mi |

### k8s-worker2 — CPU=80m, MEM=6.6Gi

| Pod | CPU | 内存 | 说明 |
|-----|-----|------|------|
| **notebook-spark** | 1m | **2720Mi** | 长期运行的 Spark Notebook |
| node-exporter | 2m | 43Mi | |
| kube-proxy | 1m | 26Mi | |
| flannel | 6m | 22Mi | |

### k8s-worker3 — CPU=52m, MEM=4.3Gi

| Pod | CPU | 内存 | 说明 |
|-----|-----|------|------|
| node-exporter | 1m | 44Mi | |
| training-operator | 1m | 41Mi | |
| server-test | 1m | 37Mi | 长期运行的测试服务 |
| kube-proxy | 1m | 30Mi | |
| flannel | 5m | 21Mi | |
| batch-test | 0m | 3Mi | |

---

## 三、汇总

| 节点 | CPU | 内存 | 系统盘 | 数据盘 | NFS |
|------|-----|------|--------|--------|-----|
| k8s-master1 | 0.23C | **16.2Gi** | / 15G (57%) | /bdm **300G (76%)** | NFS 服务端 |
| k8s-master2 | 0.16C | 5.5Gi | / 15G (48%) | /bdm 300G (2%) | 挂载 master1:/bdm/share_bdm |
| k8s-master3 | 0.12C | 5.4Gi | / 15G (48%) | /bdm 300G (2%) | 挂载 master1:/bdm/share_bdm |
| k8s-worker1 | 0.06C | 4.5Gi | — | — | |
| k8s-worker2 | 0.08C | 6.6Gi | — | — | |
| k8s-worker3 | 0.05C | 4.3Gi | — | — | |
| **合计** | **0.69C** | **42.5Gi** | | | |

---

## 四、与开发集群对比

| 维度 | 开发（5节点） | 生产（6节点） |
|------|-------------|-------------|
| 总 CPU 实际 | 0.45C | 0.69C |
| 总内存实际 | 12.1Gi | **42.5Gi** |
| 最大节点 | master1 6.8Gi | **master1 16.2Gi** |
| 内存差异原因 | — | 生产多了 MySQL(955Mi) + notebook-spark(2.7Gi) + batch-test/server-test + Prometheus 数据多 500Mi |
| master1 /bdm | — | **76% 告警** (226/300G) |
