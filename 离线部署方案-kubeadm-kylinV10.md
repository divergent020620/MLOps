﻿# CubeStudio 离线部署方案 — Kubeadm + K8s 1.28 + 麒麟V10

> **适用场景**：完全离线（无互联网）的内网环境  
> **操作系统**：麒麟V10 Server（Kylin Linux Advanced Server V10，基于 OpenEuler/CentOS，使用 yum/dnf）  
> **K8s 版本**：1.28.2（`v1.28.2`）  
> **容器运行时**：containerd（推荐）或 Docker 23.0.4  
> **CNI 网络插件**：Flannel（`ghcr.io/flannel-io/flannel:v0.28.4`）  
> **镜像仓库**：Harbor 自建私有仓库  
> **K8s 部署工具**：kubeadm（不使用 Rancher）

---

## 一、方案架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      联网机器（跳板机）                            │
│  1. 下载 k8s 1.28 离线二进制包 (kubeadm/kubelet/kubectl)         │
│  2. 下载 CNI 插件、containerd、Flannel yaml                      │
│  3. 下载 Harbor 离线安装包                                        │
│  4. 下载麒麟V10 RPM依赖包（可选，如内网已有yum源则跳过）           │
│  5. 从用户已有虚机导出全部容器镜像 → 打包为 tar.gz                │
└───────────────┬─────────────────────────────────────────────────┘
                │ U盘/移动硬盘 拷贝
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    离线内网环境（目标集群）                         │
│                                                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                     │
│  │  Master   │   │ Worker-1 │   │ Worker-N │   ...              │
│  │ (kubeadm │   │ (kubeadm │   │ (kubeadm │                     │
│  │  init)   │   │  join)   │   │  join)   │                     │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘                     │
│       │              │              │                             │
│       └──────────────┼──────────────┘                             │
│                      │                                            │
│              ┌───────▼───────┐                                    │
│              │    Harbor     │  私有镜像仓库                       │
│              │  (v2.11.1+)  │                                     │
│              └───────────────┘                                    │
│                      │                                            │
│                      ▼ 所有容器镜像从Harbor拉取                     │
│              ┌───────────────┐                                    │
│              │  CubeStudio   │  MLOps 平台                        │
│              │  全部组件      │                                    │
│              └───────────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 已具备的镜像清单（来自用户虚机导出）

根据 `log.txt`，用户虚机中已部署成功，所有需要的镜像如下（**53个镜像全量清单**）：

| 序号 | 镜像完整名称 | 类型 |
|------|------------|------|
| 1 | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-apiserver:v1.28.2` | K8s核心 |
| 2 | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-controller-manager:v1.28.2` | K8s核心 |
| 3 | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-scheduler:v1.28.2` | K8s核心 |
| 4 | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-proxy:v1.28.2` | K8s核心 |
| 5 | `registry.cn-hangzhou.aliyuncs.com/google_containers/coredns:v1.10.1` | K8s核心 |
| 6 | `registry.cn-hangzhou.aliyuncs.com/google_containers/etcd:3.5.9-0` | K8s核心 |
| 7 | `registry.cn-hangzhou.aliyuncs.com/google_containers/pause:3.9` | K8s核心 |
| 8 | `registry.cn-hangzhou.aliyuncs.com/google_containers/pause:3.8` | K8s核心 |
| 9 | `ghcr.io/flannel-io/flannel:v0.28.4` | CNI网络 |
| 10 | `ghcr.io/flannel-io/flannel-cni-plugin:v1.9.1-flannel1` | CNI网络 |
| 11 | `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2025.03.01` | 平台后端 |
| 12 | `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2025.03.01` | 平台前端 |
| 13 | `ccr.ccs.tencentyun.com/cube-studio/k8s-dashboard:v2.6.1` | K8s Dashboard |
| 14 | `ccr.ccs.tencentyun.com/cube-studio/redis:7.4` | Redis |
| 15 | `ccr.ccs.tencentyun.com/cube-studio/kube-rbac-proxy:0.14.1` | RBAC代理 |
| 16 | `ccr.ccs.tencentyun.com/cube-studio/notebook:jupyter-ubuntu22.04` | Notebook |
| 17 | `ccr.ccs.tencentyun.com/cube-argoproj/argocli:v3.4.3` | Argo CLI |
| 18 | `ccr.ccs.tencentyun.com/cube-argoproj/argoexec:v3.4.3` | Argo Executor |
| 19 | `ccr.ccs.tencentyun.com/cube-argoproj/workflow-controller:v3.4.3` | Argo Controller |
| 20 | `docker.io/library/mysql:8.0.32` | MySQL |
| 21 | `docker.io/library/redis:7.4`（已有 cube-studio 版本） | Redis |
| 22 | `docker.io/library/postgres:11.5` | PostgreSQL |
| 23 | `docker.io/library/python:3.9` | Python基础镜像 |
| 24 | `docker.io/library/ubuntu:20.04` | Ubuntu基础镜像 |
| 25 | `docker.io/library/alpine:3.10` | Alpine基础镜像 |
| 26 | `docker.io/library/busybox:1.36.0` | BusyBox |
| 27 | `docker.io/library/docker:23.0.4` | Docker-in-Docker |
| 28 | `docker.io/library/nginx:latest` | Nginx |
| 29 | `docker.io/prom/prometheus:v2.27.1` | Prometheus |
| 30 | `docker.io/prom/node-exporter:v1.5.0` | Node Exporter |
| 31 | `docker.io/grafana/grafana:9.5.20` | Grafana |
| 32 | `docker.io/kubernetesui/dashboard:v2.6.1` | K8s Dashboard |
| 33 | `docker.io/kubernetesui/metrics-scraper:v1.0.8` | Dashboard Metrics |
| 34 | `docker.io/istio/pilot:1.15.0` | Istio Pilot |
| 35 | `docker.io/istio/proxyv2:1.15.0` | Istio Proxy |
| 36 | `docker.io/volcanosh/vc-controller-manager:v1.7.0` | Volcano Controller |
| 37 | `docker.io/volcanosh/vc-scheduler:v1.7.0` | Volcano Scheduler |
| 38 | `docker.io/volcanosh/vc-webhook-manager:v1.7.0` | Volcano Webhook |
| 39 | `docker.io/kubeflow/training-operator:v1-8a066f9` | 训练Operator |
| 40 | `docker.io/nvidia/k8s-device-plugin:v0.11.0-ubuntu20.04` | GPU插件 |
| 41 | `docker.io/nvidia/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04` | GPU监控 |
| 42 | `docker.io/minio/minio:RELEASE.2023-04-20T17-56-55Z` | MinIO对象存储 |
| 43 | `docker.io/carlosedp/addon-resizer:v1.8.4` | 资源调整器 |
| 44 | `quay.io/prometheus-operator/prometheus-operator:v0.46.0` | Prometheus Operator |
| 45 | `quay.io/prometheus-operator/prometheus-config-reloader:v0.46.0` | Config Reloader |
| 46 | `docker.io/nvidia/cuda:latest`（如需要GPU） | CUDA基础镜像 |

---

## 二、阶段1：在联网机器上准备离线包

> **工作流**：对于每个组件，都遵循 **"先在已部署虚机上查版本 → 再在联网机器上下载匹配版本"** 的原则。

在**能够连接外网**的机器上执行以下所有操作，然后将文件通过 U 盘/移动硬盘拷贝到内网环境。

### 2.0 前置步骤：在已部署虚机上收集版本信息

> **重要**：先 SSH 到**已部署成功的麒麟V10虚机**上执行以下全部检查命令，记录输出结果。后续下载时严格按照这些版本号来，确保与虚机环境一致。

```bash
# ===== 在已部署成功的麒麟V10虚机上执行 =====
echo "==================== 版本信息收集 ===================="

echo ""
echo ">>> 操作系统版本"
cat /etc/os-release | head -5
uname -m  # 确认架构：x86_64 或 aarch64

echo ""
echo ">>> K8s 相关版本"
kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null
kubeadm version --short 2>/dev/null || kubeadm version 2>/dev/null
kubelet --version 2>/dev/null

echo ""
echo ">>> K8s Server 版本（集群中运行的实际版本）"
kubectl version --short 2>/dev/null | grep Server || kubectl version 2>/dev/null | grep Server

echo ""
echo ">>> 容器运行时版本"
containerd --version 2>/dev/null
runc --version 2>/dev/null
docker --version 2>/dev/null

echo ""
echo ">>> CNI 插件版本（查看已安装的二进制）"
ls /opt/cni/bin/ 2>/dev/null || ls /usr/libexec/cni/ 2>/dev/null
# 如有版本文件
cat /opt/cni/VERSION 2>/dev/null || true

echo ""
echo ">>> Flannel 版本（从 K8s DaemonSet 中获取）"
kubectl get daemonset -n kube-flannel kube-flannel-ds -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null && echo ""

echo ""
echo ">>> CoreDNS 版本（从 K8s Deployment 获取）"
kubectl get deployment -n kube-system coredns -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null && echo ""

echo ""
echo ">>> etcd 版本"
etcdctl version 2>/dev/null || \
kubectl get pod -n kube-system -l component=etcd -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null && echo ""

echo ""
echo ">>> K8s 核心组件镜像（kube-apiserver / controller-manager / scheduler / proxy）"
kubectl get pod -n kube-system -l component=kube-apiserver -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null && echo ""
kubectl get pod -n kube-system -l component=kube-controller-manager -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null && echo ""
kubectl get pod -n kube-system -l component=kube-scheduler -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null && echo ""
kubectl get pod -n kube-system -l k8s-app=kube-proxy -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null && echo ""

echo ""
echo ">>> 全部容器镜像清单（逐条列出，用于核对）"
crictl images --output table 2>/dev/null || crictl images 2>/dev/null
# 也输出摘要（镜像名:tag + 镜像ID）
crictl images -o json 2>/dev/null | jq -r '.images[] | "\(.repoTags[0] // "none")  ID=\(.id)"' 2>/dev/null || true

echo ""
echo ">>> 麒麟V10 已安装的 RPM（kubeadm 依赖检测用）"
rpm -qa | grep -E "iproute|conntrack|socat|ebtables|ethtool|ipset|nfs-utils|yum-utils|device-mapper|lvm2|iptables-services|container-selinux|kubernetes-cni" 2>/dev/null | sort

echo ""
echo "==================== 收集完毕，请保存以上输出 ===================="
```

