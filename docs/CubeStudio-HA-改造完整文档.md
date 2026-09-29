# Cube Studio HA 改造完整文档

> 日期：2026-07-21  
> 目标：3 Master + 2 Worker，任意 Master 宕机，用户和运维均无感知  

---

## 一、改造全景

```
改造前:
  所有流量 → 192.168.11.11 (master1) ← 单点
  master1 宕机 → 集群全崩

改造后:
  用户流量 → 192.168.11.100 (MetalLB VIP) → Istio → Frontend(2副本) → Backend(2副本)
  运维流量 → 192.168.11.200 (MetalLB VIP) → API Server(3副本)
  任一 Master 宕机 → VIP 自动漂移 → 服务不中断
```

---

## 二、改造清单

### 2.1 Kubernetes 层（控制面 HA）

| # | 改了什么 | 文件/命令 | 原因 |
|---|---------|----------|------|
| 1 | kubeadm 初始配置加 `192.168.11.200` 到 certSANs | `kubeadm-init.yaml` | API Server 证书必须包含 VIP，否则 kubelet TLS 校验失败 |
| 2 | `controlPlaneEndpoint` 改为 VIP | `kubeadm-init.yaml` | kubeadm join 时新节点连 VIP 而不是某台 Master |
| 3 | 部署 MetalLB | `metallb-native.yaml` | L2 模式 ARP 实现 VIP 漂移 |
| 4 | 创建 MetalLB IP 池 + L2 宣告 | `apiserver-lb.yaml` | 分配 `192.168.11.100`(前端) 和 `192.168.11.200`(API Server) |
| 5 | 创建 `kube-apiserver-lb` Service (LoadBalancer) | `apiserver-lb.yaml` | 3 个 apiserver 自动成为 Endpoint |
| 6 | Worker kubelet 连 VIP | `/etc/kubernetes/kubelet.conf` | Master 宕机时 Worker 不丢失 kubelet 连接 |
| 7 | kubectl 配置指向 VIP | `~/.kube/config` | 任一 Master 宕机 kubectl 仍可用 |

### 2.2 Cube Studio 应用层（业务 HA）

| # | 改了什么 | 文件 | 原因 |
|---|---------|------|------|
| 8 | Frontend replicas:1→2 + podAntiAffinity + 探针 | `deploy-frontend.yaml` | 死 1 个还有 1 个 |
| 9 | Backend replicas:1→2 + podAntiAffinity + preStop | `deploy-backend.yaml` | 同上 + 优雅关闭 |
| 10 | Worker replicas:1→2 + 探针修复 | `deploy-worker.yaml` | 异步任务不中断 |
| 11 | Istio IngressGateway replicas:1→2 | `kubectl scale` | 入口不单点 |
| 12 | istiod replicas:1→2 | `kubectl scale` | Istio 控制面不单点 |
| 13 | Istio VirtualService 加 retry | `virtual.yaml` | 宕机瞬间请求自动重试到存活 Pod |
| 14 | entrypoint.sh 加 `|| true` | `entrypoint.sh` | Pod 重启不 CrashLoopBackOff |
| 15 | ENABLE_PROXY_FIX=True + 连接池缩小 | `config.py` | 多级代理 IP 正确 + 防止撑爆 MySQL |
| 16 | PodDisruptionBudget (4个) | `pdb.yaml` | 维护时不误杀所有 Pod |

---

## 三、改动的文件清单

```
install/kubernetes/cube/base/deploy-frontend.yaml   ← replicas:2, podAntiAffinity, 探针
install/kubernetes/cube/base/deploy-backend.yaml    ← replicas:2, podAntiAffinity, preStop, 探针提速
install/kubernetes/cube/base/deploy-worker.yaml     ← replicas:2, liveness 探针修复
install/kubernetes/cube/base/pdb.yaml               ← 新建, 4个 PDB
install/kubernetes/cube/base/kustomization.yml      ← 加入 pdb.yaml
install/kubernetes/cube/overlays/config/config.py   ← ENABLE_PROXY_FIX, 连接池缩小
install/kubernetes/cube/overlays/config/entrypoint.sh ← create-admin/init 加 || true
install/docker/config.py                            ← ENABLE_PROXY_FIX 同步
install/docker/entrypoint.sh                        ← create-admin/init 加 || true
install/kubernetes/virtual.yaml                     ← Istio retry + cancelled
install/kubernetes/metallb-native.yaml              ← 新建, MetalLB (私有仓库镜像)
install/kubernetes/metallb-config.yaml              ← 新建, IP池 192.168.11.100
install/kubernetes/apiserver-lb.yaml                ← 新建, IP池+200 + API Server LB Service
```

