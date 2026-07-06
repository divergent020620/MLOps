# Cube Studio 完整开发部署流程

## 项目结构概览

```
cube-studio-master/
├── myapp/                          # 后端 Flask 应用
│   ├── models/                     # 数据模型 (SQLAlchemy)
│   ├── views/                      # 视图/API (Flask-AppBuilder)
│   ├── tasks/                      # Celery 异步任务 + 定时任务
│   ├── utils/py/                   # 工具函数 (K8s 操作等)
│   ├── config.py                   # 默认配置
│   └── frontend/                   # 主前端 React 项目
│       ├── src/                    # 源码
│       ├── public/                 # 静态资源
│       └── package.json
├── myapp/vision/                   # 流水线可视化编辑器 (React)
├── myapp/visionPlus/               # ETL 数据管道编辑器 (React)
├── install/
│   ├── docker/                     # 平台镜像构建
│   │   ├── Dockerfile-base         # 基础镜像 (OS + Python + Node)
│   │   ├── Dockerfile              # 后端应用镜像
│   │   ├── dockerFrontend/         # 前端 nginx 镜像
│   │   ├── config.py               # 开发环境配置
│   │   ├── entrypoint.sh           # 容器启动脚本
│   │   └── requirements.txt        # Python 依赖
│   └── kubernetes/cube/            # K8s 部署清单
│       ├── base/                   # 基础部署 YAML
│       └── overlays/               # 环境覆盖 (镜像 tag、配置)
├── job-template/job/               # 作业模板 (每个目录一个模板)
└── images/                         # 预制镜像 (notebook、GPU、serving)
```

---

## 一、前端开发

Cube Studio 有三个前端项目，修改前先确认目标项目：

| 项目 | 路径 | 功能 |
|------|------|------|
| 主前端 | `myapp/frontend/` | 平台主界面 |
| Vision | `myapp/vision/` | 流水线可视化编辑器 |
| VisionPlus | `myapp/visionPlus/` | ETL 数据管道编辑器 |

### 1.1 本地开发（热更新调试）

```bash
# ========== 主前端 ==========
cd myapp/frontend

# 首次运行：安装依赖
npm install

# 启动开发服务器 (默认 http://localhost:3000)
npm run start

# 代理配置在 src/setupProxy.js，指向后端地址
# 例如：proxy 指向 http://localhost:80 或你的开发环境后端


# ========== Vision 编辑器 ==========
cd myapp/vision

npm install
npm run start


# ========== VisionPlus 编辑器 ==========
cd myapp/visionPlus

# 使用 yarn 管理依赖
yarn
npm run build   # 注：VisionPlus 没有 dev server，直接 build
```

**注意事项：**
- 本地开发需要后端 API 可用，确保 `setupProxy.js` 中代理地址正确
- 主前端和 Vision 支持热更新，修改保存即刷新
- Windows 下遇到换行符问题，修改 `visionPlus/.eslintrc` 中 `linebreak-style` 为 `windows`

### 1.2 构建前端产物

```bash
# ========== 主前端 ==========
cd myapp/frontend
npm run build
# 产物输出到 myapp/frontend/build/


# ========== Vision ==========
cd myapp/vision
npm run build
# 产物输出到 myapp/vision/build/


# ========== VisionPlus ==========
cd myapp/visionPlus
npm run build
# 产物输出到 myapp/visionPlus/build/
```

构建产物最终会被打包到前端的 nginx 镜像中，或由后端的 gunicorn 直接静态托管。

### 1.3 打包前端镜像并部署

**方式一：前端独立镜像（推荐，生产环境）**

```bash
# 1. 确保各前端已 build
cd myapp/frontend && npm run build
cd ../../myapp/vision && npm run build
cd ../../myapp/visionPlus && npm run build

# 2. 构建 nginx 前端镜像
docker build --network=host \
  -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:$(date +%Y.%m.%d) \
  -f install/docker/dockerFrontend/Dockerfile .

# 3. 推送到镜像仓库
docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:$(date +%Y.%m.%d)

# 4. 更新 K8s 部署的镜像 tag
# 修改 install/kubernetes/cube/overlays/kustomization.yml 中的 newTag
#   newTag: 2026.06.09    # 改为刚刚 push 的版本号

# 5. 应用更新
kubectl apply -k install/kubernetes/cube/overlays/
```