### 2.1 目录结构规划

```bash
# 在联网机器上创建离线包目录
mkdir -p /opt/offline/{k8s-bin,cni,containerd,harbor,rpm,images}
cd /opt/offline
```

### 2.2 下载匹配版本的 K8s 二进制包（kubeadm / kubelet / kubectl）

```bash
cd /opt/offline/k8s-bin

# === 第一步：在已部署虚机上查看版本 ===
# kubectl version --client --short
# 例如输出：Client Version: v1.28.2
#
# kubeadm version --short
# 例如输出：kubeadm version: &version.Info{...GitVersion:"v1.28.2"...}
#
# kubelet --version
# 例如输出：Kubernetes v1.28.2

# === 第二步：设置版本号（替换为虚机实际版本）===
K8S_VERSION="v1.28.2"    # ← 改成上面查到的版本号

# 确认架构
ARCH=$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/')
echo "架构: ${ARCH}，K8s 版本: ${K8S_VERSION}"

# === 第三步：下载对应版本的二进制 ===
wget "https://dl.k8s.io/${K8S_VERSION}/bin/linux/${ARCH}/kubeadm"
wget "https://dl.k8s.io/${K8S_VERSION}/bin/linux/${ARCH}/kubelet"
wget "https://dl.k8s.io/${K8S_VERSION}/bin/linux/${ARCH}/kubectl"

chmod +x kubeadm kubelet kubectl

# 验证下载的版本
./kubectl version --client
./kubeadm version
```

### 2.3 下载匹配版本的 CNI 插件

```bash
cd /opt/offline/cni

# === 第一步：在已部署虚机上查看 CNI 插件版本 ===
# ls /opt/cni/bin/        # 看有哪些插件文件
# 或直接看已下载的安装包名：cni-plugins-linux-amd64-v1.1.1.tgz
# K8s 1.28 默认自带 CNI 版本通常为 v1.1.1
# 也可以看 K8s kubelet 日志中的 CNI 版本：
# journalctl -u kubelet | grep -i "cni" | head -5

# === 第二步：设置版本号（替换为虚机实际版本）===
CNI_VERSION="v1.1.1"    # ← 改成虚机上查到的版本号（K8s 1.28 常见为 v1.1.1）

# === 第三步：下载对应版本 ===
wget "https://github.com/containernetworking/plugins/releases/download/${CNI_VERSION}/cni-plugins-linux-${ARCH}-${CNI_VERSION}.tgz"

echo "CNI 插件 ${CNI_VERSION} 下载完成"
```

### 2.4 下载匹配版本的 containerd 和 runc

```bash
cd /opt/offline/containerd

# === 第一步：在已部署虚机上查看容器运行时版本 ===
# containerd --version
# 例如输出：containerd github.com/containerd/containerd 1.7.29
#
# runc --version
# 例如输出：runc version 1.1.12

# === 第二步：设置版本号（替换为虚机实际版本）===
CONTAINERD_VERSION="1.7.29"   # ← 改成虚机上 containerd --version 的版本号
RUNC_VERSION="v1.1.12"        # ← 改成虚机上 runc --version 的版本号

# === 第三步：下载对应版本 ===
wget "https://github.com/containerd/containerd/releases/download/v${CONTAINERD_VERSION}/containerd-${CONTAINERD_VERSION}-linux-${ARCH}.tar.gz"
wget "https://github.com/opencontainers/runc/releases/download/${RUNC_VERSION}/runc.${ARCH}"
chmod +x runc.${ARCH}

echo "containerd ${CONTAINERD_VERSION} + runc ${RUNC_VERSION} 下载完成"
```

### 2.5 下载 Harbor 离线安装包

```bash
cd /opt/offline/harbor

# === 第一步：在已部署虚机上查看 Harbor 版本（如果已安装）=====
# curl -s http://<harbor_ip>:88/api/v2.0/systeminfo | jq '.harbor_version' 2>/dev/null
# 或者：docker inspect harbor-core | grep HARBOR_VERSION 2>/dev/null
#
# 如果没有 Harbor 或想用新版，可以使用推荐版本 v2.11.1

# === 第二步：设置版本号 ===
HARBOR_VERSION="v2.11.1"    # ← 按需修改

# === 第三步：下载对应版本 ===
wget "https://github.com/goharbor/harbor/releases/download/${HARBOR_VERSION}/harbor-offline-installer-${HARBOR_VERSION}.tgz"

# 如果是 ARM64 架构（鲲鹏），Harbor 官方不含 arm，使用社区 ARM 构建：
# wget https://github.com/wise2c-devops/build-harbor-aarch64/releases/download/v2.13.0/harbor-offline-installer-aarch64-v2.13.0.tgz

echo "Harbor ${HARBOR_VERSION} 下载完成"
```

### 2.6 下载匹配版本的 Flannel CNI 部署 YAML

```bash
cd /opt/offline

# === 第一步：在已部署虚机上查看 Flannel 版本 ===
# kubectl get daemonset -n kube-flannel kube-flannel-ds -o jsonpath='{.spec.template.spec.containers[0].image}'
# 例如输出：ghcr.io/flannel-io/flannel:v0.28.4
#
# 从镜像 tag 提取版本号（去掉 v 前缀即为 release tag）
# 也可以直接看全部容器：
# kubectl get pods -n kube-flannel -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}'

# === 第二步：根据镜像 tag 提取版本号 ===
# 示例：镜像 ghcr.io/flannel-io/flannel:v0.28.4 → FLANNEL_VER="v0.28.4"
FLANNEL_VER="v0.28.4"    # ← 改成虚机上查到的 Flannel 版本号

# === 第三步：下载对应版本 yaml ===
# 注意：Flannel v0.24.0+ 版本可能不在 release 页面单独提供 yaml
# 优先从 raw.githubusercontent.com 下载对应 tag 的 yaml
FLANNEL_VER_NUM=$(echo "$FLANNEL_VER" | sed 's/^v//')  # 去掉 v 前缀，如 v0.28.4 → 0.28.4
wget "https://raw.githubusercontent.com/flannel-io/flannel/v${FLANNEL_VER_NUM}/Documentation/kube-flannel.yml" 2>/dev/null || \
wget "https://github.com/flannel-io/flannel/releases/download/${FLANNEL_VER}/kube-flannel.yml" 2>/dev/null || \
wget "https://raw.githubusercontent.com/flannel-io/flannel/master/Documentation/kube-flannel.yml"

echo "Flannel ${FLANNEL_VER} yaml 下载完成"

# 注意：如果虚机上用的是 ghcr.io/flannel-io/flannel:v0.28.4 这个镜像，
# 那在 kube-flannel.yml 中也要把镜像地址改成一致的。
# 后续导入 Harbor 后，再做镜像地址替换。
```

### 2.7 下载麒麟V10所需的 RPM 离线包（建议补齐，防止内网无 yum 源）

> **注意**：麒麟V10基于OpenEuler，一般自带本地yum源（ISO挂载）。如果内网目标机器确定有 yum 源，可跳过此步骤。但为保险起见建议下载。

```bash
cd /opt/offline/rpm

# === 第一步：在已部署虚机上查看已安装的依赖 RPM 版本 ===
rpm -qa --queryformat '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' \
    | grep -E "conntrack|socat|ebtables|ethtool|ipset|iproute|nfs-utils|device-mapper|lvm2|iptables|libseccomp" \
    | sort

# === 第二步：下载 RPM（使用 yumdownloader，即使已安装也能下载）===
# 先确保 yumdownloader 可用
yum install -y yum-utils

# yumdownloader --resolve 会自动下载所有依赖
yumdownloader --resolve --destdir=/opt/offline/rpm \
    conntrack-tools socat ebtables ethtool ipset \
    nfs-utils device-mapper-persistent-data lvm2 \
    iptables-services libseccomp

# 说明：
# - 用 yumdownloader 而非 yum install --downloadonly，因为后者不下载已装包
# - 麒麟V10 中 iproute 包已包含 tc，无需单独 iproute-tc
# - fuse-overlayfs、slirp4netns 是 rootless 容器依赖，kubeadm 不需要，忽略
# - container-selinux 在麒麟V10 中通常不提供，也无需
# - 部分包可能提示 "No matching package"，跳过即可

ls -la rpm/
echo "RPM 包总计: $(ls rpm/*.rpm 2>/dev/null | wc -l) 个"
```

### 2.8 从用户虚机导出全部容器镜像

> 在**已部署成功的虚机（麒麟V10）**上执行，将全部镜像打包导出。

