# 全局DNS配置 - 实现计划

## 概述

为Cube Studio添加全局DNS配置功能：admin可在界面配置额外DNS nameservers/search domains/options，所有Pod创建时自动注入。

---

## Task 1: 创建数据模型

### 文件: `myapp/models/model_platform_config.py` (新建)

```python
from flask_appbuilder import Model
from myapp.models.helpers import AuditMixinNullable
from myapp.models.base import MyappModelBase
from sqlalchemy import Column, Integer, String, Text


class PlatformConfig(Model, AuditMixinNullable, MyappModelBase):
    """
    平台全局配置表，只有一条记录（id=1）。
    """
    __tablename__ = 'platform_config'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='配置ID')

    dns_nameservers = Column(Text, default='',
        comment='额外DNS nameservers，每行一个IP，如: 10.0.0.1')

    dns_searches = Column(Text, default='',
        comment='额外DNS search domains，每行一个，如: spark.internal.local')

    dns_options = Column(Text, default='',
        comment='DNS options，每行一个 name:value，如: ndots:5')

    label_columns = {
        'id': 'ID',
        'dns_nameservers': '额外DNS服务器',
        'dns_searches': '额外搜索域',
        'dns_options': 'DNS选项',
        'created_on': '创建时间',
        'created_by': '创建人',
        'changed_on': '修改时间',
        'changed_by': '修改人',
    }

    def __repr__(self):
        return '平台全局配置'


# 导入到模型列表
```

**验证**: `python -c "from myapp.models.model_platform_config import PlatformConfig; print('OK')"`

---

## Task 2: 创建后端API视图

### 文件: `myapp/views/view_platform_config.py` (新建)

参考 `view_announcement.py` 的模式：

