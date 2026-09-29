# CubeStudio离线部署操作手册 — 新环境（3Master + 2Worker + Harbor）

---

## 一、部署概况

| 项目 | 说明 |
|------|------|
| K8s版本 | v1.28.2，kubeadm部署，Harbor作为集群内镜像仓库 |
| 容器运行时/网络 | Containerd 1.7.29 / Flannel v0.28.4 |
| 操作内容 | 前置检查 → 环境准备 → NFS → Containerd → Harbor(镜像仓库) → K8s → Flannel → CubeStudio |
| 集群规模 | 3 Master + 2 Worker（共5台） |

### 回退决策条件

1. K8s节点异常超过2个无法恢复时，执行 `kubeadm reset` 回退
2. 初始化失败时，`kubeadm reset -f` 后重新初始化
3. 部署时间超过预期窗口时，由负责人决策是否回退

---

## 二、服务器规划

| IP地址 | 主机名 | 角色 | 备注 |
|--------|--------|------|------|
| 192.168.11.11 | k8s-master1 | Master | K8s控制平面主节点 |
| 192.168.11.12 | k8s-master2 | Master + Harbor | **Harbor部署于此节点** |
| 192.168.11.13 | k8s-master3 | Master | |
| 192.168.11.14 | k8s-worker1 | Worker | |
| 192.168.11.15 | k8s-worker2 | Worker | |

---

## 三、软件版本

| 组件 | 版本 | 说明 |
|------|------|------|
| Kubernetes | 1.28.2 | kubeadm部署，3Master+2Worker |
| Containerd | 1.7.29 | 容器运行时 |
| CNI Plugins | 1.1.1 | 网络插件基础组件 |
| Flannel | v0.28.4 | CNI网络插件 |
| Harbor | 2.11.1 | 集群内镜像仓库（部署于Master-2：192.168.11.12） |
| CubeStudio | 2026.03.01 | 前后端 |

---

## 四、物料清单（/data/offline/）

| 目录/文件 | 说明 | 节点数 |
|-----------|------|--------|
| nerdctl-full-1.7.6-linux-amd64.tar.gz | Nerdctl完整包（含containerd/buildkit等） | 5 |
| k8s-bin/ | kubeadm、kubelet、kubectl | 5 |
| cni/ | cni-plugins-linux-amd64-v1.1.1.tgz | 5 |
| containerd/ | containerd-1.7.29 + runc.amd64 | 5 |
| harbor/ | harbor-offline-installer-v2.11.1.tgz | 1（Master-2） |
| images/ | 容器镜像.tar文件（54个） | 5 |
| model/ | coco.zip、resnet50等模型文件 | 5 |
| cube-studio-master.zip | CubeStudio源码 | 1（Master-1） |
| kube-flannel.yml | Flannel部署YAML文件 | 1（Master-1） |
| nfsrpm.tar.gz | NFS相关RPM包 | 5 |
| rpm-new-kilin/ | Kylin V10离线RPM包（Docker） | 1（Master-2） |

---

## 五、部署步骤

### 阶段一：准备阶段（所有节点：192.168.11.11/12/13/14/15）

> **执行用户：root**

#### 步骤1 — 前置检查

```bash
# 系统版本
cat /etc/redhat-release
uname -r

# 资源
nproc
free -g | grep Mem
df -h /

# 网络（从每台机器ping其他4台）
for ip in 192.168.11.11 192.168.11.12 192.168.11.13 192.168.11.14 192.168.11.15; do
  ping -c 2 $ip
done

# 端口检查（K8s关键端口，应无输出）
netstat -tunlp | grep -E ':(6443|2379|2380|10250|10251|10252|10255)'

# 旧环境检查
ps aux | grep -E 'kube|etcd' | grep -v grep
ls -la /etc/kubernetes/ 2>/dev/null
systemctl status firewalld --no-pager
systemctl status iptables --no-pager
getenforce
```

**验证：** 系统正常，所有IP可达，关键端口未占用，无旧K8s残留。

---

#### 步骤2 — 设置主机名

```bash
# 各服务器分别执行：
# 192.168.11.11 → hostnamectl set-hostname k8s-master1
# 192.168.11.12 → hostnamectl set-hostname k8s-master2
# 192.168.11.13 → hostnamectl set-hostname k8s-master3
# 192.168.11.14 → hostnamectl set-hostname k8s-worker1
# 192.168.11.15 → hostnamectl set-hostname k8s-worker2
```

**验证：** `hostname` 确认主机名已更改。

---

#### 步骤3 — 配置hosts文件

```bash
cp /etc/hosts /etc/hosts.bak

cat > /etc/hosts << 'EOF'
127.0.0.1   localhost localhost.localdomain
::1         localhost localhost.localdomain

192.168.11.11 k8s-master1
192.168.11.12 k8s-master2
192.168.11.13 k8s-master3
192.168.11.14 k8s-worker1
192.168.11.15 k8s-worker2
EOF
```