```bash
# === 在已部署成功的虚机上执行 ===

# 第一步：查看并确认所有镜像
echo ">>> 当前所有容器镜像："
crictl images

# 第二步：导出全部镜像
mkdir -p /opt/offline/images

# 方法1：使用 nerdctl（推荐，containerd 环境）
nerdctl -n k8s.io images --format '{{.Repository}}:{{.Tag}}' | while read img; do
    if [ "$img" != "REPOSITORY:TAG" ] && [ -n "$img" ]; then
        filename=$(echo "$img" | tr '/:' '_')
        echo "Saving $img ..."
        nerdctl -n k8s.io save "$img" -o "/opt/offline/images/${filename}.tar"
    fi
done

# 方法2：如果 nerdctl 不可用，用 ctr
# crictl images -o json | jq -r '.images[] | .repoTags[0]' | while read img; do
#     if [ -n "$img" ] && [ "$img" != "null" ]; then
#         filename=$(echo "$img" | tr '/:' '_')
#         echo "Saving $img ..."
#         ctr -n k8s.io image export "/opt/offline/images/${filename}.tar" "$img"
#     fi
# done

# 第三步：打包所有镜像为一个压缩包
cd /opt/offline
echo ">>> 打包中，文件较大请耐心等待..."
tar -czf cube-studio-all-images.tar.gz images/
ls -lh cube-studio-all-images.tar.gz

echo ">>> 镜像导出完成！"
echo ">>> 镜像总数：$(ls images/*.tar | wc -l)"
echo ">>> 打包文件：/opt/offline/cube-studio-all-images.tar.gz"
```

### 2.9 最终离线包清单

拷贝以下文件到移动存储设备，带去内网环境：

```
/opt/offline/
├── k8s-bin/
│   ├── kubeadm          # K8s（与虚机版本一致）
│   ├── kubelet          # K8s（与虚机版本一致）
│   └── kubectl          # K8s（与虚机版本一致）
├── cni/
│   └── cni-plugins-linux-*.tgz     # CNI 插件（与虚机版本一致）
├── containerd/
│   ├── containerd-*.tar.gz         # containerd（与虚机版本一致）
│   └── runc.*                      # runc（与虚机版本一致）
├── harbor/
│   └── harbor-offline-installer-*.tgz
├── rpm/                            # 麒麟V10 RPM依赖包（必须补齐，不能为空）
├── kube-flannel.yml                # Flannel CNI 部署文件
├── cube-studio-master.zip          # CubeStudio 项目源码（可选，也可单独拷贝）
└── cube-studio-all-images.tar.gz   # 全部容器镜像（直接从虚机导出）
```

> **版本校验清单**：在进入内网之前，建议对照 2.0 步骤的输出结果，逐一确认下载的版本与虚机一致。

### 2.10 离线包完整性自检（进内网前必须执行）

> **在联网机器上打包完成后、拷贝进内网之前**，执行以下脚本验证离线包是否完整可用。

```bash
cd /opt/offline
echo "==================== 离线包完整性自检 ===================="

ERRORS=0

# ---- 1. 检查 K8s 二进制 ----
echo ""
echo ">>> [1/8] 检查 K8s 二进制 (kubeadm/kubelet/kubectl)"
for bin in kubeadm kubectl kubelet; do
    if [ -f "k8s-bin/${bin}" ]; then
        echo "  ✅ k8s-bin/${bin} 存在 — 版本: $(./k8s-bin/${bin} version --client 2>/dev/null | head -1 || echo '无法检测')"
    else
        echo "  ❌ k8s-bin/${bin} 缺失！"
        ERRORS=$((ERRORS+1))
    fi
done

# ---- 2. 检查 CNI 插件 ----
echo ""
echo ">>> [2/8] 检查 CNI 插件"
CNI_TAR=$(ls cni/cni-plugins-*.tgz 2>/dev/null)
if [ -n "$CNI_TAR" ]; then
    echo "  ✅ ${CNI_TAR}"
    tar tzf "$CNI_TAR" | head -3
else
    echo "  ❌ cni/ 目录下未找到 cni-plugins-*.tgz！"
    ERRORS=$((ERRORS+1))
fi

# ---- 3. 检查 containerd + runc ----
echo ""
echo ">>> [3/8] 检查容器运行时 (containerd + runc)"
CTRD_TAR=$(ls containerd/containerd-*.tar.gz 2>/dev/null)
RUNC=$(ls containerd/runc.* 2>/dev/null)
[ -n "$CTRD_TAR" ] && echo "  ✅ ${CTRD_TAR}" || { echo "  ❌ containerd 缺失！"; ERRORS=$((ERRORS+1)); }
[ -n "$RUNC" ] && echo "  ✅ ${RUNC}" || { echo "  ❌ runc 缺失！"; ERRORS=$((ERRORS+1)); }

# ---- 4. 检查 Harbor ----
echo ""
echo ">>> [4/8] 检查 Harbor"
HARBOR_TAR=$(ls harbor/harbor-offline-installer-*.tgz 2>/dev/null)
[ -n "$HARBOR_TAR" ] && echo "  ✅ ${HARBOR_TAR}" || { echo "  ❌ Harbor 安装包缺失！"; ERRORS=$((ERRORS+1)); }

# ---- 5. 检查 Flannel yaml ----
echo ""
echo ">>> [5/8] 检查 Flannel yaml"
if [ -f "kube-flannel.yml" ]; then
    FLANNEL_IMG=$(grep 'image:.*flannel' kube-flannel.yml | grep -v cni-plugin | head -1 | awk '{print $2}')
    echo "  ✅ kube-flannel.yml 存在，其中 flannel 镜像: ${FLANNEL_IMG}"
    # 检查镜像中的版本号是否与实际 tar 包匹配
    FLANNEL_VER=$(echo "$FLANNEL_IMG" | grep -oP 'v?\d+\.\d+\.\d+')
    IMG_TAR=$(ls images/ghcr.io_flannel-io_flannel_*.tar images/*flannel* 2>/dev/null | head -1)
    if [ -n "$FLANNEL_VER" ] && [ -n "$IMG_TAR" ]; then
        echo "    镜像文件: ${IMG_TAR}"
        if echo "$IMG_TAR" | grep -q "$FLANNEL_VER"; then
            echo "    ✅ yaml 中版本 ${FLANNEL_VER} 与镜像文件匹配"
        else
            echo "    ⚠️  警告：yaml 版本 (${FLANNEL_VER}) 与镜像文件版本可能不一致，请核对！"
        fi
    fi
else
    echo "  ❌ kube-flannel.yml 缺失！"
    ERRORS=$((ERRORS+1))
fi

# ---- 6. 检查 RPM 目录 ----
echo ""
echo ">>> [6/8] 检查 RPM 目录"
RPM_COUNT=$(ls rpm/*.rpm 2>/dev/null | wc -l)
if [ "$RPM_COUNT" -gt 0 ]; then
    echo "  ✅ rpm/ 目录包含 ${RPM_COUNT} 个 RPM 包"
else
    echo "  ⚠️  rpm/ 目录为空！如果内网麒麟V10无 yum 源，需要补充以下依赖 RPM："
    echo "     conntrack-tools socat ebtables ethtool ipset nfs-utils device-mapper-persistent-data lvm2 iptables-services libseccomp"
    echo "     补充方法：在联网麒麟V10上执行"
    echo "     yumdownloader --resolve --destdir=rpm/ conntrack-tools socat ebtables ethtool ipset nfs-utils device-mapper-persistent-data lvm2 iptables-services libseccomp"
fi

# ---- 7. 检查镜像文件 ----
echo ""
echo ">>> [7/8] 检查容器镜像"
IMG_COUNT=$(ls images/*.tar 2>/dev/null | wc -l)
echo "  镜像 tar 文件数: ${IMG_COUNT}"

# 对照必备镜像列表检查
MUST_HAVE_IMAGES=(
    "kube-apiserver_v1.28" "kube-controller-manager_v1.28" "kube-scheduler_v1.28" "kube-proxy_v1.28"
    "coredns_v1.10" "etcd_3.5" "pause_3.9"
    "flannel_v0.28" "flannel-cni-plugin_v1.9"
    "mysql_8.0" "redis_7.4" "kubeflow-dashboard_2025" "kubeflow-dashboard-frontend_2025"
    "prometheus_v2.27" "grafana_9.5" "node-exporter_v1.5"
    "istio_pilot_1.15" "istio_proxyv2_1.15"
    "vc-controller-manager_v1.7" "vc-scheduler_v1.7" "vc-webhook-manager_v1.7"
    "training-operator_v1-8a066f9"
    "k8s-device-plugin_v0.11" "dcgm-exporter_3.1"
    "minio_RELEASE.2023" "addon-resizer_v1.8"
    "prometheus-operator_v0.46" "prometheus-config-reloader_v0.46"
    "argoexec_v3.4" "argocli_v3.4" "workflow-controller_v3.4"
    "k8s-dashboard_v2.6" "kube-rbac-proxy_0.14"
    "docker_23.0" "python_3.9" "ubuntu_20.04" "alpine_3.10" "busybox_1.36" "nginx_latest" "postgres_11.5"
    "notebook_jupyter-ubuntu22.04"
)
echo "  必备镜像检查（共 ${#MUST_HAVE_IMAGES[@]} 项）："
MISSING_IMGS=0
for pattern in "${MUST_HAVE_IMAGES[@]}"; do
    if ls images/*${pattern}* 1>/dev/null 2>&1; then
        : # 存在
    else
        echo "    ❌ 缺失: 包含 '${pattern}' 的镜像"
        MISSING_IMGS=$((MISSING_IMGS+1))
    fi
done
if [ "$MISSING_IMGS" -eq 0 ]; then
    echo "    ✅ 全部必备镜像已就绪"
else
    echo "    ❌ 共缺失 ${MISSING_IMGS} 个必备镜像"
    ERRORS=$((ERRORS+MISSING_IMGS))
fi

# ---- 8. 检查大文件打包 ----
echo ""
echo ">>> [8/8] 检查总打包文件"
if [ -f "cube-studio-all-images.tar.gz" ]; then
    SIZE=$(ls -lh cube-studio-all-images.tar.gz | awk '{print $5}')
    echo "  ✅ cube-studio-all-images.tar.gz 存在，大小: ${SIZE}"
else
    echo "  ⚠️  cube-studio-all-images.tar.gz 不存在（如果有 images/ 目录也可直接用 images/）"
fi

# ---- 汇总 ----
echo ""
echo "==================== 自检完成 ===================="
if [ "$ERRORS" -eq 0 ]; then
    echo "  ✅ 离线包完整性检查全部通过！"
elif [ "$ERRORS" -le 3 ]; then
    echo "  ⚠️  发现 ${ERRORS} 个问题（可能是非致命的），请确认后进入内网"
else
    echo "  ❌ 发现 ${ERRORS} 个严重问题，请补充缺失项后再进入内网！"
fi
```