```python
from flask import g, jsonify
from flask_babel import lazy_gettext as _
from flask_appbuilder import expose
from flask_appbuilder.models.sqla.interface import SQLAInterface
from wtforms import StringField
import subprocess, re

from myapp.models.model_platform_config import PlatformConfig
from myapp.views.baseApi import MyappModelRestApi
from myapp.forms import MyBS3TextAreaFieldWidget
from myapp import appbuilder, conf, db
from myapp.utils.py import py_k8s


class PlatformConfig_ModelView_Api(MyappModelRestApi):
    datamodel = SQLAInterface(PlatformConfig)
    route_base = '/platform_config_modelview/api'
    label_title = '平台配置'
    primary_key = 'id'

    base_permissions = ['can_add', 'can_show', 'can_edit', 'can_list', 'can_delete']
    base_order = ('id', 'desc')
    order_columns = ['id', 'created_on', 'changed_on']

    list_columns = ['id', 'dns_nameservers', 'dns_searches', 'dns_options',
                    'created_on', 'created_by', 'changed_on', 'changed_by']
    add_columns = ['dns_nameservers', 'dns_searches', 'dns_options']
    edit_columns = ['dns_nameservers', 'dns_searches', 'dns_options']
    show_columns = add_columns + ['created_on', 'changed_on']

    edit_form_extra_fields = {
        'dns_nameservers': StringField(
            label=_('额外DNS服务器'),
            description=_('每行一个IP地址，这些DNS服务器会被追加到K8s默认DNS之后'),
            widget=MyBS3TextAreaFieldWidget(rows=5),
        ),
        'dns_searches': StringField(
            label=_('额外搜索域'),
            description=_('每行一个域名，会自动补充K8s默认搜索域'),
            widget=MyBS3TextAreaFieldWidget(rows=5),
        ),
        'dns_options': StringField(
            label=_('DNS选项'),
            description=_('每行一个 name:value，如 ndots:5'),
            widget=MyBS3TextAreaFieldWidget(rows=5),
        ),
    }

    # --- 权限钩子 ---
    def pre_add(self, item):
        if not g.user.is_admin():
            raise Exception('仅管理员可操作平台配置')
        # 只允许一条记录
        existing = db.session.query(PlatformConfig).first()
        if existing:
            raise Exception('已存在平台配置，请使用编辑功能')

    def pre_update(self, item):
        if not g.user.is_admin():
            raise Exception('仅管理员可操作平台配置')

    def pre_delete(self, item):
        if not g.user.is_admin():
            raise Exception('仅管理员可操作平台配置')

    def post_add(self, item):
        """新增后刷新app.config中的DNS值"""
        self._refresh_config()

    def post_update(self, item):
        """更新后刷新app.config中的DNS值"""
        self._refresh_config()

    def _refresh_config(self):
        """从数据库读取DNS配置，写入app.config（运行时缓存）"""
        config = db.session.query(PlatformConfig).filter_by(id=1).first()
        if config:
            conf['DNS_NAMESERVERS'] = config.dns_nameservers or ''
            conf['DNS_SEARCHES'] = config.dns_searches or ''
            conf['DNS_OPTIONS'] = config.dns_options or ''
        else:
            conf['DNS_NAMESERVERS'] = ''
            conf['DNS_SEARCHES'] = ''
            conf['DNS_OPTIONS'] = ''

    # --- 自定义端点 ---
    @expose('/dns_detect/', methods=['GET'])
    def dns_detect(self):
        """读取本机 /etc/resolv.conf 和 /etc/hosts"""
        if not g.user.is_admin():
            return self.response(403, message='仅管理员可用')
        try:
            result = {'resolv_conf': '', 'hosts': ''}
            try:
                with open('/etc/resolv.conf', 'r') as f:
                    result['resolv_conf'] = f.read()
            except:
                result['resolv_conf'] = ''
            try:
                with open('/etc/hosts', 'r') as f:
                    result['hosts'] = f.read()
            except:
                result['hosts'] = ''
            return self.response(200, data=result, message='ok', status=0)
        except Exception as e:
            return self.response(500, message=str(e), status=1)

    @expose('/dns_apply_all/', methods=['POST'])
    def dns_apply_all(self):
        """更新配置并应用到所有现存Pod"""
        if not g.user.is_admin():
            return self.response(403, message='仅管理员可用')
        try:
            self._refresh_config()
            # 收集所有namespace
            k8s_client = py_k8s.K8s()
            namespaces = conf.get('K8S_NAMESPACES', ['pipeline', 'jupyter', 'service', 'kubeflow', 'inf')]  # 根据实际配置调整
            results = {'restarted': [], 'failed': [], 'skipped': []}
            for ns in namespaces:
                try:
                    # 获取所有deployment
                    deps = k8s_client.AppsV1Api.list_namespaced_deployment(namespace=ns)
                    for dep in deps.items:
                        try:
                            # 通过patch annotation触发滚动重启
                            body = {
                                "spec": {
                                    "template": {
                                        "metadata": {
                                            "annotations": {
                                                "kubectl.kubernetes.io/restartedAt": str(int(time.time()))
                                            }
                                        }
                                    }
                                }
                            }
                            k8s_client.AppsV1Api.patch_namespaced_deployment(
                                name=dep.metadata.name, namespace=ns, body=body)
                            results['restarted'].append(f"{ns}/{dep.metadata.name}")
                        except Exception as e:
                            results['failed'].append(f"{ns}/{dep.metadata.name}: {str(e)}")
                            
                    # 获取所有statefulset
                    stss = k8s_client.AppsV1Api.list_namespaced_stateful_set(namespace=ns)
                    for sts in stss.items:
                        try:
                            body = {
                                "spec": {
                                    "template": {
                                        "metadata": {
                                            "annotations": {
                                                "kubectl.kubernetes.io/restartedAt": str(int(time.time()))
                                            }
                                        }
                                    }
                                }
                            }
                            k8s_client.AppsV1Api.patch_namespaced_stateful_set(
                                name=sts.metadata.name, namespace=ns, body=body)
                            results['restarted'].append(f"{ns}/{sts.metadata.name}")
                        except Exception as e:
                            results['failed'].append(f"{ns}/{sts.metadata.name}: {str(e)}")
                except Exception as e:
                    results['skipped'].append(f"namespace {ns}: {str(e)}")
            return self.response(200, data=results, message=f'更新完成: {len(results["restarted"])}成功, {len(results["failed"])}失败', status=0)
        except Exception as e:
            return self.response(500, message=str(e), status=1)


# 注册
appbuilder.add_api(PlatformConfig_ModelView_Api)
```

### 注册到 `myapp/__init__.py`

在文件末尾 `from myapp import views` 之后，`model_platform_config` 会自动被发现（因为在models目录下）。需确保在 `static_urls` 中（如果不需要登录认证白名单就跳过）。

---

## Task 3: 启动时加载DNS配置

### 文件: `myapp/__init__.py` (修改)

在app创建后，添加DNS配置加载逻辑。找到合适位置（约在view注册之后），添加：