**方式二：后端托管前端静态文件（简单，开发环境）**

```bash
# 将前端 build 产物复制到后端静态目录
cp -r myapp/frontend/build/* myapp/static/appbuilder/frontend/
cp -r myapp/vision/build/*   myapp/static/appbuilder/vision/
cp -r myapp/visionPlus/build/* myapp/static/appbuilder/visionPlus/

# 然后按照后端的流程打包部署即可，gunicorn 直接托管这些静态文件
```

### 1.4 前端文件对应关系

```
修改位置                        → 构建后去向
─────────────────────────────────────────────────────────
myapp/frontend/src/            → myapp/frontend/build/
myapp/vision/src/              → myapp/vision/build/
myapp/visionPlus/src/          → myapp/visionPlus/build/
                                 → nginx 镜像: /usr/share/nginx/html/
                                 或 后端静态: myapp/static/appbuilder/
```

---

## 二、后端开发

### 2.1 本地开发调试

#### Docker Compose 方式

```bash
cd install/docker

# 启动所有服务
docker-compose up -d

# 后端在容器内运行，端口 80
# 访问 http://localhost/frontend/
# 默认账号: admin / admin
```

```bash
# 快速迭代：用 sleep 保持容器，手动 exec
# 1. 修改 docker-compose.yml，将 myapp 的 command 改为：
#    command: ['bash', '-c', 'sleep 1000000']

docker-compose up -d

# 2. 进入容器
docker exec -it docker-myapp-1 bash

# 3. 容器内首次运行
/entrypoint.sh

# 4. 后续修改代码后直接重启
python myapp/run.py
```

#### 裸机直接运行

```bash
# 安装 Python 依赖
pip3 install --upgrade setuptools pip
pip3 install -r install/docker/requirements.txt

# 设置环境变量
export FLASK_APP=myapp:app
export STAGE=dev

# 开发模式启动
python myapp/run.py
# 或
gunicorn --bind 0.0.0.0:80 --workers 4 --worker-class=gevent --timeout 300 myapp:app
```

#### 调试工具

```python
# 项目中已全局引入 pysnooper，用它追踪函数调用
from pysnooper import snoop

@snoop()  # 添加装饰器即可打印函数执行详情
def my_function():
    ...
```

### 2.2 后端代码修改要点

**修改 API / View：**
```
myapp/views/
├── baseApi.py        # 基础 API 类 (MyappModelView, MyappRestApi)
├── home.py           # 主页和流水线 API (155KB，最大)
├── view_images.py    # 镜像仓库管理 API
├── view_docker.py    # 在线镜像构建 API
├── view_pipeline.py  # 流水线编排和执行 API
├── view_task.py      # 单个任务执行 API
├── view_job_template.py  # 作业模板 CRUD
└── ...
```

**修改数据模型：**
```
myapp/models/
├── model_job.py      # Repository, Images, Job_Template, Pipeline, Task
├── model_team.py     # Project, User
├── model_notebook.py # Notebook
└── ...
```

模型修改后需要生成数据库迁移：
```bash
# 生成迁移脚本
myapp db migrate -m "describe your change"

# 应用迁移
myapp db upgrade
```

**修改 Celery 任务：**
```
myapp/tasks/
├── async_task.py     # 异步任务 (docker commit 监控等)
├── schedules.py      # 定时任务 (流水线调度、清理等)
└── celery_app.py     # Celery 配置
```

### 2.3 打包后端镜像并部署