---

## 三、阶段2：内网环境 — Kubernetes 1.28 集群搭建

> 以下操作在**内网离线环境的目标机器**上执行，每台机器都要操作（除非特别标注）。

### 3.0 节点角色规划（多机部署必读）

#### 3.0.1 集群拓扑

| 节点 | IP | 规格 | 角色 | 承载组件 |
|------|----|------|------|---------|
| **master (K8s主控)** | `10.208.173.121` | 16C / 30G | control-plane + worker | Harbor、K8s全部控制面、MySQL、Redis、Prometheus全家桶、Grafana、Istio ingressgateway、Argo、Volcano、CubeStudio全部微服务、K8s Dashboard |
| **worker-1** | `10.208.173.122` | 2C / 4G | worker | 业务负载 (Notebook、Pipeline、推理服务 等) |
| **worker-2** | `10.208.173.123` | 2C / 4G | worker | 业务负载 (Notebook、Pipeline、推理服务 等) |

> **说明**：2C4G 的 Worker 节点资源有限，仅承担少量业务 Pod。所有基础设施组件（20+ 个）全部放在 Master 节点。kubelet + containerd + Flannel 每个 Worker 约占用 1~1.5G 内存，剩余 ~2.5G 可用于业务 Pod。

#### 3.0.2 Harbor 部署位置

Harbor 是 Docker Compose 部署（独立于 K8s），建议放在 **Master 节点 (121)** 上，内存占用约 2~4G。Harbor 数据目录确保所在磁盘 > 200G。

#### 3.0.3 每台机器设置 hostname

```bash
# 10.208.173.121 上执行
hostnamectl set-hostname master

# 10.208.173.122 上执行
hostnamectl set-hostname worker-1

# 10.208.173.123 上执行
hostnamectl set-hostname worker-2

# 三台都配置 hosts（方便互访）
cat <<EOF >> /etc/hosts
10.208.173.121 master
10.208.173.122 worker-1
10.208.173.123 worker-2
EOF
```

#### 3.0.4 节点标签策略（Master 承担所有负载）

由于 Worker 节点资源极少，**Master 要去掉污点、同时承担 Worker 角色**，让基础设施 Pod 和业务 Pod 都能调度到 Master 上：

```bash
# 在 Master 节点上（kubeadm init 之后执行）：
# Master 默认有 taint: node-role.kubernetes.io/control-plane:NoSchedule
# 把以下基础设施组件的必备标签全部打给 master：
kubectl label node master \
    train=true cpu=true notebook=true service=true \
    org=public istio=true kubeflow=true kubeflow-dashboard=true \
    mysql=true redis=true monitoring=true logging=true --overwrite

# Worker 节点只打业务相关的轻量标签
kubectl label node worker-1 train=true cpu=true notebook=true service=true org=public --overwrite
kubectl label node worker-2 train=true cpu=true notebook=true service=true org=public --overwrite

# ★ 关键：去掉 Master 污点，使 Master 也能运行业务 Pod
kubectl taint node master node-role.kubernetes.io/control-plane:NoSchedule-
```

#### 3.0.5 部署顺序（多机版）

```
第三阶段：K8s 集群搭建
  ├─ 3.1 系统初始化                   【三台全部执行】
  ├─ 3.2 安装 containerd              【三台全部执行】
  ├─ 3.3 安装 kubeadm/kubelet/kubectl 【三台全部执行】
  ├─ 3.4 安装 Harbor                  【仅 Master (121) 执行】
  ├─ 3.5 推送镜像到 Harbor            【仅 Master (121) 执行】
  ├─ 3.6 配置 containerd 私有仓库     【三台全部执行】
  ├─ 3.7 kubeadm init                【仅 Master (121) 执行】
  ├─ 3.8 安装 Flannel CNI            【仅 Master (121) 执行】
  ├─ 3.9 Worker 加入集群              【Worker-1 (122) + Worker-2 (123) 执行】
  └─ 3.10 节点标签 + 去污点           【仅 Master (121) 执行】

第四阶段：CubeStudio 平台部署
  └─ 4.1 ~ 4.3 部署全部组件           【仅 Master (121) 执行】
```

```bash
# ===== 1. 关闭防火墙和 swap =====
systemctl stop firewalld
systemctl disable firewalld
systemctl stop iptables
systemctl disable iptables
systemctl stop ip6tables
systemctl disable ip6tables
systemctl stop nftables
systemctl disable nftables

swapoff -a
# 永久关闭 swap，编辑 /etc/fstab，注释掉 swap 行
sed -i '/swap/s/^/#/' /etc/fstab

# ===== 2. 配置内核参数 =====
cat <<EOF > /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF

sysctl --system

# ===== 3. 加载内核模块 =====
cat <<EOF > /etc/modules-load.d/k8s.conf
br_netfilter
ip_tables
iptable_nat
iptable_filter
iptable_mangle
EOF

modprobe br_netfilter
modprobe ip_tables
modprobe iptable_nat
modprobe iptable_filter
modprobe iptable_mangle

# ===== 4. 关闭 SELinux =====
setenforce 0
sed -i 's/^SELINUX=enforcing$/SELINUX=permissive/' /etc/selinux/config

# ===== 5. 防火墙配置（麒麟V10可能有firewalld） =====
# 修改 firewalld 后端为 iptables（如果使用）
sed -i 's/FirewallBackend=nftables/FirewallBackend=iptables/' /etc/firewalld/firewalld.conf 2>/dev/null || true

echo "初始化完成，建议重启机器：reboot"
```

### 3.2 安装 containerd 容器运行时（每台机器）

```bash
# ===== 1. 解压安装 containerd（版本号与离线包一致）=====
cd /opt/offline
# 先看下载的包实际叫什么名字（因为版本号来自虚机，文件名按实际匹配）
ls containerd/containerd-*.tar.gz
ls containerd/runc.*

# 解压 containerd
tar -C / -xzf containerd/containerd-*.tar.gz

# ===== 2. 安装 runc =====
cp containerd/runc.* /usr/local/sbin/runc
chmod +x /usr/local/sbin/runc

# ===== 3. 安装 CNI 插件（版本号与离线包一致）=====
mkdir -p /opt/cni/bin
# 先看下载的包实际叫什么名字
ls cni/cni-plugins-*.tgz
tar -C /opt/cni/bin -xzf cni/cni-plugins-*.tgz

# ===== 4. 创建 containerd 配置 =====
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml

# ===== 5. 修改 containerd 配置 =====
# 修改 sandbox_image 为私有仓库地址（后面会用到）
sed -i 's|sandbox_image = "registry.k8s.io/pause:3.8"|sandbox_image = "HARBOR_IP:PORT/cube-studio/pause:3.9"|g' /etc/containerd/config.toml
# 注意：等Harbor部署完成后，再改回正确的地址，现在先保持默认
# 如果后续用docker，可跳过containerd配置

# 启用 SystemdCgroup
sed -i 's|SystemdCgroup = false|SystemdCgroup = true|g' /etc/containerd/config.toml

# ===== 6. 创建 systemd 服务 =====
cat <<EOF > /etc/systemd/system/containerd.service
[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target local-fs.target

[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/local/bin/containerd
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
LimitNOFILE=infinity
TasksMax=infinity
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable containerd --now
systemctl status containerd
```

### 3.3 安装 kubeadm / kubelet / kubectl（每台机器）

```bash
cd /opt/offline/k8s-bin

# 安装 kubectl（所有节点）
cp kubectl /usr/local/bin/
chmod +x /usr/local/bin/kubectl

# 安装 kubeadm 和 kubelet（所有节点）
cp kubeadm /usr/local/bin/
cp kubelet /usr/local/bin/
chmod +x /usr/local/bin/kubeadm /usr/local/bin/kubelet

# 安装 crictl（kubeadm preflight 校验必须；不在 nerdctl-full 中，需单独下载）
# 联网机器下载：wget https://github.com/kubernetes-sigs/cri-tools/releases/download/v1.28.0/crictl-v1.28.0-linux-amd64.tar.gz -O /opt/offline/k8s-bin/crictl-v1.28.0-linux-amd64.tar.gz && cd /opt/offline/k8s-bin && tar -xzf crictl-v1.28.0-linux-amd64.tar.gz
cp /opt/offline/k8s-bin/crictl /usr/local/bin/ 2>/dev/null || true
chmod +x /usr/local/bin/crictl 2>/dev/null || true
crictl --version

# ===== 创建 kubelet systemd 服务 =====
cat <<EOF > /etc/systemd/system/kubelet.service
[Unit]
Description=kubelet: The Kubernetes Node Agent
Documentation=https://kubernetes.io/docs/
Wants=containerd.service
After=containerd.service

[Service]
ExecStart=/usr/local/bin/kubelet
Restart=always
StartLimitInterval=0
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 创建 kubelet 配置目录
mkdir -p /etc/kubernetes/manifests /var/lib/kubelet /var/lib/kubernetes

# 创建 kubeadm 初始化配置目录
mkdir -p /etc/kubernetes

systemctl daemon-reload
systemctl enable kubelet
```