```python
# 在 app 创建和 db 初始化之后，views 加载之前
# 加载平台全局配置（DNS等）
from myapp.models.model_platform_config import PlatformConfig
try:
    config = db.session.query(PlatformConfig).filter_by(id=1).first()
    if config:
        conf['DNS_NAMESERVERS'] = config.dns_nameservers or ''
        conf['DNS_SEARCHES'] = config.dns_searches or ''
        conf['DNS_OPTIONS'] = config.dns_options or ''
except Exception as e:
    # 表还不存在（首次部署）时忽略
    pass
```

**验证**: 启动app不报错

---

## Task 4: 修改 make_pod 注入DNS

### 文件: `myapp/utils/py/py_k8s.py` (修改)

在 `make_pod` 方法中，在 host_aliases 构建之后、V1PodSpec 构建之前（约第1306行之后），添加DNS配置：

```python
        # 注入DNS配置 (在第1306行 service_account = ... 之后)
        # 读取全局DNS配置
        dns_nameservers_str = conf.get('DNS_NAMESERVERS', '')
        dns_searches_str = conf.get('DNS_SEARCHES', '')
        dns_options_str = conf.get('DNS_OPTIONS', '')

        dns_config = None
        if dns_nameservers_str or dns_searches_str or dns_options_str:
            # 构建额外的 nameservers
            nameservers = []
            if dns_nameservers_str:
                for line in dns_nameservers_str.strip().split('\n'):
                    ns = line.strip()
                    if ns:
                        nameservers.append(ns)

            # 构建 searches (K8s默认 + admin配置)
            # K8s默认搜索域
            k8s_default_searches = [
                namespace + '.svc.cluster.local',
                'svc.cluster.local',
                'cluster.local'
            ] if namespace else [
                'svc.cluster.local',
                'cluster.local'
            ]
            searches = list(k8s_default_searches)
            if dns_searches_str:
                for line in dns_searches_str.strip().split('\n'):
                    s = line.strip()
                    if s and s not in searches:
                        searches.append(s)

            # 构建 options
            options = []
            if dns_options_str:
                for line in dns_options_str.strip().split('\n'):
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':', 1)
                        opt = client.V1PodDNSConfigOption(
                            name=parts[0].strip(),
                            value=parts[1].strip() if len(parts) > 1 else ''
                        )
                        options.append(opt)

            dns_config = client.V1PodDNSConfig(
                nameservers=nameservers if nameservers else None,
                searches=searches if searches else None,
                options=options if options else None
            )

        # 修改V1PodSpec构造，添加dns_config
        spec = v1_pod_spec.V1PodSpec(
            affinity=affinity,
            image_pull_secrets=image_pull_secrets,
            node_selector=nodeSelector,
            node_name=node_name if node_name else None,
            volumes=k8s_volumes,
            containers=containers,
            restart_policy=restart_policy,
            host_aliases=host_aliases,
            service_account=service_account,
            scheduler_name=scheduler_name,
            dns_config=dns_config   # 新增
        )
```

**关键**: 不修改 `dns_policy` 字段，保持K8s默认 `ClusterFirst`。

**验证**: 创建一个debug pod，检查 `kubectl get pod <name> -o yaml | grep -A10 dnsConfig`

---

## Task 5: 创建前端页面

### 文件: `myapp/frontend/src/pages/PlatformConfig/index.tsx` (新建)

参考 `pages/HDFSConfig/index.tsx` 模式，使用 Ant Design Form + TextArea：

