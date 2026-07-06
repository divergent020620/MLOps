# CubeStudio 二次开发指南 — 启用角色管理功能

## 一、问题分析cd 

### 1.1 当前状态

根据代码分析，CubeStudio 的角色管理功能：

**后端**：✅ **已完整实现**

- 位置：`myapp/views/view_user_role.py`
- API 路由：`/roles/api`
- 功能：角色的增删改查、权限管理
- 视图类：`Role_ModelView_Api` (已注册)

**前端**：❌ **未启用**

- 前端采用 React + TypeScript
- 路由配置：`myapp/vision/src/routes/config.ts`（仅有 2 个路由）
- 菜单系统：由后端 Flask-AppBuilder 控制，前端未独立实现菜单

**关键发现**：

- CubeStudio 采用**前后端分离架构**
- 前端主要用于任务流编排（Pipeline Editor）
- 用户管理、角色管理等功能在**后端 Flask-AppBuilder 自带的管理界面**中
- 访问地址：`http://<ip>/myapp/users/list`（用户列表）
- 访问地址：`http://<ip>/myapp/roles/list`（角色列表，可能被隐藏）

***

## 二、启用角色管理功能（无需修改代码）

### 2.1 方法一：直接访问后端管理界面

```bash
# 1. 登录 CubeStudio
http://<your-ip>/frontend/

# 2. 直接访问角色管理页面（后端 Flask-AppBuilder 界面）
http://<your-ip>/myapp/roles/list

# 3. 访问用户管理页面
http://<your-ip>/myapp/users/list
```

**说明**：

- Flask-AppBuilder 自带完整的 CRUD 界面
- 角色管理功能已经存在，只是菜单可能被隐藏
- 可以直接通过 URL 访问

### 2.2 方法二：在后端添加菜单链接

修改 `myapp/views/view_user_role.py`，在文件末尾添加：

```python
# 在 appbuilder.add_api(Role_ModelView_Api) 后面添加

# 添加角色管理菜单（可选，如果想在左侧菜单显示）
appbuilder.add_view(
    Role_ModelView_Api,
    "角色列表",
    icon="fa-users",
    category="用户管理",
    category_icon="fa-user",
    category_label="用户管理"
)
```

**重启后端服务**：

```bash
kubectl rollout restart deploy/kubeflow-dashboard -n infra
```

***

## 三、二次开发完整流程

如果你需要修改源码进行二次开发，完整流程如下：

### 3.1 开发环境准备

#### 3.1.1 克隆代码仓库

```bash
# 1. 克隆 CubeStudio 仓库
git clone https://github.com/tencentmusic/cube-studio.git
cd cube-studio

# 2. 创建开发分支
git checkout -b feature/role-management
```

#### 3.1.2 安装前端依赖

```bash
cd myapp/vision

# 安装 Node.js 依赖
npm install
# 或使用 yarn
yarn install
```

#### 3.1.3 安装后端依赖

```bash
cd ../..

# 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3.2 前端开发

#### 3.2.1 启动前端开发服务器

```bash
cd myapp/vision

# 启动开发服务器（热更新）
npm run dev

# 前端会运行在 http://localhost:3000
```

#### 3.2.2 添加角色管理页面（如需要）

**步骤 1：创建角色管理页面组件**

```bash
mkdir -p src/pages/RoleManagement
```

创建 `src/pages/RoleManagement/index.tsx`：

```typescript
import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, message } from 'antd';
import api from '@src/api';