```bash
# ========== 1. 构建基础镜像（依赖变更时执行） ==========
docker build --network=host \
  -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9-$(date +%Y%m%d) \
  -f install/docker/Dockerfile-base .

docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9-$(date +%Y%m%d)

# 更新 Dockerfile 中的 FROM 为新的 base tag


# ========== 2. 构建后端应用镜像（每次代码变更） ==========
docker build --network=host \
  -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:$(date +%Y.%m.%d) \
  -f install/docker/Dockerfile .

docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:$(date +%Y.%m.%d)


# ========== 3. 更新 K8s 部署 ==========
# 修改 install/kubernetes/cube/overlays/kustomization.yml：
#   newTag: 2026.06.09    # 改为刚 push 的后端镜像 tag

kubectl apply -k install/kubernetes/cube/overlays/
```

### 2.4 后端 Dockerfile 详解

```dockerfile
# install/docker/Dockerfile
FROM ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9-20260301

# 1. 后端代码
COPY myapp/ /home/myapp/myapp/

# 2. 前端编译好的静态文件（gunicorn 会托管）
COPY myapp/static/appbuilder/frontend/ /home/myapp/myapp/static/appbuilder/frontend/

# 3. 启动脚本
COPY install/docker/entrypoint.sh /entrypoint.sh

# 4. 入口
ENTRYPOINT ["/entrypoint.sh"]
```

---

## 三、K8s 部署架构

### 3.1 五个核心 Deployment

| Deployment | 镜像 | 作用 |
|------------|------|------|
| `deploy-backend.yaml` | `kubeflow-dashboard` | Flask/Gunicorn Web 后端 |
| `deploy-frontend.yaml` | `kubeflow-dashboard-frontend` | Nginx 托管前端静态文件 |
| `deploy-worker.yaml` | `kubeflow-dashboard` | Celery Worker (异步任务) |
| `deploy-schedule.yaml` | `kubeflow-dashboard` | Celery Beat (定时调度) |
| `deploy-watch.yaml` | `kubeflow-dashboard` | K8s 资源监控 |

**注意：** backend、worker、schedule、watch 四个组件使用**同一个后端镜像**，通过不同的启动命令区分：

```yaml
# backend: gunicorn web 服务
command: ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "20", "myapp:app"]

# worker: celery 异步任务
command: ["celery", "-A", "myapp.tasks.celery_app", "worker", "--loglevel=info"]

# schedule: celery 定时调度
command: ["celery", "-A", "myapp.tasks.celery_app", "beat", "--loglevel=info"]

# watch: supervisor 多进程守护
command: ["supervisord", "-c", "/home/myapp/myapp/supervisor/supervisor.conf"]
```

### 3.2 镜像版本管理 (Kustomize)

```yaml
# install/kubernetes/cube/overlays/kustomization.yml
images:
  - name: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard
    newName: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard
    newTag: 2026.06.09      # ← 改这里升级后端版本

  - name: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend
    newName: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend
    newTag: 2026.06.09      # ← 改这里升级前端版本
```

**滚动更新：**

```bash
# 查看当前状态
kubectl get pods -n infra

# 应用更新
kubectl apply -k install/kubernetes/cube/overlays/

# 观察滚动更新过程
kubectl rollout status deployment/kubeflow-dashboard -n infra

# 如有问题，回滚
kubectl rollout undo deployment/kubeflow-dashboard -n infra
```

---

## 四、完整开发 — 以“在主页加一个按钮”为例

### 场景：在平台主页加一个“智算平台入口”按钮

#### Step 1: 前端修改

```bash
cd myapp/frontend
npm run start    # 启动 dev server
```

编辑 `myapp/frontend/src/pages/Home/index.tsx`（示例路径，实际以项目为准），添加按钮：

```tsx
<Button 
  type="primary" 
  onClick={() => window.open('/zhisuan')}
  icon={<ThunderboltOutlined />}
>
  智算平台入口
</Button>
```

浏览器 `http://localhost:3000` 确认效果。

#### Step 2: 前端构建

```bash
cd myapp/frontend
npm run build
```

#### Step 3: 后端修改（如果需要新增 API）

编辑 `myapp/views/home.py`，添加路由：