```tsx
import React, { useState, useEffect } from 'react';
import { Form, Input, Button, Card, Space, message, Spin, Typography, Row, Col } from 'antd';
import { SaveOutlined, ReloadOutlined, CloudServerOutlined } from '@ant-design/icons';
import axios from '../../api';

const { TextArea } = Input;
const { Title, Text } = Typography;

const PlatformConfig: React.FC = () => {
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [applying, setApplying] = useState(false);
    const [detectResult, setDetectResult] = useState<any>(null);

    // 加载已有配置
    useEffect(() => {
        loadConfig();
    }, []);

    const loadConfig = async () => {
        setLoading(true);
        try {
            const res = await axios.get('/platform_config_modelview/api/list/');
            const data = res.data?.result?.data;
            if (data && data.length > 0) {
                form.setFieldsValue(data[0]);
            }
        } catch (e) {
            // 尚未配置，忽略
        }
        setLoading(false);
    };

    // 保存（仅保存，新Pod生效）
    const handleSave = async () => {
        setSaving(true);
        try {
            const values = form.getFieldsValue();
            // 检查是否已有记录
            const listRes = await axios.get('/platform_config_modelview/api/list/');
            const existing = listRes.data?.result?.data;
            if (existing && existing.length > 0) {
                await axios.put(`/platform_config_modelview/api/${existing[0].id}`, values);
            } else {
                await axios.post('/platform_config_modelview/api/add', values);
            }
            message.success('DNS配置已保存，新创建的Pod将自动使用此配置');
        } catch (e: any) {
            message.error(e?.response?.data?.message || '保存失败');
        }
        setSaving(false);
    };

    // 保存并更新所有Pod
    const handleApplyAll = async () => {
        setApplying(true);
        try {
            // 先保存
            const values = form.getFieldsValue();
            const listRes = await axios.get('/platform_config_modelview/api/list/');
            const existing = listRes.data?.result?.data;
            if (existing && existing.length > 0) {
                await axios.put(`/platform_config_modelview/api/${existing[0].id}`, values);
            } else {
                await axios.post('/platform_config_modelview/api/add', values);
            }
            // 再应用
            const applyRes = await axios.post('/platform_config_modelview/api/dns_apply_all/');
            const result = applyRes.data?.result?.data;
            message.success(`配置已保存并应用！重启成功: ${result?.restarted?.length || 0}个`);
        } catch (e: any) {
            message.error(e?.response?.data?.message || '操作失败');
        }
        setApplying(false);
    };

    // 读取本机DNS
    const handleDetect = async () => {
        setLoading(true);
        try {
            const res = await axios.get('/platform_config_modelview/api/dns_detect/');
            const data = res.data?.result?.data;
            if (data) {
                setDetectResult(data);
                // 解析 resolv.conf
                if (data.resolv_conf) {
                    const nameservers: string[] = [];
                    const searches: string[] = [];
                    const options: string[] = [];
                    for (const line of data.resolv_conf.split('\n')) {
                        const trimmed = line.trim();
                        if (trimmed.startsWith('nameserver ')) {
                            nameservers.push(trimmed.substring('nameserver '.length).trim());
                        } else if (trimmed.startsWith('search ')) {
                            const domains = trimmed.substring('search '.length).trim().split(/\s+/);
                            searches.push(...domains);
                        } else if (trimmed.startsWith('options ')) {
                            options.push(trimmed.substring('options '.length).trim());
                        }
                    }
                    form.setFieldsValue({
                        dns_nameservers: nameservers.join('\n'),
                        dns_searches: searches.join('\n'),
                        dns_options: options.join('\n'),
                    });
                }
                message.success('已读取本机DNS配置，请确认后保存');
            }
        } catch (e: any) {
            message.error('读取本机DNS失败');
        }
        setLoading(false);
    };

    return (
        <Card bordered={false}>
            <Spin spinning={loading}>
                <Title level={4}>平台全局DNS配置</Title>
                <Text type="secondary" style={{ marginBottom: 24, display: 'block' }}>
                    配置额外的DNS服务器、搜索域和选项。保存后新创建的Pod自动注入；
                    "更新所有Pod"会触发滚动重启使配置对现有Pod生效。
                </Text>

                <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
                    <Form.Item name="dns_nameservers" label="额外DNS服务器 (nameservers)">
                        <TextArea rows={4} placeholder="每行一个IP地址&#10;例如:&#10;10.0.0.1&#10;10.0.0.2" />
                    </Form.Item>
                    <Form.Item name="dns_searches" label="额外搜索域 (search domains)">
                        <TextArea rows={4} placeholder="每行一个域名&#10;例如:&#10;spark.internal.local&#10;db.internal.local" />
                    </Form.Item>
                    <Form.Item name="dns_options" label="DNS选项 (options)">
                        <TextArea rows={3} placeholder="每行一个 name:value&#10;例如:&#10;ndots:5&#10;timeout:2" />
                    </Form.Item>
                </Form>

                <Space size="middle" style={{ marginTop: 16 }}>
                    <Button icon={<ReloadOutlined />} onClick={handleDetect}>
                        读取本机DNS
                    </Button>
                    <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving}>
                        保存DNS
                    </Button>
                    <Button type="primary" danger icon={<CloudServerOutlined />} onClick={handleApplyAll} loading={applying}>
                        更新所有现存Pod
                    </Button>
                </Space>

                {detectResult && (
                    <Card title="本机DNS检测结果" size="small" style={{ marginTop: 24, maxWidth: 600 }}>
                        <Row gutter={16}>
                            <Col span={12}>
                                <pre style={{ fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
                                    {detectResult.resolv_conf || '(空)'}
                                </pre>
                                <Text type="secondary">/etc/resolv.conf</Text>
                            </Col>
                            <Col span={12}>
                                <pre style={{ fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
                                    {detectResult.hosts || '(空)'}
                                </pre>
                                <Text type="secondary">/etc/hosts (如需hosts映射请使用hostAliases)</Text>
                            </Col>
                        </Row>
                    </Card>
                )}
            </Spin>
        </Card>
    );
};

export default PlatformConfig;
```

