# 离线部署方案修正说明

## 文档对比分析

对比文件：
- 待修正文档：`离线部署方案-kubeadm-kylinV10.md`
- 参考文档：
  - `install/kubernetes/offline.md`（官方离线部署指南）
  - `install/kubernetes/all_image.py`（镜像清单脚本）
  - `install/kubernetes/rancher/install_containerd.md`（containerd安装指南）
  - `cube-studio.wiki/内网离线部署.md`（内网部署Wiki）
  - `cube-studio.wiki/平台单机部署.md`（单机部署Wiki）

---

## 主要问题与修正

### 1. 镜像版本不一致

**问题**：文档中的镜像版本与官方 `all_image.py` 不匹配

**当前文档中的版本**：
- `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2025.03.01`
- `ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2025.03.01`

**官方 all_image.py 中的版本**：
```python
cube_studio = [
    'ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01',
    'ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.03.01',
]
```

**修正**：将所有 `2025.03.01` 改为 `2026.03.01`

---

### 2. Harbor 版本建议更新

**问题**：文档使用 Harbor v2.11.1，但官方文档推荐更新版本

**官方 offline.md 推荐**：
- amd64: `harbor-offline-installer-v2.11.1.tgz`
- arm64: `harbor-offline-installer-aarch64-v2.13.0.tgz`

**修正**：
- amd64 保持 v2.11.1（正确）
- arm64 应使用 v2.13.0（文档未明确区分）

---

### 3. 镜像清单不完整

**问题**：文档中的53个镜像清单缺少部分官方必需镜像

**官方 all_image.py 中包含但文档缺失的镜像**：
```python
# Kubernetes Dashboard
'kubernetesui/dashboard:v2.6.1'
'kubernetesui/metrics-scraper:v1.0.8'

# GPU 支持（如需要）
'nvidia/k8s-device-plugin:v0.11.0-ubuntu20.04'
'nvidia/dcgm-exporter:3.1.7-3.1.4-ubuntu20.04'

# Prometheus 监控（如需要）
'prom/prometheus:v2.27.1'
'prom/node-exporter:v1.5.0'
'grafana/grafana:9.5.20'

# Istio（必需）
'istio/proxyv2:1.15.0'
'istio/pilot:1.15.0'

# Volcano 调度器（可选）
'volcanosh/vc-controller-manager:v1.7.0'
'volcanosh/vc-scheduler:v1.7.0'
'volcanosh/vc-webhook-manager:v1.7.0'

# Training Operator
'kubeflow/training-operator:v1-8a066f9'

# 基础镜像
'busybox:1.36.0'
'alpine:3.10'
```

**修正**：补充完整镜像清单，并按功能分类

---

### 4. containerd 配置不完整

**问题**：文档中 containerd 配置缺少关键参数

**官方 install_containerd.md 中的完整配置**：
```toml
# 1. SystemdCgroup 必须设置为 true（文档已有，正确）
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc.options]
  SystemdCgroup = true

# 2. config_path 配置（文档已有，正确）
[plugins."io.containerd.grpc.v1.cri".registry]
  config_path = "/etc/containerd/certs.d"

# 3. CNI 配置（文档缺失）
[plugins."io.containerd.grpc.v1.cri".cni]
  conf_dir = "/etc/cni/net.d"
  bin_dir = "/opt/cni/bin"
```

**修正**：补充 CNI 配置段

---

### 5. 镜像导出导入流程不规范

**问题**：文档中镜像导出使用单个 tar.gz，不符合官方推荐

**官方 all_image.py 生成的脚本**：
```bash
# 官方推荐：每个镜像单独保存为 .tar.gz
docker pull <image> && docker save <image> | gzip > <image-name>.tar.gz

# 导入时：
gunzip -c <image-name>.tar.gz | docker load
```

**文档中的方式**：
```bash
# 所有镜像打包为一个 cube-studio-all-images.tar.gz
docker save $(docker images --format '{{.Repository}}:{{.Tag}}') | gzip > cube-studio-all-images.tar.gz
```

**修正建议**：
- 方式1（推荐）：使用官方脚本 `image_save.sh` 和 `image_load.sh`，每个镜像单独保存
- 方式2（简化）：保持当前方式，但需说明这是简化方案，大规模部署建议用方式1

---

### 6. Harbor 镜像推送脚本问题

**问题**：文档中的镜像 tag 转换逻辑不完整

**文档中的脚本**：
```bash
if [[ "$img" == *"google_containers"* ]] || [[ "$img" == *"registry.k8s.io"* ]]; then
    new_tag="${HARBOR_REGISTRY}/k8s-gcr/${short_name}"
elif [[ "$img" == *"cube-studio/"* ]] || [[ "$img" == *"cube-argoproj/"* ]]; then
    new_tag="${HARBOR_REGISTRY}/cube-studio/${short_name}"
else
    new_tag="${HARBOR_REGISTRY}/library/${short_name}"
fi
```