### 3.4 安装 Harbor 私有镜像仓库（在 Harbor 节点上，仅1台）

> **选择一台机器部署Harbor**（建议独立机器，或与 Master 节点共用）。Harbor 依赖 Docker 或 Docker Compose，也可以使用 Harbor 自带的离线安装包（内置 docker-compose）。

```bash
cd /opt/offline/harbor

# 1. 解压 Harbor 离线包
tar -xzf harbor-offline-installer-v2.11.1.tgz -C /opt/
cd /opt/harbor

# 2. 复制并修改配置
cp harbor.yml.tmpl harbor.yml

# 3. 编辑 harbor.yml
vi harbor.yml
```

**`harbor.yml` 关键配置修改：**

```yaml
# Harbor 服务器的内网 IP
hostname: 10.208.173.121   # ← 改为你的 Harbor 机器 IP

# http 配置（离线环境通常不配 https，仅 http）
http:
  port: 88                # ← Harbor Web 端口，避开 80 冲突

# https 配置（离线环境注释掉）
# https:
#   port: 443
#   certificate: /your/certificate/path
#   private_key: /your/private/key/path

# Harbor 管理员密码
harbor_admin_password: Harbor12345

# 数据存储路径（确保该目录所在磁盘 > 200G）
data_volume: /data/harbor
```

```bash
# 4. 安装 Docker（如果 Harbor 机器上还没有 Docker，kylin V10 安装方式）
# 使用麒麟V10自带docker或离线RPM安装
yum install -y docker-ce 2>/dev/null || true

# 如无法安装，用已有二进制：
# 使用 nerdctl 或已有的容器运行时

# 5. 运行 Harbor 安装脚本
cd /opt/harbor
bash install.sh

# 6. 验证 Harbor 启动
docker ps | grep harbor  # 应看到多个 harbor 容器在运行
# 浏览器访问：http://10.208.173.121:88
# 用户名：admin，密码：Harbor12345
```

### 3.5 创建 Harbor 项目并推送镜像（在 Harbor 节点上）

```bash
# ===== 1. 登录 Harbor =====
docker login 10.208.173.121:88 -u admin -p Harbor12345
# 或 nerdctl login 10.208.173.121:88 -u admin -p Harbor12345

# ===== 2. 在 Harbor Web 界面创建以下项目（或通过 API 创建）=====
# 项目名称：cube-studio（存放 cube-studio 平台镜像）
# 项目名称：k8s-gcr（存放 K8s 核心组件镜像，如 kube-apiserver 等）
# 项目名称：library（存放通用基础镜像，如 mysql、redis、python 等）

# 通过 API 创建项目（需要 Harbor API）
HARBOR_URL="http://10.208.173.121:88"
curl -u admin:Harbor12345 -X POST "${HARBOR_URL}/api/v2.0/projects" \
  -H "Content-Type: application/json" \
  -d '{"project_name":"cube-studio","public":true}'

curl -u admin:Harbor12345 -X POST "${HARBOR_URL}/api/v2.0/projects" \
  -H "Content-Type: application/json" \
  -d '{"project_name":"k8s-gcr","public":true}'

curl -u admin:Harbor12345 -X POST "${HARBOR_URL}/api/v2.0/projects" \
  -H "Content-Type: application/json" \
  -d '{"project_name":"library","public":true}'

# ===== 3. 解压并导入镜像 =====
cd /opt/offline
tar -xzf cube-studio-all-images.tar.gz

# ===== 4. 批量重新打 tag 并推送到 Harbor =====
HARBOR_REGISTRY="10.208.173.121:88"

# 遍历所有镜像文件
for tar_file in /opt/offline/images/*.tar; do
    echo "Processing: $tar_file"
    docker load -i "$tar_file"
done

# 5. 重新 tag 并推送镜像（脚本）
docker images --format '{{.Repository}}:{{.Tag}}' | while read img; do
    # 跳过 <none> 镜像
    if [[ "$img" == *"<none>"* ]]; then
        continue
    fi

    # 根据原始镜像仓库分流到不同的 Harbor 项目
    if [[ "$img" == *"google_containers"* ]] || [[ "$img" == *"registry.k8s.io"* ]]; then
        # K8s 核心镜像 → k8s-gcr 项目
        short_name=$(echo "$img" | awk -F'/' '{print $NF}')
        new_tag="${HARBOR_REGISTRY}/k8s-gcr/${short_name}"
    elif [[ "$img" == *"cube-studio/"* ]] || [[ "$img" == *"cube-argoproj/"* ]]; then
        # CubeStudio 相关镜像 → cube-studio 项目
        short_name=$(echo "$img" | awk -F'/' '{print $NF}')
        new_tag="${HARBOR_REGISTRY}/cube-studio/${short_name}"
    else
        # 其他通用镜像 → library 项目
        short_name=$(echo "$img" | awk -F'/' '{print $NF}')
        new_tag="${HARBOR_REGISTRY}/library/${short_name}"
    fi

    echo "Tagging: $img → $new_tag"
    docker tag "$img" "$new_tag"
    echo "Pushing: $new_tag"
    docker push "$new_tag"
done

echo "所有镜像推送完成！"
```

### 3.6 配置所有节点使用 Harbor 私有仓库

> **每台机器（包括 Master 和 Worker 节点）都需要配置**

```bash
# ===== 方法1：使用 containerd =====
# 修改 /etc/containerd/config.toml
HARBOR_REGISTRY="10.208.173.121:88"

# 1. 修改 sandbox_image（pause 镜像地址）
sed -i "s|sandbox_image = .*|sandbox_image = \"${HARBOR_REGISTRY}/k8s-gcr/pause:3.9\"|g" /etc/containerd/config.toml

# 2. 添加 Harbor 镜像仓库认证配置
# 在 [plugins."io.containerd.grpc.v1.cri".registry.configs] 中增加
mkdir -p /etc/containerd/certs.d/${HARBOR_REGISTRY}
cat <<EOF > /etc/containerd/certs.d/${HARBOR_REGISTRY}/hosts.toml
server = "http://${HARBOR_REGISTRY}"

[host."http://${HARBOR_REGISTRY}"]
  capabilities = ["pull", "resolve"]
  skip_verify = true
EOF

# 3. 配置 containerd 使用 harbor 认证
# 在 config.toml 中修改（或创建 /etc/containerd/config.toml 的追加内容）
# 完整配置示例见下方

systemctl restart containerd

# ===== 方法2：如果使用 Docker =====
# 编辑 /etc/docker/daemon.json
cat <<EOF > /etc/docker/daemon.json
{
    "insecure-registries": ["10.208.173.121:88"],
    "exec-opts": ["native.cgroupdriver=systemd"],
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "100m",
        "max-file": "10"
    },
    "storage-driver": "overlay2",
    "storage-opts": ["overlay2.override_kernel_check=true"]
}
EOF
systemctl daemon-reload
systemctl restart docker
```

**完整的 containerd 私有仓库配置（`/etc/containerd/config.toml` 关键修改）：**

```toml
# 在 [plugins."io.containerd.grpc.v1.cri".registry] 部分

[plugins."io.containerd.grpc.v1.cri".registry]
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
    # 为 docker.io 配置 Harbor 代理
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
      endpoint = ["http://10.208.173.121:88"]
    # 为 registry.k8s.io 配置 Harbor 代理
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."registry.k8s.io"]
      endpoint = ["http://10.208.173.121:88"]
    # 为 ghcr.io 配置 Harbor 代理
    [plugins."io.containerd.grpc.v1.cri".registry.mirrors."ghcr.io"]
      endpoint = ["http://10.208.173.121:88"]

  [plugins."io.containerd.grpc.v1.cri".registry.configs]
    [plugins."io.containerd.grpc.v1.cri".registry.configs."10.208.173.121:88".tls]
      insecure_skip_verify = true
    [plugins."io.containerd.grpc.v1.cri".registry.configs."10.208.173.121:88".auth]
      username = "admin"
      password = "Harbor12345"
```

### 3.7 初始化 K8s Master 节点（在 Master 节点上）