**验证：** `cat /etc/hosts`

---

#### 步骤4 — 关闭防火墙与SELinux

```bash
systemctl stop firewalld && systemctl disable firewalld
systemctl stop iptables 2>/dev/null
setenforce 0
sed -i 's/^SELINUX=enforcing/SELINUX=disabled/' /etc/selinux/config
```

**验证：** `getenforce` → Disabled；`systemctl status firewalld` → inactive

---

#### 步骤5 — 关闭swap

```bash
swapoff -a
cp /etc/fstab /etc/fstab.bak
sed -i '/swap/s/^/#/' /etc/fstab
```

**验证：** `free -h | grep Swap` → 应为0

---

#### 步骤6 — 配置内核参数及内核模块

```bash
yum install -y yum-utils device-mapper-persistent-data lvm2
yum install -y iptables container-selinux iptables-services

yum localinstall -y *.rpm --allowerasing

# 写入rc.local（防火墙禁用+内核模块加载）
(
cat << EOF
systemctl stop firewalld
systemctl disable firewalld
systemctl stop iptables
systemctl disable iptables
systemctl stop ip6tables
systemctl disable ip6tables
systemctl stop nftables
systemctl disable nftables

modprobe br_netfilter
modprobe ip_tables
modprobe iptable_nat
modprobe iptable_filter
modprobe iptable_mangle
modprobe ip6_tables
modprobe ip6table_nat
modprobe ip6table_filter
modprobe ip6table_mangle
EOF
) >> /etc/rc.d/rc1.local
chmod +x /etc/rc.d/rc1.local
sh /etc/rc.d/rc1.local

echo 'ip_tables' >> /etc/modules

echo "net.bridge.bridge-nf-call-ip6tables = 1" >> /etc/sysctl.conf
echo "net.bridge.bridge-nf-call-iptables=1" >> /etc/sysctl.conf
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
echo "1" > /proc/sys/net/bridge/bridge-nf-call-iptables
sysctl -p

systemctl restart docker 2>/dev/null
reboot
```

**验证（重启后）：**
```bash
getenforce                    # Disabled
systemctl status firewalld    # inactive
lsmod | grep br_netfilter     # 已加载
sysctl net.ipv4.ip_forward    # 1
```

---

### 阶段二：NFS共享存储（所有节点）

#### 步骤7 — 配置NFS

**NFS Server（仅 Master-1：192.168.11.11）：**
```bash
mkdir -p /bdm/share_bdm
echo "/bdm/share_bdm *(rw,no_root_squash,async)" >> /etc/exports
exportfs -arv
systemctl enable rpcbind nfs-server --now
```

**NFS Client（Master-2/3、Worker-1/2）：**
```bash
showmount -e 192.168.11.11
mkdir -p /bdm/share_bdm
echo "192.168.11.11:/bdm/share_bdm  /bdm/share_bdm   nfs   defaults   0   0" >> /etc/fstab
mount -a
```

**验证：**
- Server端：`showmount -e localhost`
- Client端：`showmount -e 192.168.11.11`；`df -h | grep nfs`

---

### 阶段三：Containerd安装与配置（所有节点）

#### 步骤8 — 安装Containerd + runc + CNI插件

```bash
# 解压nerdctl-full（含containerd、buildkit等）
tar -xzf /bdm/share_bdm/nerdctl-full-1.7.6-linux-amd64.tar.gz -C /usr/local/

# 安装runc
install -m 755 /bdm/share_bdm/containerd/runc.amd64 /usr/local/sbin/runc

# 安装CNI插件
mkdir -p /opt/cni/bin
tar -xzf /bdm/share_bdm/cni/cni-plugins-linux-amd64-v1.1.1.tgz -C /opt/cni/bin/

# 复制systemd服务文件并修改buildkit
cp /usr/local/lib/systemd/system/*.service /etc/systemd/system/
# 修改 /etc/systemd/system/buildkit.service 的 ExecStart 为：
# ExecStart=/usr/local/bin/buildkitd --oci-worker=false --containerd-worker=true
```

**验证：**
```bash
ls /usr/local/bin/containerd
ls /usr/local/sbin/runc
ls /opt/cni/bin/
```

---

#### 步骤9 — 配置Containerd

