# Cube Studio K8s 集群 HA 方案（无 VIP）

> **约束：** 不能自定 VIP（IP 由行内统一管理），不能用 MetalLB 抢 IP。
> **目标：** 3 Master 高可用，任意一台宕机不影响 kubectl / kubelet / 外部访问。

---

## 一、方案调研

| 方案 | 原理 | 优点 | 缺点 | 适合本场景？|
|------|------|------|------|------------|
| **A. HAProxy 本地代理** | 每节点起 HAProxy → 3 个 apiserver，本地访问 `127.0.0.1:6443` | 无外部依赖、秒级故障切换 | 每节点多跑一个进程 | ✅ 推荐 |
| **B. DNS 轮询** | DNS 解析返回 3 个 master IP | 不额外部署 | DNS 缓存导致故障切换慢（分钟级）| ❌ |
| **C. 外部 LB** | 申请行内 F5/NGINX VIP | 专业、成熟 | 要跨部门协调 | ⚠️ 长期方案 |
| **D. kube-vip** | ARP 抢 IP（和 MetalLB 同原理） | 轻量 | 同样要占 IP | ❌ 违反约束 |
| **E. Multi-address kubeconfig** | kubeconfig 配多个 server，kubectl 自动重试 | 零部署 | 只有 kubectl 支持，kubelet 不支持 | ❌ |

**推荐方案 A：HAProxy 本地代理**，配合行内申请 VIP（方案 C）做长期规划。

---

## 二、方案 A 架构

```
┌──────────────────────────────────────────────────────┐
│                    K8s 集群                           │
│                                                      │
│  Master1 (39)          Master2 (48)     Master3 (77) │
│  ┌──────┐             ┌──────┐        ┌──────┐      │
│  │apiser│◄────────────│apiser│◄───────│apiser│      │
│  │ver   │────────────►│ver   │───────►│ver   │      │
│  └──┬───┘             └──┬───┘        └──┬───┘      │
│     │                    │               │          │
│  ┌──┴──────────────┐    │               │          │
│  │ haproxy :6443   │    │               │          │
│  │ backend:        │    │               │          │
│  │  39:6443        │    │               │          │
│  │  48:6443        │    │               │          │
│  │  77:6443        │    │               │          │
│  └─────────────────┘    │               │          │
│     ▲                   ▲               ▲          │
│  kubelet            kubelet          kubelet        │
│  kubectl            kubectl          kubectl        │
│  连 127.0.0.1:6443  连 127.0.0.1:6443               │
│                                                      │
│  Worker1 (80)         Worker2 (82)     Worker3 (83)  │
│  ┌─────────────────┐  (同 worker1)     (同 worker1)  │
│  │ haproxy :6443   │                                │
│  │ → 39, 48, 77    │                                │
│  └─────────────────┘                                │
│     ▲                                               │
│  kubelet → 127.0.0.1:6443                           │
└──────────────────────────────────────────────────────┘
```

**关键点：** 每台节点（6 台）都跑一个 HAProxy，监听 `127.0.0.1:6443`，后端是 3 个 apiserver。kubelet 和 kubectl 全部指向 `127.0.0.1:6443`。

**故障切换：** 任意 master 宕机 → HAProxy 自动踢掉 → 流量走剩余 2 台 → kubelet/kubectl 无感知。

---

## 三、实施步骤

### 3.1 每台节点安装 HAProxy（需要 root）

```bash
# 6 台节点都执行
yum install -y haproxy
```

### 3.2 配置 HAProxy

在**每台节点**创建 `/etc/haproxy/haproxy.cfg`：

```cfg
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
    server master1 10.240.125.39:6443 check inter 3s fall 2 rise 2
    server master2 10.240.125.48:6443 check inter 3s fall 2 rise 2
    server master3 10.240.125.77:6443 check inter 3s fall 2 rise 2
```

参数含义：
- `inter 3s` — 每 3 秒健康检查
- `fall 2` — 连续 2 次失败踢掉
- `rise 2` — 连续 2 次成功加回来
- 故障检测时间：**6 秒**

### 3.3 启动 + 自启

```bash
systemctl enable haproxy --now
systemctl status haproxy
```

### 3.4 改 kubelet 配置（6 台）

```bash
# 改 kubelet.conf 指向本地 HAProxy
sed -i 's|server: https://.*:6443|server: https://127.0.0.1:6443|g' /etc/kubernetes/kubelet.conf
systemctl restart kubelet
```

### 3.5 改 kubectl 配置（master1）

```bash
sed -i 's|server: https://.*:6443|server: https://127.0.0.1:6443|g' ~/.kube/config
kubectl get nodes   # 验证
```

### 3.6 删掉 MetalLB + VIP

```bash
# 确认不再需要
kubectl delete -f /bdm/share_bdm/cube-studio-master/install/kubernetes/metallb-config.yaml
kubectl delete -f /bdm/share_bdm/cube-studio-master/install/kubernetes/apiserver-lb.yaml
kubectl delete -f /bdm/share_bdm/cube-studio-master/install/kubernetes/metallb/metallb-native.yaml
```

### 3.7 验证故障切换

```bash
# 持续监控
watch -n 2 'kubectl get nodes'

# 停掉 master2 的 apiserver
# SSH 到 10.240.125.48:
mv /etc/kubernetes/manifests/kube-apiserver.yaml /tmp/
sleep 20

# kubectl 应该仍然可用（HAProxy 自动切到 master1/3）
kubectl get nodes

# 恢复
mv /tmp/kube-apiserver.yaml /etc/kubernetes/manifests/
```

---

## 四、物料清单

| 文件 | 说明 | 部署到 |
|------|------|--------|
| `haproxy.cfg` | HAProxy 配置模板 | 每台节点的 `/etc/haproxy/` |
| `setup-haproxy.sh` | 一键安装+配置脚本 | 每台节点执行 |

---

## 五、与 VIP 方案的对比

| 维度 | VIP (MetalLB) | HAProxy 本地代理 |
|------|---------------|------------------|
| IP 占用 | 需要 1 个独立 VIP | 用 localhost，不占 IP |
| 故障切换 | L2 ARP 漂移，3-5 秒 | TCP check，6 秒踢掉 |
| 外部依赖 | MetalLB speaker 必须运行 | 无（HAProxy 是独立进程） |
| 单点风险 | MetalLB speaker 本身 | 无（每节点独立） |
| 管理复杂度 | 需要维护 MetalLB + IP Pool | 每节点一个 haproxy.cfg |
| kubectl 访问 | VIP 永远可达 | 必须 SSH 到节点上用 127.0.0.1 |

**注意：** kubectl 指向 `127.0.0.1` 意味着必须登录到 K8s 节点才能用 kubectl。如果需要在笔记本上远程管理，要么 VPN 到节点，要么申请行内 VIP（方案 C）做长期方案。

---

## 六、建议实施路径

```
Phase 1（现在）
  → 部署 HAProxy 本地代理（本方案）
  → 删 MetalLB，释放 192.168.11.200
  → K8s API Server HA 完全无 VIP

Phase 2（生产上线前）
  → 向行内申请 1 个 VIP（用于 K8s API Server）
  → VIP 后端指向 HAProxy 或直接指向 3 个 master
  → kubectl 远程管理用 VIP

Phase 3（前端对外）
  → 向行内申请 1 个 VIP（用于 Cube Studio 前端）
  → 上游防火墙 VIP:80 → 3 个节点 30080
```