```bash
# ===== 1. 创建 kubeadm 初始化配置 =====
HARBOR_REGISTRY="10.208.173.121:88"
MASTER_IP="10.208.173.121"   # ← 改为 Master 节点实际 IP
K8S_VERSION="v1.28.2"       # ← 改成第二阶段从虚机查到的 K8s 版本号

cat <<EOF > /etc/kubernetes/kubeadm-config.yaml
apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: ${MASTER_IP}
  bindPort: 6443
nodeRegistration:
  criSocket: unix:///var/run/containerd/containerd.sock
  name: master-node
  taints:
  - effect: NoSchedule
    key: node-role.kubernetes.io/control-plane
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: ${K8S_VERSION}
imageRepository: ${HARBOR_REGISTRY}/k8s-gcr
controlPlaneEndpoint: "${MASTER_IP}:6443"
networking:
  serviceSubnet: "10.96.0.0/12"
  podSubnet: "10.244.0.0/16"
  dnsDomain: "cluster.local"
apiServer:
  extraArgs:
    service-account-issuer: kubernetes.default.svc
    service-account-signing-key-file: /etc/kubernetes/pki/sa.key
  certSANs:
  - "${MASTER_IP}"
controllerManager:
  extraArgs:
    bind-address: "0.0.0.0"
scheduler:
  extraArgs:
    bind-address: "0.0.0.0"
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
failSwapOn: false
---
apiVersion: kubeproxy.config.k8s.io/v1alpha1
kind: KubeProxyConfiguration
mode: "iptables"
EOF

# ===== 2. 预拉取 K8s 核心镜像（从 Harbor）=====
kubeadm config images pull --config /etc/kubernetes/kubeadm-config.yaml

# ===== 3. 初始化 Master 节点 =====
kubeadm init --config /etc/kubernetes/kubeadm-config.yaml --upload-certs

# ===== 4. 配置 kubectl =====
mkdir -p $HOME/.kube
cp /etc/kubernetes/admin.conf $HOME/.kube/config
chown $(id -u):$(id -g) $HOME/.kube/config

# ===== 5. 验证节点状态 =====
kubectl get nodes
# 此时节点状态应为 NotReady（因为还没有安装 CNI 网络插件）

# ===== 6. 保存 join 命令（后续 Worker 节点加入使用）=====
kubeadm token create --print-join-command > /root/kubeadm-join-command.sh
chmod +x /root/kubeadm-join-command.sh
echo "Join 命令已保存到 /root/kubeadm-join-command.sh"
```

### 3.8 安装 Flannel CNI 网络插件（在 Master 节点上）

```bash
# ===== 1. 先查看 Flannel 镜像在 Harbor 中的实际名称 =====
cd /opt/offline

# 从已部署虚机确认了 Flannel 版本（如 ghcr.io/flannel-io/flannel:v0.28.4）
# 在 kube-flannel.yml 中将镜像地址替换为 Harbor
FLANNEL_IMAGE_TAG="v0.28.4"    # ← 改成第二阶段从虚机查到的 Flannel 版本号
HARBOR_REGISTRY="10.208.173.121:88"

# 替换 yaml 中所有 flannel 镜像地址为 Harbor
sed -i "s|image: .*flannel.*|image: ${HARBOR_REGISTRY}/library/flannel:${FLANNEL_IMAGE_TAG}|g" kube-flannel.yml

# 同步替换 flannel-cni-plugin 镜像（如果有）
sed -i "s|image: .*flannel-cni-plugin.*|image: ${HARBOR_REGISTRY}/library/flannel-cni-plugin:v1.9.1-flannel1|g" kube-flannel.yml

# ===== 2. 应用 Flannel =====
kubectl apply -f kube-flannel.yml

# ===== 3. 等待所有系统 Pod 运行 =====
kubectl get pods -n kube-flannel
kubectl get pods -n kube-system

# ===== 4. 等待 Master 节点变为 Ready =====
watch kubectl get nodes
# 等待 STATUS 从 NotReady 变为 Ready（通常 30~60 秒）
```

### 3.9 Worker 节点加入集群（在每个 Worker 节点上）

```bash
# ===== 在 Worker 节点上执行（节点层面已完成 3.1 ~ 3.3 + 3.6 的配置）=====

# 使用之前保存的 join 命令
# 如果 join 命令过期（token 24 小时有效），在 Master 节点重新生成：
# kubeadm token create --print-join-command

bash /root/kubeadm-join-command.sh

# 或者直接执行：
# kubeadm join 10.208.173.121:6443 --token xxxxx \
#     --discovery-token-ca-cert-hash sha256:xxxxx
```

在 **Master 节点**上验证：

```bash
kubectl get nodes
# 所有节点 State 应为 Ready

kubectl get pods -A
# 所有系统 Pod 应为 Running 状态
```

---

## 四、阶段3：CubeStudio 平台离线部署

> K8s 集群就绪后，开始部署 CubeStudio MLOps 平台。

### 4.1 准备部署脚本

```bash
# 进入 CubeStudio 部署目录
cd /opt/cube-studio-master/install/kubernetes

# 复制 kubeconfig
mkdir -p ~/.kube && cp /etc/kubernetes/admin.conf ~/.kube/config
mkdir -p kubeconfig && echo "" > kubeconfig/dev-kubeconfig
```

### 4.2 修改镜像地址为 Harbor（关键步骤）

#### 4.2.1 修改 kustomization.yml

编辑 `cube/overlays/kustomization.yml`：

```bash
vi cube/overlays/kustomization.yml
```

修改 `images` 部分，将 `ccr.ccs.tencentyun.com/cube-studio/` 替换为 Harbor 地址：

```yaml
images:
- name: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard
  newName: 10.208.173.121:88/cube-studio/kubeflow-dashboard
  newTag: 2025.03.01
- name: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend
  newName: 10.208.173.121:88/cube-studio/kubeflow-dashboard-frontend
  newTag: 2025.03.01
```

#### 4.2.2 修改配置文件 config.py

```bash
vi cube/overlays/config/config.py
```

修改以下关键配置项（将 `ccr.ccs.tencentyun.com/cube-studio/` 替换为 `10.208.173.121:88/cube-studio/`）：

```python
# 私有仓库的组织名，修改为自己的内网 Harbor
REPOSITORY_ORG = '10.208.173.121:88/cube-studio/'
PUSH_REPOSITORY_ORG = '10.208.173.121:88/cube-studio/'

# 用户默认镜像
USER_IMAGE = '10.208.173.121:88/cube-studio/ubuntu-gpu:cuda11.8.0-cudnn8-python3.9'

# notebook 镜像
NOTEBOOK_IMAGES = [
    ['10.208.173.121:88/cube-studio/notebook:vscode-ubuntu-cpu-base', 'vscode（cpu）'],
    # ... 其他 notebook 镜像同样修改地址
]

# 推理服务镜像
INFERNENCE_IMAGES = {
    "tfserving": ['10.208.173.121:88/cube-studio/tfserving:2.14.1-gpu', ...],
    "torch-server": ['10.208.173.121:88/cube-studio/torchserve:0.9.0-gpu', ...],
    # ... 其他推理镜像同样修改
}

# docker/nni/wait-pod 镜像
DOCKER_IMAGES = '10.208.173.121:88/cube-studio/docker:23.0.4'
NERDCTL_IMAGES = '10.208.173.121:88/cube-studio/nerdctl:1.7.2'
NNI_IMAGES = '10.208.173.121:88/cube-studio/nni:20240501'
WAIT_POD_IMAGES = '10.208.173.121:88/cube-studio/wait-pod:v1'

# 内网服务 IP
SERVICE_EXTERNAL_IP = ['10.208.173.121']  # 内网 Master/入口 IP
```

#### 4.2.3 修改所有 K8s YAML 中的镜像地址（批量替换）

```bash
cd /opt/cube-studio-master/install/kubernetes

# 批量替换所有 YAML 文件中的腾讯云镜像地址为 Harbor 地址
HARBOR_REGISTRY="10.208.173.121:88"

find . -type f \( -name "*.yaml" -o -name "*.yml" \) -exec sed -i \
  -e "s|ccr.ccs.tencentyun.com/cube-studio/|${HARBOR_REGISTRY}/cube-studio/|g" \
  -e "s|ccr.ccs.tencentyun.com/cube-argoproj/|${HARBOR_REGISTRY}/cube-studio/|g" \
  -e "s|ccr.ccs.tencentyun.com/cube-rancher/|${HARBOR_REGISTRY}/cube-studio/|g" \
  -e "s|docker.io/library/mysql:8.0.32|${HARBOR_REGISTRY}/library/mysql:8.0.32|g" \
  -e "s|docker.io/library/redis:7.4|${HARBOR_REGISTRY}/library/redis:7.4|g" \
  -e "s|docker.io/library/python:3.9|${HARBOR_REGISTRY}/library/python:3.9|g" \
  -e "s|docker.io/library/docker:23.0.4|${HARBOR_REGISTRY}/library/docker:23.0.4|g" \
  -e "s|docker.io/library/nginx:latest|${HARBOR_REGISTRY}/library/nginx:latest|g" \
  -e "s|docker.io/library/alpine:3.10|${HARBOR_REGISTRY}/library/alpine:3.10|g" \
  -e "s|docker.io/library/busybox:1.36.0|${HARBOR_REGISTRY}/library/busybox:1.36.0|g" \
  -e "s|docker.io/library/ubuntu:20.04|${HARBOR_REGISTRY}/library/ubuntu:20.04|g" \
  -e "s|docker.io/library/postgres:11.5|${HARBOR_REGISTRY}/library/postgres:11.5|g" \
  -e "s|docker.io/nvidia/k8s-device-plugin:v0.11.0-ubuntu20.04|${HARBOR_REGISTRY}/library/k8s-device-plugin:v0.11.0-ubuntu20.04|g" \
  -e "s|docker.io/nvidia/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04|${HARBOR_REGISTRY}/library/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04|g" \
  -e "s|docker.io/minio/minio:RELEASE.2023-04-20T17-56-55Z|${HARBOR_REGISTRY}/library/minio:RELEASE.2023-04-20T17-56-55Z|g" \
  -e "s|docker.io/carlosedp/addon-resizer:v1.8.4|${HARBOR_REGISTRY}/library/addon-resizer:v1.8.4|g" \
  -e "s|docker.io/kubernetesui/dashboard:v2.6.1|${HARBOR_REGISTRY}/library/dashboard:v2.6.1|g" \
  -e "s|docker.io/kubernetesui/metrics-scraper:v1.0.8|${HARBOR_REGISTRY}/library/metrics-scraper:v1.0.8|g" \
  -e "s|quay.io/prometheus-operator/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|ghcr.io/flannel-io/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|registry.cn-hangzhou.aliyuncs.com/google_containers/|${HARBOR_REGISTRY}/k8s-gcr/|g" \
  -e "s|registry.k8s.io/|${HARBOR_REGISTRY}/k8s-gcr/|g" \
  -e "s|docker.io/prom/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/grafana/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/istio/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/volcanosh/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/kubeflow/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/nvidia/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/minio/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/carlosedp/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/kubernetesui/|${HARBOR_REGISTRY}/library/|g" \
  -e "s|docker.io/library/|${HARBOR_REGISTRY}/library/|g" \
  {} +

echo "镜像地址批量替换完成！"
```