```bash
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml

# 修改 /etc/containerd/config.toml 关键改动：
# 1. sandbox_image = "192.168.11.12/cube-studio/google_containers/pause:3.8"
# 2. SystemdCgroup = true
# 3. config_path = "/etc/containerd/certs.d"
# 4. root = "/bdm/containerd"（将containerd存储目录改到数据盘）

# 创建docker.io镜像源hosts
mkdir -p /etc/containerd/certs.d/docker.io
tee /etc/containerd/certs.d/docker.io/hosts.toml << 'EOF'
server = "https://docker.io"
[host."https://docker.1panel.live"]
  capabilities = ["pull", "resolve"]
[host."https://hub.rat.dev/"]
  capabilities = ["pull", "resolve"]
[host."https://docker.chenby.cn"]
  capabilities = ["pull", "resolve"]
[host."https://docker.m.daocloud.io"]
  capabilities = ["pull", "resolve"]
EOF

# 如果忘记修改为数据盘
mkdir -p /bdm/containerd
vi /etc/containerd/config.toml
rsync -av /var/lib/containerd/ /bdm/containerd/
systemctl restart containerd
```

**验证：**
```bash
cat /etc/containerd/config.toml | grep -E "sandbox_image|SystemdCgroup|config_path"
cat /etc/containerd/certs.d/docker.io/hosts.toml
```

---

#### 步骤10 — 配置Harbor镜像源（Harbor部署后再执行）

```bash
mkdir -p /etc/containerd/certs.d/192.168.11.12
cat > /etc/containerd/certs.d/192.168.11.12/hosts.toml << 'EOF'
server = "http://192.168.11.12"
[host."http://192.168.11.12"]
  capabilities = ["pull", "resolve", "push"]
  skip_verify = true
EOF
```

**验证：** `cat /etc/containerd/certs.d/192.168.11.12/hosts.toml`

---

#### 步骤11 — 启动Containerd

```bash
systemctl daemon-reload
systemctl enable containerd buildkit --now
systemctl status containerd
```

**验证：** `systemctl status containerd` → active (running)；`ctr version`

---

**验证：** `ctr -n k8s.io images ls | wc -l` → 54

---

### 阶段四：Harbor镜像仓库（仅Master-2：192.168.11.12）

#### 步骤13 — 安装Docker（Harbor依赖）

```bash
cd /docker
rpm -ivh docker-ce-*.rpm docker-ce-cli-*.rpm containerd.io-*.rpm docker-compose-plugin-*.rpm --nodeps 2>/dev/null

mkdir -p /bdm/docker
mkdir -p /etc/docker

cat > /etc/docker/daemon.json << 'EOF'
{
  "data-root": "/bdm/docker",
  "insecure-registries": ["192.168.11.12"],
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerproxy.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  }
}
EOF

systemctl enable docker --now
```

**验证：** `docker version`；`docker ps`

---

#### 步骤14 — 安装Harbor

```bash
cd /data/offline/harbor
tar -xzf harbor-offline-installer-v2.11.1.tgz -C /opt/
cd /opt/harbor
cp harbor.yml.tmpl harbor.yml

# 修改harbor.yml关键项：
# hostname: 192.168.11.12
# http.port: 80
# https注释掉（内网使用http）
# harbor_admin_password: Harbor12345
# data_volume: /bdm/harbor

./install.sh
```

**验证：**
```bash
docker ps | grep harbor
curl http://192.168.11.12/api/v2.0/health
# 默认账号 admin / Harbor12345
```

---

#### 步骤15 — 推送镜像到Harbor

```bash
docker login 192.168.11.12 -u admin -p Harbor12345

# 创建cube-studio项目（公开）
curl -u admin:Harbor12345 -X POST http://192.168.11.12/api/v2.0/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name":"cube-studio","public":true}'

# docker load所有镜像
for f in /bdm/share_bdm/images/*.tar; do
  docker load -i "$f"
done

for img in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>' | grep -v '192.168.11.12'); do
  clean_name=$(echo "$img" | sed -E 's|^[^/]*\.[^/]+/||')
  clean_name=$(echo "$clean_name" | sed 's|^cube-studio/||')
  new_tag="192.168.11.12/cube-studio/$clean_name"
  echo "Push: $img -> $new_tag"
  docker tag "$img" "$new_tag"
  docker push "$new_tag"
done
```

**验证：**
```bash
docker images | wc -l
curl -u admin:Harbor12345 http://192.168.11.12/api/v2.0/projects
```

---

### 阶段五：K8s集群部署

#### 步骤16 — 安装crictl（所有节点）

```bash
tar -xzf /bdm/share_bdm/crictl-v1.28.0-linux-amd64.tar.gz -C /usr/local/bin/
crictl version
```

---

#### 步骤17 — 安装K8s二进制文件（所有节点）

```bash
cd /bdm/share_bdm/k8s-bin/
install -m 755 kubeadm /usr/bin/kubeadm
install -m 755 kubelet /usr/bin/kubelet
install -m 755 kubectl /usr/bin/kubectl
```

**验证：**
```bash
kubeadm version
kubelet --version
kubectl version --client
```

---

#### 步骤18 — 配置kubelet服务（所有节点）

