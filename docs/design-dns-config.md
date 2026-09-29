# 全局 hostAliases 配置 - 最终设计文档

## 现状

Cube Studio **已有 hostAliases 机制**，分为两层：

| 层级 | 来源 | 管理方式 |
|------|------|----------|
| 平台全局 | `config.py` 的 `HOSTALIASES` | 写死在文件，改完要重启后端 |
| 任务模板 | Job Template 的"域名映射"字段 | UI 可编辑，只影响该模板的 Pod |

运行时两层的值会合并：
```python
host_aliases = config.py的HOSTALIASES + job_template的host_aliases
```

## 痛点

1. 全局 `HOSTALIASES` 写死在配置文件，改一次要重启后端
2. 历史 Pod 不受影响，得逐个手动重建
3. 没有"读取本机 /etc/hosts"的便利功能

## 方案

**不改动原有的 hostAliases 机制，只做增强：**

- 全局 hostAliases 新增一个**数据库来源**（`platform_config` 表）
- `make_pod()` 合并三个来源：config.py + 数据库 + 任务模板
- Admin 通过 Web UI 管理数据库里的值
- DNS nameservers/searches/options 字段预留（以后有 DNS 服务器了再用）

```
hostAliases 最终值 = config.py HOSTALIASES + 数据库 platform_config.host_aliases + 模板 host_aliases
```

**不破坏现有功能** — config.py 的 HOSTALIASES 继续有效，数据库为空时行为不变。

## UI 设计

```
┌─────────────────────────────────────────────────────────┐
│  平台全局配置                                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  全局 hostAliases (额外的 /etc/hosts 映射):              │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 192.168.100.1 spark-master.internal              │   │
│  │ 192.168.100.2 db.internal                        │   │
│  │ ...                                              │   │
│  └─────────────────────────────────────────────────┘   │
│  每行一条。会和 config.py 的 HOSTALIASES 及模板的合并     │
│                                                         │
│  [读取本机DNS]  [保存]  [更新所有现存Pod]                  │
│  读取服务器       新Pod    触发滚动重启，使配置对             │
│  /etc/hosts       生效      已有Pod也生效                  │
│                                                         │
│  ─────── 以下为 DNS 预留（暂无 DNS 服务器）───────────      │
│                                                         │
│  DNS nameservers（预留）:                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │                                                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  DNS search domains（预留）:                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │                                                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  DNS options（预留）:                                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │                                                  │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 数据模型

`platform_config` 表，只有一条记录（id=1）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `host_aliases` | Text | 额外 hostAliases，每行 `IP host1 host2` |
| `dns_nameservers` | Text | DNS nameservers（预留） |
| `dns_searches` | Text | DNS search domains（预留） |
| `dns_options` | Text | DNS options（预留） |

## 修改点

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `myapp/models/model_platform_config.py` | 新建 | 数据模型 |
| 2 | `myapp/views/view_platform_config.py` | 新建 | 后端API + 自定义端点 |
| 3 | `myapp/__init__.py` | 修改 | 启动时从DB加载配置到 app.config |
| 4 | `myapp/utils/py/py_k8s.py` | 修改 | make_pod() 合并数据库的 hostAliases |
| 5 | `myapp/frontend/src/pages/PlatformConfig/index.tsx` | 新建 | 前端页面 |
| 6 | `myapp/frontend/src/routerConfig.tsx` | 修改 | 添加路由（admin only） |
| 7 | `myapp/views/home.py` | 修改 | admin菜单添加"平台配置" |

## 关键行为

- **保存** → 写数据库，新 Pod 自动合并。现有 Pod 不受影响。
- **更新所有现存Pod** → 保存 + 滚动重启所有 Deployment/StatefulSet
- **读取本机DNS** → 读服务器 `/etc/hosts` 填充 hostAliases，读 `/etc/resolv.conf` 填充 DNS 字段
- **未配置时无影响** → 数据库为空时 hostAliases 保持原样
- **dnsPolicy 不变** → 保持 K8s 默认 ClusterFirst