### 4.3 初始化节点并部署 CubeStudio

```bash
cd /opt/cube-studio-master/install/kubernetes

# ===== 1. 节点初始化（创建数据目录、关闭防火墙等）=====
bash init_node.sh

# ===== 2. kubectl 已安装（离线包中已拷贝），跳过 wget 步骤 =====
# 确认版本
kubectl version --client --short

# ===== 3. 创建命名空间 =====
for ns in infra kubeflow istio-system pipeline automl jupyter service monitoring logging kube-system aihub; do
    kubectl create ns $ns --dry-run=client -o yaml | kubectl apply -f -
done

# ===== 4. 创建镜像拉取 Secret（关联 Harbor 认证）=====
for ns in infra kubeflow istio-system pipeline automl jupyter service monitoring logging kube-system aihub; do
    kubectl delete secret docker-registry hubsecret -n $ns --ignore-not-found=true
    kubectl create secret docker-registry hubsecret \
        --docker-server="${HARBOR_REGISTRY}" \
        --docker-username=admin \
        --docker-password=Harbor12345 \
        -n $ns
    kubectl label ns $ns istio-injection=disabled --overwrite
done
kubectl label ns service istio-injection-

# ===== 5. 部署 K8s Dashboard =====
kubectl apply -f dashboard/v2.6.1-cluster.yaml
kubectl apply -f dashboard/v2.6.1-user.yaml

# ===== 6. 部署 MySQL =====
kubectl create -f mysql/pv-pvc-hostpath.yaml
kubectl create -f mysql/service.yaml
kubectl create -f mysql/configmap-mysql.yaml
kubectl create -f mysql/deploy.yaml

# ===== 7. 部署 Redis =====
kubectl create -f redis/redis.yaml

# ===== 8. 部署 Prometheus 监控全家桶 =====
cd prometheus
kubectl apply -f ./operator/operator-crd.yml
kubectl apply -f ./operator/operator-rbac.yml
kubectl wait crd/podmonitors.monitoring.coreos.com --for condition=established --timeout=60s
kubectl apply -f ./operator/operator-dp.yml
kubectl apply -f ./node-exporter/node-exporter-sa.yml
kubectl apply -f ./node-exporter/node-exporter-rbac.yml
kubectl apply -f ./node-exporter/node-exporter-svc.yml
kubectl apply -f ./node-exporter/node-exporter-ds.yml
kubectl apply -f ./node-exporter/node-exporter-sm.yml
kubectl apply -f ./grafana/pv-pvc-hostpath.yml
kubectl apply -f ./grafana/grafana-sa.yml
kubectl apply -f ./grafana/grafana-source.yml
kubectl apply -f ./grafana/grafana-datasources.yml
kubectl apply -f ./grafana/grafana-admin-secret.yml
kubectl apply -f ./grafana/grafana-svc.yml
kubectl delete configmap grafana-config all-grafana-dashboards --namespace=monitoring --ignore-not-found=true
kubectl create configmap grafana-config --from-file=./grafana/grafana.ini --namespace=monitoring
kubectl create configmap all-grafana-dashboards --from-file=./grafana/dashboard --namespace=monitoring
kubectl apply -f ./grafana/grafana-dp.yml
kubectl apply -f ./service-discovery/kube-controller-manager-svc.yml
kubectl apply -f ./service-discovery/kube-scheduler-svc.yml
kubectl apply -f ./prometheus/prometheus-secret.yml
kubectl apply -f ./prometheus/prometheus-rules.yml
kubectl apply -f ./prometheus/prometheus-rbac.yml
kubectl apply -f ./prometheus/prometheus-svc.yml
kubectl wait crd/prometheuses.monitoring.coreos.com --for condition=established --timeout=60s
kubectl apply -f ./prometheus/pv-pvc-hostpath.yaml
kubectl apply -f ./prometheus/prometheus-main.yml
# ServiceMonitor
kubectl apply -f ./servicemonitor/
cd ..

# ===== 9. GPU 插件（有 GPU 的节点）=====
kubectl apply -f gpu/nvidia-device-plugin.yml
kubectl apply -f gpu/dcgm-exporter.yaml

# ===== 10. 部署 Volcano 批调度 =====
kubectl apply -f volcano/volcano-development.yaml
kubectl wait crd/jobs.batch.volcano.sh --for condition=established --timeout=60s

# ===== 11. 部署 Istio 服务网格 =====
kubectl apply -f istio/install-crd.yaml
kubectl wait crd/envoyfilters.networking.istio.io --for condition=established --timeout=60s
kubectl apply -f istio/install-1.15.0.yaml
kubectl wait crd/virtualservices.networking.istio.io --for condition=established --timeout=60s
kubectl wait crd/gateways.networking.istio.io --for condition=established --timeout=60s
kubectl apply -f gateway.yaml
kubectl apply -f virtual.yaml

# ===== 12. 部署 Argo Workflow 引擎 =====
kubectl apply -f argo/minio-pv-pvc-hostpath.yaml
kubectl apply -f argo/pipeline-runner-rolebinding.yaml
kubectl apply -f argo/install-3.4.3-all.yaml

# ===== 13. 部署 Kubeflow 训练 Operator =====
kubectl apply -f kubeflow/sa-rbac.yaml
kubectl apply -k kubeflow/train-operator/manifests/overlays/standalone

# ===== 14. 创建 ConfigMap（K8s 配置）=====
kubectl delete configmap kubernetes-config -n infra --ignore-not-found=true
kubectl create configmap kubernetes-config --from-file=kubeconfig -n infra
kubectl delete configmap kubernetes-config -n pipeline --ignore-not-found=true
kubectl create configmap kubernetes-config --from-file=kubeconfig -n pipeline
kubectl delete configmap kubernetes-config -n automl --ignore-not-found=true
kubectl create configmap kubernetes-config --from-file=kubeconfig -n automl

# ===== 15. 创建持久化存储 PV/PVC =====
kubectl create -f pv-pvc-infra.yaml
kubectl create -f pv-pvc-jupyter.yaml
kubectl create -f pv-pvc-automl.yaml
kubectl create -f pv-pvc-pipeline.yaml
kubectl create -f pv-pvc-service.yaml

# ===== 16. 修改内网 IP =====
MASTER_IP="10.208.173.121"   # ← 改为实际内网 IP
sed -i "s/SERVICE_EXTERNAL_IP=\[\]/SERVICE_EXTERNAL_IP=\[\"${MASTER_IP}\"\]/g" cube/overlays/config/config.py

# ===== 17. 部署 CubeStudio 平台本体 =====
kubectl apply -f sa-rbac.yaml
kubectl delete -k cube/overlays --ignore-not-found=true
sleep 3
kubectl apply -k cube/overlays

# ===== 18. 配置外部入口 IP =====
kubectl patch svc istio-ingressgateway -n istio-system \
    -p "{\"spec\":{\"externalIPs\":[\"${MASTER_IP}\"]}}"

echo "============================================"
echo "  CubeStudio 部署完成！"
echo "  访问地址：http://${MASTER_IP}"
echo "  默认账号：admin / admin"
echo "============================================"
```

---

## 五、阶段4：部署后验证与问题排查

### 5.1 部署状态检查清单

```bash
# 1. 检查所有节点状态
kubectl get nodes
# 预期：所有节点 STATUS=Ready

# 2. 检查所有 Pod 运行状态
kubectl get pods -A | grep -v Running | grep -v Completed
# 预期：没有输出（即所有 Pod 都是 Running 或 Completed）

# 3. 检查 CubeStudio 核心 Pod
kubectl get pods -n infra
# 预期看到：kubeflow-dashboard-xxx, kubeflow-dashboard-frontend-xxx,
#           kubeflow-dashboard-schedule-xxx, kubeflow-dashboard-worker-xxx,
#           kubeflow-watch-xxx

# 4. 检查关键命名空间 Pod
kubectl get pods -n istio-system
kubectl get pods -n kubeflow
kubectl get pods -n monitoring
kubectl get pods -n volcano-system

# 5. 检查服务入口
kubectl get svc -n istio-system istio-ingressgateway
# 确认 EXTERNAL-IP 是否正确

# 6. 浏览器访问
# http://<MASTER_IP>
# 默认账号：admin
# 默认密码：admin
```

### 5.2 常见问题解决

#### 问题1：kubeadm init 时报镜像拉取失败

```bash
# 确认 containerd 配置中的 sandbox_image 和 registry mirrors 正确
crictl pull 10.208.173.121:88/k8s-gcr/kube-apiserver:v1.28.2

# 如果失败，手动拉取
ctr -n k8s.io images pull 10.208.173.121:88/k8s-gcr/kube-apiserver:v1.28.2
```

#### 问题2：Flannel Pod CrashLoopBackOff