```python
class ZhisuanRedirect(MyappModelRestApi):
    route_base = '/zhisuan'
    
    @expose('/', methods=['GET'])
    def index(self):
        return redirect('https://zhisuan.oa.com/')
```

#### Step 4: 本地验证

```bash
# 将前端产物复制到后端静态目录
cp -r myapp/frontend/build/* myapp/static/appbuilder/frontend/

# 启动后端
export FLASK_APP=myapp:app
python myapp/run.py

# 访问 http://localhost:80/frontend/ 验证
```

#### Step 5: 构建和推送镜像

```bash
# 构建后端镜像
docker build --network=host \
  -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.06.09 \
  -f install/docker/Dockerfile .

docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.06.09

# 构建前端镜像
docker build --network=host \
  -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.06.09 \
  -f install/docker/dockerFrontend/Dockerfile .

docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.06.09
```

#### Step 6: 部署到 K8s

```yaml
# 修改 install/kubernetes/cube/overlays/kustomization.yml
images:
  - name: ...kubeflow-dashboard
    newTag: 2026.06.09   # 更新
  - name: ...kubeflow-dashboard-frontend
    newTag: 2026.06.09   # 更新
```

```bash
kubectl apply -k install/kubernetes/cube/overlays/
kubectl rollout status deployment/kubeflow-dashboard -n infra
```

---

## 五、只有后端变更的情况

这是最常见的场景，**不需要重新构建前端镜像**：

```
修改 myapp/views/*.py 或 myapp/models/*.py
        │
        ▼
docker build -f install/docker/Dockerfile  → 只更新后端镜像
        │
        ▼
docker push → 更新 kustomization.yml 中后端 newTag
        │
        ▼
kubectl apply -k → 只滚动更新 backend / worker / schedule / watch
```

---

## 六、只有前端变更的情况

```
修改 myapp/frontend/src/*.tsx (或 vision/src, visionPlus/src)
        │
        ▼
npm run build → 生成静态文件
        │
        ▼
docker build -f install/docker/dockerFrontend/Dockerfile → 只更新前端镜像
        │
        ▼
docker push → 更新 kustomization.yml 中前端 newTag
        │
        ▼
kubectl apply -k → 只滚动更新 frontend deployment
```

---

## 七、数据库变更流程

```bash
# 1. 修改模型文件 myapp/models/*.py

# 2. 生成迁移脚本
export FLASK_APP=myapp:app
myapp db migrate -m "add zhisuan_config table"

# 3. 检查生成的迁移文件 myapp/migrations/versions/xxxx.py

# 4. 在容器内应用迁移
kubectl exec -it deployment/kubeflow-dashboard -n infra -- bash
myapp db upgrade

# 或者让 entrypoint.sh 自动执行（会在容器启动时运行 myapp db upgrade）
```

---

## 八、常用命令速查

```bash
# ─── 本地开发 ───
cd myapp/frontend && npm run start          # 前端 dev server
cd myapp/frontend && npm run build          # 前端构建
python myapp/run.py                         # 后端 dev 模式
gunicorn --bind 0.0.0.0:80 -w 4 myapp:app  # 后端生产模式

# ─── 镜像构建 ───
# 后端镜像
docker build --network=host -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:$(date +%Y.%m.%d) -f install/docker/Dockerfile .

# 前端镜像
docker build --network=host -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:$(date +%Y.%m.%d) -f install/docker/dockerFrontend/Dockerfile .

# ─── 推送镜像 ───
docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:<tag>
docker push ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:<tag>

# ─── K8s 操作 ───
kubectl apply -k install/kubernetes/cube/overlays/           # 部署
kubectl rollout status deployment/kubeflow-dashboard -n infra  # 查看更新进度
kubectl rollout undo deployment/kubeflow-dashboard -n infra    # 回滚
kubectl get pods -n infra -w                                   # 查看 Pod 状态
kubectl logs -f deployment/kubeflow-dashboard -n infra         # 查看日志

# ─── 数据库 ───
myapp db migrate -m "message"    # 生成迁移
myapp db upgrade                 # 应用迁移
myapp db history                 # 查看迁移历史
```