```bash
cat > /etc/systemd/system/kubelet.service << 'EOF'
[Unit]
Description=kubelet: The Kubernetes Node Agent
Wants=network-online.target
After=network-online.target
[Service]
ExecStart=/usr/bin/kubelet
Restart=always
StartLimitInterval=0
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

mkdir -p /etc/systemd/system/kubelet.service.d
cat > /etc/systemd/system/kubelet.service.d/10-kubeadm.conf << 'EOF'
[Service]
Environment="KUBELET_KUBECONFIG_ARGS=--bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf"
Environment="KUBELET_CONFIG_ARGS=--config=/var/lib/kubelet/config.yaml"
EnvironmentFile=-/var/lib/kubelet/kubeadm-flags.env
EnvironmentFile=-/etc/default/kubelet
ExecStart=
ExecStart=/usr/bin/kubelet $KUBELET_KUBECONFIG_ARGS $KUBELET_CONFIG_ARGS $KUBELET_KUBEADM_ARGS $KUBELET_EXTRA_ARGS
EOF

systemctl daemon-reload
systemctl enable kubelet
```

**验证：** `systemctl status kubelet` → dead状态

---

#### 步骤19 — 初始化第一个Master（k8s-master1：192.168.11.11）

```bash
cat > /root/kubeadm-init.yaml << 'EOF'
apiVersion: kubeadm.k8s.io/v1beta3
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: 192.168.11.11
  bindPort: 6443
nodeRegistration:
  criSocket: unix:///run/containerd/containerd.sock
  name: k8s-master1
---
apiVersion: kubeadm.k8s.io/v1beta3
kind: ClusterConfiguration
kubernetesVersion: v1.28.2
controlPlaneEndpoint: "192.168.11.200:6443"   # HA: VIP，非单台 Master IP
networking:
  serviceSubnet: "10.96.0.0/12"
  podSubnet: "10.244.0.0/16"
imageRepository: 192.168.11.12/cube-studio/google_containers
apiServer:
  certSANs:
  - "192.168.11.11"
  - "192.168.11.12"
  - "192.168.11.13"
    - "192.168.11.200"       # HA: MetalLB VIP
  - "k8s-master1"
  - "k8s-master2"
  - "k8s-master3"
etcd:
  local:
    dataDir: /var/lib/etcd
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
EOF

# 如果内网没有DNS服务器，配置resolv.conf
cat > /etc/resolv.conf << 'EOF'
nameserver 192.168.11.1
EOF

kubeadm init --config=/root/kubeadm-init.yaml --upload-certs
```

> **重要：** 保存输出的 `kubeadm join` 命令（Master加入命令和Worker加入命令）！

**如果初始化失败，回退：**
```bash
kubeadm reset -f
rm -rf /var/lib/etcd /etc/cni/net.d /etc/kubernetes
cat > /etc/resolv.conf << 'EOF'
nameserver 192.168.11.1
EOF
# 修正问题后重新执行 kubeadm init
```

**验证：** 初始化成功输出 `"Your Kubernetes control-plane has initialized successfully!"`

---

#### 步骤20 — 配置kubectl（Master-1：192.168.11.11）

```bash
mkdir -p /root/.kube
cp /etc/kubernetes/admin.conf /root/.kube/config
# 有时候会出现config没有被进入系统命令
# echo 'export KUBECONFIG=/root/.kube/config' >> ~/.bashrc
# source ~/.bashrc
kubectl get nodes
```

**验证：** `kubectl get nodes` → 应显示k8s-master1节点

---

#### 步骤21 — 加入其他Master节点（Master-2：192.168.11.12、Master-3：192.168.11.13）

```bash
# 使用Master-1 init输出的Master加入命令：（依次执行，不要同时，会timeout！！！！）
# HA: join 地址使用 VIP 192.168.11.200
kubeadm join 192.168.11.200:6443 --token <token> \
    --discovery-token-ca-cert-hash sha256:<hash> \
    --control-plane --certificate-key <cert-key>
```

> **Token/Hash/Cert-Key获取方式（在Master-1上执行）：**
> ```bash
> # 查看已有token
> kubeadm token list
> # 如果token已过期（默认24小时），创建新token
> kubeadm token create --print-join-command
>
> # 获取hash
> openssl x509 -pubkey -in /etc/kubernetes/pki/ca.crt \
>   | openssl rsa -pubin -outform der 2>/dev/null \
>   | openssl dgst -sha256 -hex \
>   | sed 's/^.* //'
>
> # 获取cert-key（Master加入专用）
> kubeadm init phase upload-certs --upload-certs
> ```

**验证：** `kubectl get nodes` → 应有3个Master节点（状态NotReady，等待CNI）

---

#### 步骤22 — 加入Worker节点（Worker-1：192.168.11.14、Worker-2：192.168.11.15）

```bash
# 使用Master-1 init输出的Worker加入命令：
# HA: join 地址使用 VIP 192.168.11.200
kubeadm join 192.168.11.200:6443 --token <token> \
    --discovery-token-ca-cert-hash sha256:<hash>

systemctl restart containerd kubelet
```