**官方 all_image.py 中的逻辑**：
```python
# 官方使用更精确的替换规则
new_image = harbor_repo + image.replace('ccr.ccs.tencentyun.com/cube-studio/', '').replace('/', '-')
```

**问题点**：
1. 文档脚本未处理 `ghcr.io/flannel-io/` 等特殊仓库
2. 未处理 `docker.io/library/` 前缀
3. 镜像名中的 `/` 未转换为 `-`

**修正**：提供更完善的 tag 转换脚本

---

### 7. CubeStudio 部署配置缺失

**问题**：文档缺少 CubeStudio 部署时的关键配置修改步骤

**官方 offline.md 中的必需步骤**：
```bash
# 1. 修改 kustomization.yml 中的镜像地址
vi install/kubernetes/cube/overlays/kustomization.yml
# 修改最底部的 newName 和 newTag

# 2. 修改 config.py 中的仓库地址
vi install/kubernetes/cube/overlays/config/config.py
# 修改以下变量为内网仓库地址：
# REPOSITORY_ORG
# PUSH_REPOSITORY_ORG
# USER_IMAGE
# NOTEBOOK_IMAGES
# DOCKER_IMAGES
# NERDCTL_IMAGES
# NNI_IMAGES
# WAIT_POD_IMAGES
# INFERNENCE_IMAGES

# 3. 修改 SERVICE_EXTERNAL_IP
SERVICE_EXTERNAL_IP = ['内网ip|外网ip']

# 4. 修改 DEFAULT_GPU_RESOURCE_NAME（如无 GPU）
DEFAULT_GPU_RESOURCE_NAME = 'cpu'  # 或保持默认
```

**修正**：在阶段三中补充完整的配置修改步骤

---

### 8. init_node.sh 脚本修改说明不清晰

**问题**：文档未明确说明如何修改 init_node.sh

**官方 offline.md 中的说明**：
```bash
# 修改 init_node.sh 中的镜像拉取脚本
# 将 pull_images.sh 改为 pull_harbor.sh
vi install/kubernetes/init_node.sh

# 查找并替换：
# sh pull_images.sh  →  sh pull_harbor.sh
```

**修正**：补充具体的修改命令和验证步骤

---

### 9. kubectl 下载地址不准确

**问题**：文档中 kubectl 下载使用 `dl.k8s.io`，但官方推荐使用 OSS 镜像

**官方 offline.md 和 平台单机部署.md 中的地址**：
```bash
# amd64
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl

# arm64
wget https://cube-studio.oss-cn-hangzhou.aliyuncs.com/install/kubectl-arm64
```

**修正**：提供两种下载方式（官方 + OSS 镜像）

---

### 10. 缺少 kubeconfig 文件配置说明

**问题**：文档未说明如何配置 kubeconfig 文件用于 CubeStudio 部署

**官方 平台单机部署.md 中的说明**：
```bash
# 将 k8s 集群的 kubeconfig 文件复制到指定位置
cp ~/.kube/config install/kubernetes/kubeconfig/

# 对于双网卡，需要在 rancher 中切换 current-context 为内网连接
```

**修正**：在阶段三部署 CubeStudio 前补充此步骤

---

### 11. Flannel 部署 YAML 地址错误

**问题**：文档中 Flannel YAML 下载地址可能失效

**文档中的地址**：
```bash
wget https://github.com/flannel-io/flannel/releases/download/v0.28.4/kube-flannel.yml
```

**建议修正**：
```bash
# 方式1：使用 GitHub 加速
wget https://githubfast.com/flannel-io/flannel/releases/download/v0.28.4/kube-flannel.yml

# 方式2：从已部署虚机导出
kubectl get -n kube-flannel daemonset kube-flannel-ds -o yaml > kube-flannel.yml
```

---

### 12. 系统初始化步骤不完整

**问题**：文档中系统初始化缺少部分关键步骤

**官方 install_containerd.md 和 rancher 文档中的完整步骤**：
```bash
# 1. 关闭 swap（文档已有）
swapoff -a
sed -i '/swap/s/^/#/' /etc/fstab

# 2. 关闭 SELinux（文档已有）
setenforce 0
sed -i 's/^SELINUX=enforcing$/SELINUX=disabled/' /etc/selinux/config

# 3. 关闭防火墙（文档已有）
systemctl stop firewalld
systemctl disable firewalld

# 4. 配置 iptables（文档已有）
cat <<EOF > /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF
sysctl --system

# 5. 加载内核模块（文档缺失）
modprobe br_netfilter
modprobe overlay

# 6. 配置内核参数（文档缺失部分参数）
cat <<EOF >> /etc/sysctl.d/k8s.conf
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
vm.swappiness = 0
EOF
sysctl --system
```