const RoleManagement: React.FC = () => {
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);
  const [form] = Form.useForm();

  // 获取角色列表
  const fetchRoles = async () => {
    setLoading(true);
    try {
      const res = await api.get('/roles/api/');
      if (res.status === 0) {
        setRoles(res.result.data);
      }
    } catch (error) {
      message.error('获取角色列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRoles();
  }, []);

  // 创建角色
  const handleCreate = async (values: any) => {
    try {
      await api.post('/roles/api/', values);
      message.success('创建成功');
      setVisible(false);
      form.resetFields();
      fetchRoles();
    } catch (error) {
      message.error('创建失败');
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: '角色名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '权限',
      dataIndex: 'permissions',
      key: 'permissions',
      render: (permissions: any[]) => permissions?.map(p => p.name).join(', '),
    },
    {
      title: '操作',
      key: 'action',
      render: (text: any, record: any) => (
        <Button type="link" onClick={() => handleEdit(record)}>
          编辑
        </Button>
      ),
    },
  ];

  const handleEdit = (record: any) => {
    // 编辑逻辑
    console.log('编辑角色:', record);
  };

  return (
    <div style={{ padding: 24 }}>
      <Button type="primary" onClick={() => setVisible(true)} style={{ marginBottom: 16 }}>
        创建角色
      </Button>
      <Table
        columns={columns}
        dataSource={roles}
        loading={loading}
        rowKey="id"
      />
      <Modal
        title="创建角色"
        visible={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onFinish={handleCreate}>
          <Form.Item
            label="角色名称"
            name="name"
            rules={[{ required: true, message: '请输入角色名称' }]}
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default RoleManagement;
```

**步骤 2：添加路由**

修改 `src/routes/config.ts`：

```typescript
import React, { lazy } from 'react';

export interface IRoute {
  name: string;
  path: string;
  component: React.LazyExoticComponent<React.FC<any>>;
}

const config: Array<IRoute> = [
  {
    name: 'index',
    path: '/',
    component: lazy(() => import('../pages/Index')),
  },
  {
    name: 'home',
    path: '/home',
    component: lazy(() => import('../pages/Home')),
  },
  // 新增：角色管理路由
  {
    name: 'roleManagement',
    path: '/role-management',
    component: lazy(() => import('../pages/RoleManagement')),
  }
];

export default config;
```

**步骤 3：添加 API 接口**

修改 `src/api/index.ts`，添加角色管理 API：

```typescript
// 在现有 API 基础上添加
export default {
  // ... 现有 API

  // 角色管理 API
  getRoles: () => ajax.get('/roles/api/'),
  createRole: (data: any) => ajax.post('/roles/api/', data),
  updateRole: (id: number, data: any) => ajax.put(`/roles/api/${id}`, data),
  deleteRole: (id: number) => ajax.delete(`/roles/api/${id}`),
};
```

#### 3.2.3 构建前端

```bash
cd myapp/vision

# 构建生产版本
npm run build

# 构建产物在 myapp/static/appbuilder/frontend/
```

### 3.3 后端开发

#### 3.3.1 修改角色管理视图（如需要）

编辑 `myapp/views/view_user_role.py`：

```python
# 在 Role_ModelView_Api 类中添加自定义方法

class Role_ModelView_Api(Role_ModelView_Base, MyappModelRestApi):
    datamodel = SQLAInterface(MyRole)
    route_base = '/roles/api'
    
    # 添加自定义权限检查
    def pre_add(self, item):
        # 添加角色前的验证逻辑
        if not item.name:
            raise Exception("角色名称不能为空")
        return item
    
    def pre_update(self, item):
        # 更新角色前的验证逻辑
        return item
    
    # 添加自定义 API 端点
    @expose_api(description="获取角色权限", url="/permissions/<int:role_id>", methods=["GET"])
    def get_role_permissions(self, role_id):
        role = db.session.query(MyRole).filter_by(id=role_id).first()
        if not role:
            return jsonify({"status": -1, "message": "角色不存在"})
        
        permissions = [{"id": p.id, "name": p.name} for p in role.permissions]
        return jsonify({
            "status": 0,
            "result": {
                "role_id": role.id,
                "role_name": role.name,
                "permissions": permissions
            }
        })
```

#### 3.3.2 本地运行后端（开发调试）

```bash
# 1. 配置环境变量
export FLASK_APP=myapp
export FLASK_ENV=development
export MYAPP_CONFIG=myapp.config

# 2. 初始化数据库（首次运行）
flask db upgrade

# 3. 启动开发服务器
flask run --host=0.0.0.0 --port=8080

# 后端运行在 http://localhost:8080
```

### 3.4 构建 Docker 镜像

#### 3.4.1 构建前端镜像

```bash
# 在项目根目录执行

# 1. 先构建前端代码
cd myapp/vision
npm run build
cd ../..

# 2. 构建前端 Docker 镜像
docker build -t <your-registry>/kubeflow-dashboard-frontend:custom-v1.0 \
  -f install/docker/dockerFrontend/Dockerfile .

# 3. 推送到镜像仓库
docker push <your-registry>/kubeflow-dashboard-frontend:custom-v1.0
```

**示例（推送到内网 Harbor）**：

```bash
# 假设 Harbor 地址为 10.208.173.121:88
docker tag <your-registry>/kubeflow-dashboard-frontend:custom-v1.0 \
  10.208.173.121:88/cube-studio/kubeflow-dashboard-frontend:custom-v1.0

docker push 10.208.173.121:88/cube-studio/kubeflow-dashboard-frontend:custom-v1.0
```

#### 3.4.2 构建后端镜像

```bash
# 在项目根目录执行

# 1. 构建后端 Docker 镜像
docker build -t <your-registry>/kubeflow-dashboard:custom-v1.0 \
  -f install/docker/Dockerfile .

# 2. 推送到镜像仓库
docker push <your-registry>/kubeflow-dashboard:custom-v1.0
```

**示例（推送到内网 Harbor）**：

```bash
docker tag <your-registry>/kubeflow-dashboard:custom-v1.0 \
  10.208.173.121:88/cube-studio/kubeflow-dashboard:custom-v1.0

docker push 10.208.173.121:88/cube-studio/kubeflow-dashboard:custom-v1.0
```

### 3.5 部署到 Kubernetes

#### 3.5.1 修改镜像配置

编辑 `install/kubernetes/cube/overlays/kustomization.yml`：

```yaml
# 找到 images 部分，修改为自定义镜像
images:
- name: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard
  newName: 10.208.173.121:88/cube-studio/kubeflow-dashboard
  newTag: "custom-v1.0"  # 改为自定义版本
- name: ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend
  newName: 10.208.173.121:88/cube-studio/kubeflow-dashboard-frontend
  newTag: "custom-v1.0"  # 改为自定义版本
```

#### 3.5.2 应用更新

```bash
cd install/kubernetes

# 方式1：使用 kubectl apply
kubectl apply -k cube/overlays/

# 方式2：重启 Deployment（如果只是镜像更新）
kubectl set image deployment/kubeflow-dashboard \
  kubeflow-dashboard=10.208.173.121:88/cube-studio/kubeflow-dashboard:custom-v1.0 \
  -n infra

kubectl set image deployment/kubeflow-dashboard-frontend \
  kubeflow-dashboard-frontend=10.208.173.121:88/cube-studio/kubeflow-dashboard-frontend:custom-v1.0 \
  -n infra

# 查看更新状态
kubectl rollout status deployment/kubeflow-dashboard -n infra
kubectl rollout status deployment/kubeflow-dashboard-frontend -n infra
```

#### 3.5.3 验证部署

```bash
# 1. 查看 Pod 状态
kubectl get pods -n infra | grep kubeflow-dashboard

# 2. 查看日志
kubectl logs -n infra deploy/kubeflow-dashboard --tail=50
kubectl logs -n infra deploy/kubeflow-dashboard-frontend --tail=50

# 3. 访问应用
# 浏览器访问：http://<your-ip>/frontend/
# 角色管理：http://<your-ip>/myapp/roles/list
```

***

## 四、完整的二次开发工作流

### 4.1 开发流程

```
1. 本地开发
   ├── 前端：npm run dev（热更新）
   ├── 后端：flask run（开发模式）
   └── 测试功能

2. 构建镜像
   ├── 前端：npm run build → docker build
   └── 后端：docker build

3. 推送镜像
   ├── docker push 到 Harbor/DockerHub
   └── 确保 K8s 集群可访问

4. 部署更新
   ├── 修改 kustomization.yml
   ├── kubectl apply 或 kubectl set image
   └── 验证部署

5. 回滚（如有问题）
   └── kubectl rollout undo deployment/<name> -n infra
```

### 4.2 开发环境配置

#### 4.2.1 前端代理配置

编辑 `myapp/vision/src/setupProxy.js`：

```javascript
const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  // 代理后端 API 请求
  app.use(
    '/myapp',
    createProxyMiddleware({
      target: 'http://localhost:8080',  // 后端开发服务器地址
      changeOrigin: true,
    })
  );
};
```

#### 4.2.2 后端配置

编辑 `myapp/config.py`（开发环境配置）：

```python
# 开发环境配置
DEBUG = True
SQLALCHEMY_DATABASE_URI = 'mysql://root:admin@localhost:3306/kubeflow'

# CORS 配置（允许前端跨域）
ENABLE_CORS = True
CORS_OPTIONS = {
    'origins': ['http://localhost:3000'],  # 前端开发服务器地址
    'supports_credentials': True
}
```

### 4.3 常见问题排查

#### 问题 1：前端构建失败

```bash
# 清理缓存重新安装
cd myapp/vision
rm -rf node_modules package-lock.json
npm install
npm run build
```

#### 问题 2：后端 API 404

```bash
# 检查路由注册
# 在 myapp/views/view_user_role.py 确认：
appbuilder.add_api(Role_ModelView_Api)

# 重启后端
kubectl rollout restart deploy/kubeflow-dashboard -n infra
```

#### 问题 3：镜像拉取失败

```bash
# 检查镜像是否推送成功
docker images | grep kubeflow-dashboard

# 检查 K8s 是否能访问镜像仓库
kubectl run test --image=10.208.173.121:88/cube-studio/kubeflow-dashboard:custom-v1.0 --rm -it -- bash

# 配置 imagePullSecrets（如需要）
kubectl create secret docker-registry harbor-secret \
  --docker-server=10.208.173.121:88 \
  --docker-username=admin \
  --docker-password=Harbor12345 \
  -n infra

# 在 Deployment 中引用
kubectl patch deployment kubeflow-dashboard -n infra -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"harbor-secret"}]}}}}'
```

#### 问题 4：Pod 启动失败

```bash
# 查看详细错误
kubectl describe pod <pod-name> -n infra
kubectl logs <pod-name> -n infra --previous