---

## 四、关键技术决策

| 问题 | 决策 | 原因 |
|------|------|------|
| API Server HA 方式 | MetalLB Service 而非 keepalived+HAProxy | 不需要额外安装系统包，纯 K8s 原生 |
| Master kubelet 连谁 | 各自的本地 apiserver (127.0.0.1) | 避免 hairpin NAT 问题 |
| Worker kubelet 连谁 | VIP 192.168.11.200 | Master 宕机时 Worker 不丢失连接 |
| kubectl 连谁 | VIP 192.168.11.200 | 任一 Master 宕机 kubectl 仍可用 |
| 为什么 MetalLB Service 第一次失败 | 所有节点 NotReady 时 Endpoint 控制器拒绝添加 Pod | 证书加 VIP SAN 后，集群健康时正常 |
| Celery Beat HA | 不改造，保持单实例 | 多实例会重复执行定时任务 |
| Redis HA | 不改造 | 挂掉影响性能(缓存 miss)不影响 HTTP 200 |

---

## 五、测试结果

| 测试项 | 方法 | 结果 |
|--------|------|------|
| 停 master2 kubelet | `systemctl stop kubelet` + curl 5 维度监控 | 全 200，零 5xx ✅ |
| 停 master1 kubelet | 同上 | kubectl 仍可用(连 VIP)，其他节点 Ready ✅ |
| 3 轮 drain 测试 | cordon+drain 三台 Master 依次 | 应用层无中断 ✅ |

---

## 六、对已有集群的改造步骤（已执行）

```bash
# 1. 证书加 VIP SAN
# 每台 master 执行:
cp -r /etc/kubernetes/pki /etc/kubernetes/pki.bak
rm /etc/kubernetes/pki/apiserver.crt /etc/kubernetes/pki/apiserver.key
kubeadm init phase certs apiserver \
  --apiserver-cert-extra-sans=192.168.11.200 \
  --kubernetes-version=v1.28.2
mv /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/
sleep 15
mv /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/

# 2. 部署 MetalLB
kubectl apply -f install/kubernetes/metallb-native.yaml

# 3. 创建 VIP 池 + API Server LB
kubectl apply -f install/kubernetes/metallb-config.yaml
kubectl apply -f install/kubernetes/apiserver-lb.yaml

# 4. 切 Istio IngressGateway 为 LoadBalancer
kubectl patch svc istio-ingressgateway -n istio-system \
  -p '{"spec":{"type":"LoadBalancer","externalIPs":null}}'

# 5. Worker kubelet 指向 VIP
sed -i 's|server: https://192.168.11.11:6443|server: https://192.168.11.200:6443|g' \
  /etc/kubernetes/kubelet.conf
systemctl restart kubelet

# 6. kubectl 指向 VIP
sed -i 's|server: https://192.168.11.11:6443|server: https://192.168.11.200:6443|g' \
  ~/.kube/config

# 7. 应用 Cube Studio HA 改动
kubectl apply -k install/kubernetes/cube/overlays
kubectl apply -f install/kubernetes/virtual.yaml

# 8. Istio 组件扩容
kubectl scale deploy istio-ingressgateway -n istio-system --replicas=2
kubectl scale deploy istiod -n istio-system --replicas=2
```

---

## 七、相关文件路径

| 文件 | 路径 |
|------|------|
| 调研报告 | `docs/ha-research-report.md` |
| 测试方案 | `docs/ha-test-plan.md` |
| 完整测试脚本 | `scripts/ha_full_test.sh` |
| API Server LB 配置 | `install/kubernetes/apiserver-lb.yaml` |
| MetalLB 配置 | `install/kubernetes/metallb-config.yaml` |
| PDB 配置 | `install/kubernetes/cube/base/pdb.yaml` |