```bash
# 查看 Flannel Pod 日志
kubectl logs -n kube-flannel daemonset/kube-flannel-ds

# 常见原因：podSubnet 与实际配置不匹配
# 确认 kubeadm-config.yaml 中 podSubnet 与 kube-flannel.yml 中 net-conf.json 一致
# 默认 Flannel 使用 10.244.0.0/16

# 如果机器有多网卡，需要在 kube-flannel.yml 中指定网卡
# 添加 args: ["--iface=eth0"]
```

#### 问题3：CoreDNS Pending

```bash
# CoreDNS 需要 CNI 网络就绪后才能调度
# 确认 Flannel Pod 已 Running
kubectl get pods -n kube-flannel

# 如果长时间 Pending，检查节点是否有污点
kubectl describe node | grep Taint
```

#### 问题4：Harbor 推送镜像 413/unknown blob 错误

```bash
# 增加 Harbor Nginx 上传大小限制
# 在 Harbor 的 common/config/nginx/nginx.conf 中修改
client_max_body_size 0;

# 重启 Harbor
cd /opt/harbor && docker-compose down && docker-compose up -d
```

#### 问题5：麒麟V10 防火墙/iptables 报错

```bash
# 麒麟V10 默认使用 nftables，但 kube-proxy 使用 iptables
# 解决方法：切换到 iptables 并关闭防火墙
systemctl stop firewalld
systemctl disable firewalld
systemctl stop nftables
systemctl disable nftables

# 或者配置 kube-proxy 使用 ipvs 模式
# 在 kubeadm-config.yaml 中：
#   mode: "ipvs"
# 同时安装 ipvsadm：yum install -y ipvsadm
```

#### 问题6：containerd 拉取镜像超时

```bash
# 确认 Harbor 在 containerd 的配置正确
# cat /etc/containerd/config.toml | grep -A 10 registry

# 测试是否可以连接 Harbor
curl -u admin:Harbor12345 http://10.208.173.121:88/v2/_catalog

# 如果 Harbor 认证有问题，使用 ctr 命令测试
ctr -n k8s.io images pull --plain-http \
    --user admin:Harbor12345 \
    10.208.173.121:88/k8s-gcr/pause:3.9
```

---

## 六、镜像版本对照表（快速参考）

以下是项目中所有组件的版本和对应 Harbor 镜像地址速查表：

| 组件 | 原始镜像 | Harbor 镜像（示例） |
|------|---------|-------------------|
| kube-apiserver | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-apiserver:v1.28.2` | `10.208.173.121:88/k8s-gcr/kube-apiserver:v1.28.2` |
| kube-controller-manager | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-controller-manager:v1.28.2` | `10.208.173.121:88/k8s-gcr/kube-controller-manager:v1.28.2` |
| kube-scheduler | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-scheduler:v1.28.2` | `10.208.173.121:88/k8s-gcr/kube-scheduler:v1.28.2` |
| kube-proxy | `registry.cn-hangzhou.aliyuncs.com/google_containers/kube-proxy:v1.28.2` | `10.208.173.121:88/k8s-gcr/kube-proxy:v1.28.2` |
| coredns | `registry.cn-hangzhou.aliyuncs.com/google_containers/coredns:v1.10.1` | `10.208.173.121:88/k8s-gcr/coredns:v1.10.1` |
| etcd | `registry.cn-hangzhou.aliyuncs.com/google_containers/etcd:3.5.9-0` | `10.208.173.121:88/k8s-gcr/etcd:3.5.9-0` |
| pause | `registry.cn-hangzhou.aliyuncs.com/google_containers/pause:3.9` | `10.208.173.121:88/k8s-gcr/pause:3.9` |
| Flannel | `ghcr.io/flannel-io/flannel:v0.28.4` | `10.208.173.121:88/library/flannel:v0.28.4` |
| Flannel CNI Plugin | `ghcr.io/flannel-io/flannel-cni-plugin:v1.9.1-flannel1` | `10.208.173.121:88/library/flannel-cni-plugin:v1.9.1-flannel1` |
| K8s Dashboard | `ccr.ccs.tencentyun.com/cube-studio/k8s-dashboard:v2.6.1` | `10.208.173.121:88/cube-studio/k8s-dashboard:v2.6.1` |
| Dashboard（官方） | `docker.io/kubernetesui/dashboard:v2.6.1` | `10.208.173.121:88/library/dashboard:v2.6.1` |
| MySQL | `docker.io/library/mysql:8.0.32` | `10.208.173.121:88/library/mysql:8.0.32` |
| Redis | `ccr.ccs.tencentyun.com/cube-studio/redis:7.4` | `10.208.173.121:88/cube-studio/redis:7.4` |
| Prometheus | `docker.io/prom/prometheus:v2.27.1` | `10.208.173.121:88/library/prometheus:v2.27.1` |
| Grafana | `docker.io/grafana/grafana:9.5.20` | `10.208.173.121:88/library/grafana:9.5.20` |
| Istio Pilot | `docker.io/istio/pilot:1.15.0` | `10.208.173.121:88/library/pilot:1.15.0` |
| Istio Proxy | `docker.io/istio/proxyv2:1.15.0` | `10.208.173.121:88/library/proxyv2:1.15.0` |
| Argo CLI | `ccr.ccs.tencentyun.com/cube-argoproj/argocli:v3.4.3` | `10.208.173.121:88/cube-studio/argocli:v3.4.3` |
| Argo Executor | `ccr.ccs.tencentyun.com/cube-argoproj/argoexec:v3.4.3` | `10.208.173.121:88/cube-studio/argoexec:v3.4.3` |
| Argo Controller | `ccr.ccs.tencentyun.com/cube-argoproj/workflow-controller:v3.4.3` | `10.208.173.121:88/cube-studio/workflow-controller:v3.4.3` |
| Volcano Manager | `docker.io/volcanosh/vc-controller-manager:v1.7.0` | `10.208.173.121:88/library/vc-controller-manager:v1.7.0` |
| Volcano Scheduler | `docker.io/volcanosh/vc-scheduler:v1.7.0` | `10.208.173.121:88/library/vc-scheduler:v1.7.0` |
| Volcano Webhook | `docker.io/volcanosh/vc-webhook-manager:v1.7.0` | `10.208.173.121:88/library/vc-webhook-manager:v1.7.0` |
| Training Operator | `docker.io/kubeflow/training-operator:v1-8a066f9` | `10.208.173.121:88/library/training-operator:v1-8a066f9` |
| GPU Plugin | `docker.io/nvidia/k8s-device-plugin:v0.11.0-ubuntu20.04` | `10.208.173.121:88/library/k8s-device-plugin:v0.11.0-ubuntu20.04` |
| DCGM Exporter | `docker.io/nvidia/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04` | `10.208.173.121:88/library/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04` |
| MinIO | `docker.io/minio/minio:RELEASE.2023-04-20T17-56-55Z` | `10.208.173.121:88/library/minio:RELEASE.2023-04-20T17-56-55Z` |
| Docker (DinD) | `docker.io/library/docker:23.0.4` | `10.208.173.121:88/library/docker:23.0.4` |
| CubeStudio 后端 | `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2025.03.01` | `10.208.173.121:88/cube-studio/kubeflow-dashboard:2025.03.01` |
| CubeStudio 前端 | `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2025.03.01` | `10.208.173.121:88/cube-studio/kubeflow-dashboard-frontend:2025.03.01` |

---

## 七、快速命令速查

```bash
# ===== 日常运维常用命令 =====

# 查看集群状态
kubectl get nodes -o wide
kubectl top nodes
kubectl get pods -A -o wide

# 查看 CubeStudio 日志
kubectl logs -n infra deploy/kubeflow-dashboard --tail=100 -f
kubectl logs -n infra deploy/kubeflow-dashboard-frontend --tail=100 -f

# 重启 CubeStudio
kubectl rollout restart deploy/kubeflow-dashboard -n infra
kubectl rollout restart deploy/kubeflow-dashboard-frontend -n infra

# 进入 MySQL
kubectl exec -it -n infra deploy/mysql-deploy -- mysql -uroot -padmin

# 查看 Istio 入口
kubectl get svc -n istio-system istio-ingressgateway

# 重新生成 Join Token（24h过期后）
kubeadm token create --print-join-command

# 导出所有 K8s 资源备份
kubectl get all -A -o yaml > k8s-backup-$(date +%Y%m%d).yaml
```

---

## 八、总结

本方案实现了**完全离线、不使用 Rancher、使用 kubeadm** 在麒麟V10 上部署 K8s 1.28 + CubeStudio MLOps 平台的完整链路：

| 阶段 | 关键操作 | 产物 |
|------|---------|------|
| **阶段1（联网机器）** | 下载二进制包 + 导出镜像 | 离线包 U 盘 |
| **阶段2.1~2.6（内网）** | 系统初始化 + 安装容器运行时 | 所有节点就绪 |
| **阶段2.7（内网）** | 部署 Harbor 私有仓库 + 导入镜像 | 内网镜像仓库可用 |
| **阶段2.8~2.10（内网）** | kubeadm init + 安装 Flannel + 加入 Worker | K8s 集群就绪 |
| **阶段3（内网）** | 修改 YAML 镜像地址 + 部署 CubeStudio | 平台上线 |

**核心优势**：
1. **无需 Rancher**：直接用 kubeadm 初始化集群，减少一层依赖和复杂度
2. **全离线**：所有二进制、镜像、RPM 包均预先打包，内网零外网依赖
3. **麒麟V10适配**：系统初始化、iptables 配置均针对 Kylin V10 优化
4. **Harbor 统一管理**：所有镜像推送到 Harbor，后续升级和新节点加入只需从 Harbor 拉取
5. **可复制性强**：标准化脚本化流程，支持批量部署和扩容