# 常见原因：
# 1. 镜像拉取失败 → 检查镜像地址和认证
# 2. 配置错误 → 检查 ConfigMap
# 3. 数据库连接失败 → 检查数据库配置
```

***

## 五、快速启用角色管理（推荐方案）

如果你只是想快速启用角色管理功能，**无需修改代码**，按以下步骤操作：

### 5.1 直接访问后端管理界面

```bash
# 1. 登录 CubeStudio
http://<your-ip>/frontend/

# 2. 在浏览器地址栏直接访问角色管理
http://<your-ip>/myapp/roles/list

# 3. 如果提示权限不足，确保你的账号有 Admin 角色
```

### 5.2 添加菜单快捷方式（可选）

如果想在界面上添加快捷入口，可以通过配置文件添加链接：

编辑 `install/kubernetes/cube/overlays/config/config.py`：

```python
# 在文件末尾添加
ALL_LINKS = [
    {
        'label': '角色管理',
        'url': '/myapp/roles/list'
    },
    {
        'label': '用户管理',
        'url': '/myapp/users/list'
    }
]
```

更新配置：

```bash
# 1. 更新 ConfigMap
kubectl create configmap kubeflow-dashboard-config \
  --from-file=config.py=install/kubernetes/cube/overlays/config/config.py \
  -n infra \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. 重启后端