### 文件: `myapp/frontend/src/pages/PlatformConfig/style.less` (新建，可以为空)

```less
// PlatformConfig styles
```

---

## Task 6: 注册前端路由

### 文件: `myapp/frontend/src/routerConfig.tsx` (修改)

在 `innerDynamicRouterConfig` 数组中（约第88行）添加：

```tsx
    {
        path: '/platformConfig',
        title: '平台配置',
        key: 'platform_config',
        icon: '',
        menu_type: 'innerRouter',
        isCollapsed: true,
        element: lazy2Compont(() => import("./pages/PlatformConfig/index"))
    },
```

---

## Task 7: 添加Admin菜单

### 文件: `myapp/views/home.py` (修改)

在 `if is_admin:` 块内（约第679行 announcement_setting 之后），添加：

```python
            # 平台配置菜单（仅管理员可见）
            platform_config_menu = {
                "name": 'platform_config',
                "title": __('平台配置'),
                "icon": '<svg t="1743484800000" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5300" width="128" height="128"><path d="M512 512m-447.4 0a447.4 447.4 0 1 0 894.8 0 447.4 447.4 0 1 0-894.8 0Z" fill="#666666" p-id="5301"></path><path d="M512 160L320 352h128v192h128V352h128L512 160zM512 864l192-192h-128V480h-128v192H320l192 192z" fill="#FFFFFF" p-id="5302"></path></svg>',
                "isMenu": True,
                "isExpand": True,
                "children": [
                    {
                        "name": 'platform_config',
                        "title": __('DNS配置'),
                        "icon": '<svg t="1743484800000" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" p-id="5300" width="128" height="128"><path d="M512 512m-447.4 0a447.4 447.4 0 1 0 894.8 0 447.4 447.4 0 1 0-894.8 0Z" fill="#666666" p-id="5301"></path><path d="M512 160L320 352h128v192h128V352h128L512 160zM512 864l192-192h-128V480h-128v192H320l192 192z" fill="#FFFFFF" p-id="5302"></path></svg>',
                        "menu_type": "innerRoute",
                        "url": "{host}/frontend/platformConfig".format(host=request.host_url.strip('/')),
                        "disable": not is_admin
                    }
                ]
            }
            projetc['children'].append(platform_config_menu)
```

---

## Task 8: 数据库迁移

### 创建迁移文件

```bash
cd /bdm/share_bdm/cube-studio-master/myapp
# 自动探测模型变化生成迁移脚本
flask db migrate -m "add platform_config table"
# 应用迁移
flask db upgrade
```

或者手动创建SQL:
```sql
CREATE TABLE IF NOT EXISTS platform_config (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    dns_nameservers TEXT DEFAULT '',
    dns_searches TEXT DEFAULT '',
    dns_options TEXT DEFAULT '',
    created_on DATETIME DEFAULT CURRENT_TIMESTAMP,
    changed_on DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by_fk INTEGER,
    changed_by_fk INTEGER
);
```

---

## 执行顺序

1. **Task 1** → 创建模型
2. **Task 8** → 数据库迁移（建表）
3. **Task 2** → 创建API视图
4. **Task 3** → 修改 __init__.py 加载配置
5. **Task 4** → 修改 make_pod 注入DNS
6. **Task 5** → 创建前端页面
7. **Task 6** → 注册前端路由
8. **Task 7** → 添加Admin菜单
9. **验证** → 自底向上端到端测试

## 文件修改清单

| # | 文件 | 操作 |
|---|------|------|
| 1 | `myapp/models/model_platform_config.py` | **新建** |
| 2 | `myapp/views/view_platform_config.py` | **新建** |
| 3 | `myapp/__init__.py` | **修改** - 加载DNS到app.config |
| 4 | `myapp/utils/py/py_k8s.py` | **修改** - make_pod()添加dns_config |
| 5 | `myapp/frontend/src/pages/PlatformConfig/index.tsx` | **新建** |
| 6 | `myapp/frontend/src/pages/PlatformConfig/style.less` | **新建** |
| 7 | `myapp/frontend/src/routerConfig.tsx` | **修改** - 添加路由 |
| 8 | `myapp/views/home.py` | **修改** - 添加菜单项 |