> Token过期时在Master-1执行：`kubeadm token create --print-join-command`

**验证：** `kubectl get nodes` → 应有5个节点（3 Master + 2 Worker）

---

#### 步骤23 — 部署CNI网络插件Flannel（Master-1：192.168.11.11）

```bash
sed -i 's|ghcr.io/flannel-io/flannel-cni-plugin:v1.9.1-flannel1|192.168.11.12/cube-studio/flannel-io/flannel-cni-plugin:v1.9.1-flannel1|g' kube-flannel.yml
sed -i 's|ghcr.io/flannel-io/flannel:v0.28.4|192.168.11.12/cube-studio/flannel-io/flannel:v0.28.4|g' kube-flannel.yml
kubectl apply -f kube-flannel.yml
kubectl get nodes -w    # 等待所有节点变为Ready
```

**验证：** `kubectl get nodes` → 所有5个节点Ready

---

#### 步骤23.5 — 部署 MetalLB + API Server VIP（HA: 控制面高可用）

**在 Master-1 上执行：**

```bash
cd /bdm/share_bdm/cube-studio-master

# 1. 部署 MetalLB（镜像已替换为私有仓库，无需拉外网）
kubectl apply -f install/kubernetes/metallb-native.yaml
kubectl wait --namespace metallb-system --for=condition=ready pod -l app=metallb --timeout=120s

# 2. 创建 IP 地址池（前端 VIP 100 + API Server VIP 200）
kubectl apply -f install/kubernetes/apiserver-lb.yaml

# 3. 验证 VIP
sleep 5
kubectl get svc -n kube-system kube-apiserver-lb
kubectl get endpoints -n kube-system kube-apiserver-lb
# Endpoints 应包含 192.168.11.11:6443, 192.168.11.12:6443, 192.168.11.13:6443

curl -sk https://192.168.11.200:6443/healthz
# 应返回 ok
```

**验证：** `curl -sk https://192.168.11.200:6443/healthz` → `ok`

---

#### 步骤23.6 — Worker 节点 kubelet 指向 VIP

**在 Worker-1 (192.168.11.14) 和 Worker-2 (192.168.11.15) 上分别执行：**

```bash
sed -i 's|server: https://192.168.11.11:6443|server: https://192.168.11.200:6443|g' /etc/kubernetes/kubelet.conf
systemctl restart kubelet
```

**验证：** `kubectl get nodes` → 所有节点 Ready（Master 连本地 apiserver，Worker 连 VIP）

---

#### 步骤23.7 — Master-1 kubectl 指向 VIP

**在 Master-1 上执行：**

```bash
sed -i 's|server: https://192.168.11.11:6443|server: https://192.168.11.200:6443|g' ~/.kube/config
kubectl get nodes
```

**验证：** `kubectl get nodes` 正常返回 → kubectl 已通过 VIP 连接任一存活 Master

---

#### 步骤24 — 创建命名空间与持久化存储目录（所有节点）

```bash
# 软链（每台机器）
mkdir -p /data/k8s
if [ ! -L /data/k8s ]; then
  [ -d /data/k8s ] && mv /data/k8s /data/k8s.bak.$(date +%Y%m%d)
  ln -sf /bdm/share_bdm /data/k8s
fi
ls -la /data/k8s
# 预期：lrwxrwxrwx ... /data/k8s -> /bdm/share_bdm

# 创建平台目录（只在 Master-1 执行一次即可，NFS 上所有节点可见）
if [ "$(hostname)" = "k8s-master1" ]; then
  mkdir -p /data/k8s/kubeflow/pipeline/workspace
  mkdir -p /data/k8s/kubeflow/pipeline/archives
  mkdir -p /data/k8s/infra/mysql
  mkdir -p /data/k8s/kubeflow/minio/mlpipeline
  mkdir -p /data/k8s/kubeflow/global
  mkdir -p /data/k8s/monitoring/grafana/
  mkdir -p /data/k8s/monitoring/prometheus/
  mkdir -p /data/k8s/kubeflow/labelstudio/
  mkdir -p /data/k8s/kubeflow/dataset

  chmod -R 777 /data/k8s/monitoring/grafana/ /data/k8s/monitoring/prometheus/
  chmod -R 777 /data/k8s/kubeflow/labelstudio/ /data/k8s/kubeflow/pipeline/
  chmod -R 777 /data/k8s/infra/ /data/k8s/kubeflow/minio/
  chmod -R 777 /data/k8s/kubeflow/global/ /data/k8s/kubeflow/dataset/
fi

# 每台机器验证软链可达
ls /data/k8s/kubeflow/pipeline/workspace
df -h /data/k8s/
```

---

### 阶段六：K8s集群验证（Master-1：192.168.11.11）