kubectl rollout restart deploy/kubeflow-dashboard -n infra
```

***

## 六、总结

### 6.1 关键要点

1. **角色管理功能已存在**：后端 API 完整，可直接通过 `/myapp/roles/list` 访问
2. **前端是独立的**：主要用于任务流编排，用户/角色管理在后端 Flask-AppBuilder 界面
3. **二次开发流程**：
   - 前端：React + TypeScript，使用 `npm run build` 构建
   - 后端：Flask + SQLAlchemy，修改 Python 代码
   - 部署：构建 Docker 镜像 → 推送到仓库 → 更新 K8s Deployment

### 6.2 推荐方案

**如果只是使用角色管理**：

- ✅ 直接访问 `http://<ip>/myapp/roles/list`
- ✅ 无需修改代码和重新部署

**如果需要定制界面**：

- ✅ 修改前端代码（添加页面和路由）
- ✅ 构建自定义镜像
- ✅ 部署到 K8s

### 6.3 参考资料

- **CubeStudio 官方文档**：<https://github.com/tencentmusic/cube-studio>
- **Flask-AppBuilder 文档**：<https://flask-appbuilder.readthedocs.io/>
- **React 官方文档**：<https://react.dev/>

***

**文档版本**：v1.0\
**更新日期**：2026.05.11\
**适用版本**：CubeStudio 2026.03.01+