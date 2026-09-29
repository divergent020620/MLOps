# Cube Studio 开发流程

> 源码在 k8s-master1（192.168.11.11）的 `/bdm/share_bdm/cube-studio-master/`。  
> Harbor 镜像仓库：`http://192.168.11.12`，Docker 需先登录。

## 一键构建（改代码后执行）

| 改了什么 | 执行命令 | 耗时 |
|----------|---------|------|
| 仅后端 Python | `bash build_backend.sh` | ~2 分钟 |
| 仅前端 React | `bash build_frontend.sh` | ~3 分钟 |
| 前后端都改了 | 先跑前端，再跑后端 | ~5 分钟 |

```bash
# 默认 TAG = 当天日期（如 20260714）
bash build_backend.sh
bash build_frontend.sh

# 指定 TAG
bash build_backend.sh 20260714-hotfix
bash build_frontend.sh 20260714-hotfix
```

脚本会自动：构建 → 推送 Harbor → 更新 Deployment → 等待 rollout 完成。

## 首次环境准备（仅一次）

```bash
# 1. Docker 登录 Harbor
echo 'Harbor12345' | docker login 192.168.11.12 -u admin --password-stdin

# 2. Docker daemon.json（/etc/docker/daemon.json）
cat > /etc/docker/daemon.json << 'EOF'
{
  "iptables": false,
  "insecure-registries": ["192.168.11.12"]
}
EOF
systemctl restart docker
```

## 构建原理

### 后端（build_backend.sh）

```
当前运行镜像（含所有依赖）
  + COPY myapp/          ← 覆盖后端代码
  + COPY frontend/build  ← 覆盖前端静态文件
  = 新镜像（增量，构建快）
```

- 基础镜像：`192.168.11.12/cube-studio/kubeflow-dashboard:20260703`
- 同时更新 4 个 Deployment：`kubeflow-dashboard` / `schedule` / `worker` / `watch`

### 前端（build_frontend.sh）

```
1. npm run build          ← 构建静态文件
2. nginx 基础镜像
  + COPY frontend/build   ← 覆盖静态文件
  = 新镜像
```

- 基础镜像：`192.168.11.12/cube-studio/kubeflow-dashboard-frontend:20260630v1`

## 新增 Python 依赖时

如果改了 `requirements.txt`，不能再用旧镜像做 base。需要完整构建：

```bash
# 先构建新的 base 镜像（含新依赖）
docker build -t 192.168.11.12/cube-studio/kubeflow-dashboard:20260703 \
  -f install/docker/Dockerfile .

# 然后在 build_backend.sh 里把 BASE_IMAGE 改成新的 tag
```

## 切换部署环境（替换镜像仓库地址）

```bash
cd install/kubernetes

# 预览
bash replace_registry.sh --dry-run harbor.mycompany.com/cube-studio

# 执行
bash replace_registry.sh harbor.mycompany.com/cube-studio

# 然后运行 kubectl apply -k cube/overlays
```

## 常用命令

```bash
# 查看所有 Pod
kubectl get pods -A -o wide --sort-by='.spec.nodeName'

# 查看后端日志
kubectl logs -n infra deploy/kubeflow-dashboard --tail=50 -f

# 进入后端容器
kubectl exec -it -n infra deploy/kubeflow-dashboard -- bash

# 强制重建 Pod
kubectl rollout restart deployment -n infra kubeflow-dashboard

# 查看镜像版本
kubectl get deploy -n infra -o jsonpath='{range .items[*]}{.metadata.name}{" = "}{.spec.template.spec.containers[0].image}{"\n"}{end}'
```

## 文件路径速查

| 用途 | 路径 |
|------|------|
| 后端源码 | `myapp/` |
| 前端源码 | `myapp/frontend/src/` |
| 前端构建产物 | `myapp/static/appbuilder/frontend/` |
| 后端 Dockerfile | `install/docker/Dockerfile` |
| 前端 Dockerfile | `install/docker/dockerFrontend/Dockerfile` |
| K8s 部署 YAML | `install/kubernetes/cube/base/` |
| 镜像仓库替换脚本 | `install/kubernetes/replace_registry.sh` |
| 后端构建脚本 | `build_backend.sh` |
| 前端构建脚本 | `build_frontend.sh` |