```bash
kubectl get nodes                    # 5节点全部Ready
kubectl get pods -n kube-system      # 全部Running
kubectl get pods -n kube-flannel     # 全部Running
kubectl cluster-info
```

---

### 阶段七：CubeStudio平台部署

#### 步骤25 — 解压CubeStudio源码（Master-1：192.168.11.11）

```bash
cd /data/offline
unzip -o cube-studio-master.zip -d /bdm/share_bdm/
unzip -o cube-studio-master.zip -d /tmp/
```

**验证：** `ls /bdm/share_bdm/cube-studio-master/install/kubernetes/`

---

#### 步骤26 — CubeStudio配置调整

```bash
# 1. config.py中 CONTAINER_CLI 改为 nerdctl
CONTAINER_CLI = "nerdctl"

# 2. 替换所有YAML中的镜像地址为Harbor地址
cd /bdm/share_bdm/cube-studio-master/install/kubernetes

# 使用cd /bdm/share_bdm/cube-studio-master/install/kubernetes

# 预览（不改文件）
bash replace_registry.sh --dry-run <harbor.mycompany.com>/cube-studio

# 正式替换
bash replace_registry.sh <harbor.mycompany.com>/cube-studio

# 自定义新旧地址
bash replace_registry.sh 192.168.11.12/cube-studio <harbor.mycompany.com>/cube-studio

# 脚本会替换 install/kubernetes/ 下所有 .yaml/.yml/.sh 中的镜像地址，涵盖 50+ 个文件。--dry-run 模式先预览再执行。

或者使用以下方法：
# 使用replace_images.py脚本（将HARBOR地址改为 192.168.11.12/cube-studio）
# 注意：以下文件脚本执行后会损坏，需拿原版本覆盖后手工更改镜像名称：
#   - istio/install-1.15.0.yaml
#   - redis/redis.yaml
#   - gpu/dcgm-exporter.yaml
# 此外，argo/install-3.4.3-all.yaml 的 --executor-image 部分镜像修改会遗漏

# 3. 修改config.py中的镜像地址
cd /bdm/share_bdm/cube-studio-master/install/kubernetes/cube/overlays/config/
sed -i 's|ccr.ccs.tencentyun.com/cube-studio/|192.168.11.12/cube-studio/|g' config.py
grep -c "ccr.ccs" config.py  # 应返回0

# 4. 修改init JSON中的镜像地址
cd /bdm/share_bdm/cube-studio-master/myapp/init
sed -i 's|ccr.ccs.tencentyun.com/cube-studio/|192.168.11.12/cube-studio/|g' *.json
sed -i 's|"python:|"192.168.11.12/cube-studio/python:|g' *.json
grep -c "ccr.ccs" *.json  # 应返回0
```

**replace_images.py 脚本内容：**
```python
import os, re

HARBOR = "192.168.11.12/cube-studio"
K8S_DIR = "/bdm/share_bdm/cube-studio-master/install/kubernetes"

SKIP_DIRS = {'crds', 'base'}
SKIP_FILES = {'operator-crd.yml', 'install-crd.yaml'}

def fix_image(img):
    q = img[0] if img and img[0] in '"\'' else ''
    clean = img.strip('"\'')
    if clean == 'auto' or '{{' in clean or '$' in clean:
        return img
    if clean.startswith('192.168.11.12'):
        return img
    original = clean
    m = re.match(r'^([a-zA-Z0-9][a-zA-Z0-9._-]*\.[a-zA-Z]{2,})/', clean)
    if m:
        rest = clean[len(m.group(0)):]
        clean = f"{HARBOR}/{rest}"
        clean = clean.replace(f"{HARBOR}/cube-studio/", f"{HARBOR}/")
    else:
        clean = f"{HARBOR}/{clean}"
    if clean != original:
        print(f"  {original} -> {clean}")
    return q + clean + q if q else clean

def process_file(fpath):
    try:
        with open(fpath, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except:
        return 0

    changed = 0
    new_lines = []
    in_crd = False

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if 'openAPIV3Schema' in line or 'validation:' in line:
            in_crd = True
        if in_crd and line and line[0] not in (' ', '\t'):
            in_crd = False

        if stripped.startswith('image:') and not stripped.startswith('imagePull'):
            if in_crd or indent >= 20 or stripped == 'image:':
                new_lines.append(line)
                continue

        if stripped.startswith('#'):
            new_lines.append(line)
            continue

        def replace_match(m):
            nonlocal changed
            prefix = m.group(1)
            quote = m.group(2) or ''
            image = m.group(3)
            if '{{' in image or '}}' in image or '$' in image:
                return m.group(0)
            full = quote + image + quote if quote else image
            new = fix_image(full)
            if new != full:
                changed += 1
            return prefix + new

        new_line = re.sub(
            r'(image:\s*)(["\']?)([a-zA-Z0-9][a-zA-Z0-9._/\-]*(?::[a-zA-Z0-9][a-zA-Z0-9._\-]*)?)',
            replace_match, line
        )
        new_lines.append(new_line)

    if changed:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        print(f"[{fpath}] +{changed}")
    return changed

total = 0
for root, dirs, files in os.walk(K8S_DIR):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if f.endswith(('.yaml', '.yml')) and f not in SKIP_FILES:
            total += process_file(os.path.join(root, f))

print(f"\nTotal: {total} images replaced")
```