**修正**：补充缺失的内核模块加载步骤

---

### 13. Harbor 数据目录规划建议

**问题**：文档未说明 Harbor 数据目录的磁盘空间要求

**建议补充**：
```bash
# Harbor 数据目录磁盘空间建议：
# - 小规模（< 50 个镜像）：100G
# - 中规模（50-200 个镜像）：500G
# - 大规模（> 200 个镜像）：1T+

# 检查磁盘空间
df -h /data/harbor

# 如空间不足，可修改 harbor.yml 中的 data_volume 指向更大的磁盘
```

---

### 14. 缺少镜像拉取策略配置

**问题**：文档未说明离线环境下需要修改镜像拉取策略

**官方 offline.md 和 内网离线部署.md 中的说明**：
```bash
# 将 infra 命名空间下 deployment 拉取策略改为 IfNotPresent
kubectl patch deployment -n infra kubeflow-dashboard -p '{"spec":{"template":{"spec":{"containers":[{"name":"kubeflow-dashboard","imagePullPolicy":"IfNotPresent"}]}}}}'

# 同时修改配置文件
vi install/kubernetes/cube/overlays/config/config.py
# 添加或修改：
IMAGE_PULL_POLICY = 'IfNotPresent'
```

**修正**：在阶段三部署后补充此配置

---

### 15. 缺少 Web 界面配置修改说明

**问题**：文档未说明部署后需要在 Web 界面进行的配置

**官方 offline.md 中的说明**：
```bash
# 1. 修改 hubsecret 为内网仓库账号密码
# 路径：在线开发 -> 镜像仓库 -> 编辑 hubsecret

# 2. 添加企业自己的镜像仓库
# 路径：在线开发 -> 镜像仓库 -> 添加
# 填写内网 Harbor 地址和账号密码

# 3. 修改示例 Pipeline 中的数据拉取命令
# 将 wget https://... 改为 cp /mnt/admin/offline/...

# 4. 修改推理服务启动命令
# 将 wget https://... 改为 cp /mnt/admin/offline/...
```

**修正**：在阶段四补充 Web 界面配置章节

---

## 建议的文档结构调整

### 当前结构问题：
1. 阶段划分不够清晰（联网机器 vs 内网机器操作混在一起）
2. 缺少验证步骤
3. 缺少故障排查章节

### 建议的新结构：

```
一、方案架构总览
二、前置准备（联网机器操作）
  2.1 环境信息收集
  2.2 下载 K8s 二进制包
  2.3 下载 CNI 插件
  2.4 下载 containerd
  2.5 下载 Harbor
  2.6 下载麒麟 V10 RPM 包
  2.7 导出镜像
  2.8 打包离线包
三、内网环境部署（内网机器操作）
  3.1 系统初始化（所有节点）
  3.2 安装容器运行时（所有节点）
  3.3 安装 K8s 组件（所有节点）
  3.4 部署 Harbor（Harbor 节点）
  3.5 导入镜像到 Harbor
  3.6 配置私有仓库（所有节点）
  3.7 初始化 K8s 集群（Master 节点）
  3.8 部署 Flannel（Master 节点）
  3.9 加入 Worker 节点
  3.10 验证集群状态
四、部署 CubeStudio
  4.1 准备 kubeconfig
  4.2 修改镜像地址
  4.3 修改配置文件
  4.4 执行部署
  4.5 验证部署
  4.6 Web 界面配置
五、验证与测试
  5.1 创建测试 Notebook
  5.2 运行测试 Pipeline
  5.3 部署测试推理服务
六、故障排查
  6.1 镜像拉取失败
  6.2 Pod 无法启动
  6.3 网络不通
  6.4 存储问题
七、常用运维命令
八、总结
```

---

## 具体修正建议

### 修正优先级：

**P0（必须修正）**：
1. 镜像版本更新为 2026.03.01
2. 补充完整镜像清单
3. 补充 containerd CNI 配置
4. 补充 CubeStudio 配置修改步骤
5. 补充镜像拉取策略配置

**P1（强烈建议）**：
6. 优化镜像导出导入流程
7. 完善 Harbor 镜像推送脚本
8. 补充 kubeconfig 配置说明
9. 补充 Web 界面配置说明
10. 补充验证步骤

**P2（建议优化）**：
11. 调整文档结构
12. 补充故障排查章节
13. 优化脚本可读性
14. 补充 Harbor 磁盘空间建议
15. 提供多种下载方式

---

## 下一步行动

建议按以下顺序修正：

1. **立即修正**：P0 级别问题（影响部署成功率）
2. **短期修正**：P1 级别问题（影响部署体验）
3. **长期优化**：P2 级别问题（提升文档质量）

是否需要我生成修正后的完整文档？