**验证：**
```bash
grep -E "K8S_NETWORK_MODE|CONTAINER_CLI" /bdm/share_bdm/cube-studio-master/install/kubernetes/cube/overlays/config/config.py
grep -r "192.168.11.12" --include="*.yaml" | head -5
```

---

#### 步骤27 — 执行CubeStudio部署（Master-1：192.168.11.11）

```bash
# 1. worker 打计算标签
kubectl label node k8s-worker1 cpu=true train=true notebook=true service=true org=public
kubectl label node k8s-worker2 cpu=true train=true notebook=true service=true org=public

# 3. master 去 taint + 打控制面标签
kubectl taint nodes k8s-master1 node-role.kubernetes.io/control-plane-
kubectl taint nodes k8s-master2 node-role.kubernetes.io/control-plane-
kubectl taint nodes k8s-master3 node-role.kubernetes.io/control-plane-

kubectl label node k8s-master1 kubeflow-dashboard=true mysql=true redis=true kubeflow=true istio=true monitoring=true
kubectl label node k8s-master2 kubeflow-dashboard=true mysql=true redis=true kubeflow=true istio=true monitoring=true
kubectl label node k8s-master3 kubeflow-dashboard=true mysql=true redis=true kubeflow=true istio=true monitoring=true


cp /etc/kubernetes/admin.conf /bdm/share_bdm/cube-studio-master/install/kubernetes/config
cd /bdm/share_bdm/cube-studio-master/install/kubernetes
sh start.sh 192.168.11.11
```

**验证：**
```bash
kubectl get pods -n cube-studio
kubectl get svc -n istio-system istio-ingressgateway
```

---

#### 步骤28 — Istio 入口切为 LoadBalancer + HA 扩容

```bash
# 1. 切 Istio IngressGateway 为 LoadBalancer（MetalLB 自动分配前端 VIP 192.168.11.100）
kubectl patch svc istio-ingressgateway -n istio-system -p '{"spec":{"type":"LoadBalancer","externalIPs":null}}'

# 2. Istio 组件 HA 扩容
kubectl scale deploy istio-ingressgateway -n istio-system --replicas=2
kubectl scale deploy istiod -n istio-system --replicas=2

# 3. 验证
sleep 5
kubectl get svc -n istio-system istio-ingressgateway
# EXTERNAL-IP 应为 192.168.11.100
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.11.100/frontend/
# 应返回 200
```

**验证：** `curl http://192.168.11.100/frontend/` → HTTP 200

> **注意：** HA 模式下不再使用 NodePort 30080。前端通过 MetalLB VIP `192.168.11.100` 直接访问，前端 Pod 在 2 个不同节点运行。

---

### 阶段八：最终验证

**集群状态检查（Master-1：192.168.11.11）：**
```bash
kubectl get nodes                    # 5节点全部Ready
kubectl get pods -n kube-system      # 全部Running
kubectl get pods -n cube-studio      # 全部Running

# 前端访问验证（HA: 通过 VIP 192.168.11.100 访问，前端 2 副本）
curl http://192.168.11.100
```

**Harbor状态检查（Master-2：192.168.11.12）：**
```bash
docker ps | grep harbor
curl http://192.168.11.12/api/v2.0/health
```

**验证：** 
- 浏览器访问 `http://192.168.11.100` → CubeStudio登录页，默认账号 `admin / admin`（HA: VIP，前端 2 副本）
- 浏览器访问 `http://192.168.11.12` → Harbor管理页，默认账号 `admin / Harbor12345`

---

## 六、回退方案

### 卸载CubeStudio（Master-1）

```bash
kubectl delete namespace cube-studio
rm -rf /data/k8s-volumes/{mysql,redis,cubestudio}/*
```

### 清理K8s环境（对应节点）

```bash
kubeadm reset -f
rm -rf /etc/kubernetes/ /var/lib/etcd/ /var/lib/kubelet/ /var/lib/cni/ /etc/cni/net.d/ ~/.kube/
iptables -F && iptables -t nat -F && iptables -t mangle -F && iptables -X
```

**验证：** `ps aux | grep -E "kube|etcd" | grep -v grep` → 无残留

### 卸载Harbor（Master-2）

```bash
cd /opt/harbor
docker-compose down
rm -rf /opt/harbor
```

### 恢复系统配置

```bash
cp /etc/hosts.bak /etc/hosts
cp /etc/fstab.bak /etc/fstab
rm -f /etc/sysctl.d/k8s.conf
```

---

## 七、常见问题处理

### CNI冲突问题

哪个节点冲突就在哪个节点上执行：
```bash
rm -f /etc/cni/net.d/*
ip link delete cni10 2>/dev/null
ip link delete flannel1.1 2>/dev/null
systemctl restart kubelet
mkdir -p ~/.kube
cp /etc/kubernetes/admin.conf ~/.kube/config
```

### 节点NotReady

```bash
kubectl describe node <node-name>
journalctl -u kubelet -f
# 1. CNI未安装 → 检查 /opt/cni/bin/
# 2. 镜像未导入 → ctr -n k8s.io images ls
# 3. containerd异常 → systemctl restart containerd
systemctl restart kubelet
```

### 镜像拉取失败（ImagePullBackOff/ErrImagePull）

```bash
kubectl describe pod <pod> -n <ns> | grep -i image
ctr -n k8s.io images ls | grep <image-name>
# 缺镜像：cd /data/offline/images && ctr -n k8s.io images import <file>.tar
# 检查Harbor：cat /etc/containerd/certs.d/192.168.11.12/hosts.toml
```

### Token过期

```bash
kubeadm token create --print-join-command
```

### Harbor无法访问（Master-2）

```bash
docker ps | grep harbor
cd /opt/harbor
docker-compose down && docker-compose up -d
docker-compose logs --tail=50
curl http://192.168.11.12/api/v2.0/health
```

### Containerd启动失败

```bash
containerd config dump > /dev/null
journalctl -u containerd -n 50
# 常见原因：config.toml语法错误 / CNI缺失 / runc未安装
```

---

## 八、关键端口

| 端口 | 服务 | 说明 | 访问方式 |
|------|------|------|----------|
| 6443 | K8s API Server | Kubernetes API入口 | `kubectl` 通过 VIP 192.168.11.200 连接 |
| 2379-2380 | etcd | etcd集群通信 | 集群内部 |
| 80 | CubeStudio前端 | CubeStudio Web界面（HA: 2副本 + VIP） | 浏览器 `http://192.168.11.100` |
| 80 | Harbor | Harbor镜像仓库 | 浏览器 `http://192.168.11.12` |
| 3306 | MySQL | 数据库（外部: 192.168.11.15） | 集群内部 |
| 6379 | Redis | 缓存（集群内） | 集群内部 |

---

## 九、目录结构

| 目录 | 用途 | 所在节点 |
|------|------|----------|
| /data/offline/ | 离线物料根目录 | 所有节点 |
| /data/offline/k8s-bin/ | K8s二进制（kubeadm、kubelet、kubectl） | 所有节点 |
| /data/offline/images/ | 容器镜像（54个.tar） | 所有节点 |
| /data/offline/harbor/ | Harbor安装包 | Master-2 |
| /data/k8s/ | 持久化存储（软链 → /bdm/share_bdm） | 所有节点 |
| /opt/harbor/ | Harbor安装目录 | Master-2 |
| /bdm/docker/ | Docker数据目录 | Master-2 |
| /bdm/share_bdm/cube-studio-master/ | CubeStudio源码 | Master-1 |

---

## 十、常用命令速查

| 类别 | 命令 | 说明 |
|------|------|------|
| 集群管理 | `kubectl get nodes -o wide` | 查看所有节点详细信息 |
| 集群管理 | `kubectl get pods -A -o wide` | 查看所有命名空间的Pod |
| 集群管理 | `kubectl describe node <node>` | 查看节点详细信息 |
| 日志查看 | `kubectl logs <pod> -n <ns> --tail=100` | 查看Pod最近100行日志 |
| 日志查看 | `journalctl -u kubelet -f` | 实时查看kubelet日志 |
| 日志查看 | `journalctl -u containerd -f` | 实时查看containerd日志 |
| 镜像管理 | `ctr -n k8s.io images ls` | 列出containerd中所有镜像 |
| 镜像管理 | `ctr -n k8s.io images import <file>.tar` | 导入镜像到containerd |
| Token管理 | `kubeadm token create --print-join-command` | 生成新的join命令 |
| Harbor | `docker login 192.168.11.12 -u admin -p Harbor12345` | 登录Harbor |
| Harbor | `curl http://192.168.11.12/api/v2.0/health` | 检查Harbor健康状态 |
| 系统检查 | `getenforce` | 查看SELinux状态 |
| 系统检查 | `systemctl status firewalld` | 查看防火墙状态 |
| 系统检查 | `showmount -e 192.168.11.11` | 查看NFS共享 |
| 故障排查 | `kubectl describe pod <pod> -n <ns>` | 排查Pod启动异常 |
| 故障排查 | `kubeadm reset -f` | 重置K8s节点 |