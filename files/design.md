# 设计文档：Notebook 全局挂载 + 批处理推理服务

## 一、背景与目标

### 功能 1：Notebook 全局挂载（管理员）
**问题**：用户创建 notebook 后无法读取数据集，需管理员逐一手动修改每个 notebook 的 `volume_mount`，补上：
```
kubeflow-user-workspace(pvc):/mnt,10.240.125.39/bdm/share_bdm/kubeflow/dataset(nfs-ro):/mnt/admin/datasets
```
**目标**：管理员在平台配置里设置一条「notebook 全局挂载」，所有 notebook 在创建/重置 pod 时自动合并注入，无需手动逐个改。

### 功能 2：批处理推理服务
**问题**：当前推理服务只有在线服务（Deployment + Service + istio ingress + HPA），只能常驻 Pod 提供服务。
**目标**：增加「批处理」部署方式——通过 K8s CronJob 定时、以及手动触发一次性 Job 运行推理命令，跑完即退出，不创建 Service/ingress/HPA。

---

## 二、关键设计决策

### 决策 1：复用 `PlatformConfig` 单例表存全局挂载
- 现有 `myapp/models/model_platform_config.py` 的 `PlatformConfig`（id=1）已是「管理员全局配置」单例，含 `host_aliases`、`dns_*`，并通过 `get_platform_config()` 懒加载进 `conf`，在 `py_k8s.py::make_pod` 里合并注入（见 `py_k8s.py:1306-1315`）。
- **方案**：在 `PlatformConfig` 新增 `notebook_volume_mount` 列，复用同一套懒加载/合并机制。不动 `myapp/config.py`（那个文件是空的），全局挂载数据进 DB。

### 决策 2：挂载在「创建/重置 pod 时」合并注入（而非仅新建时写入）
- 用户已确认选择「创建/重置时合并注入」。
- 好处：管理员之后改了全局挂载，用户点 reset 即生效；已存在 notebook 无需重新填写。
- 实现：在 `view_notebook.py` 的 `reset_theia()` 与 `entry_jupyter()` 两处生成 pod 前，用 `core.merge_volume_mount(notebook.volume_mount, 全局挂载)` 合并。
  - `core.merge_volume_mount(*args)`（`core.py:2182`）按「容器挂载路径」去重、保留首个，因此用户/项目自己的挂载优先，全局挂载只补齐缺失的（如 `/mnt/admin/datasets`），不覆盖用户已有的 `/mnt`。
- 说明：不放在 `make_pod`（那会影响 pipeline/service 等所有 pod，超出 notebook 范围）。

### 决策 3：批处理推理复用 `InferenceService` 模型，新增「部署方式」字段
- 不新建模型，新增两个字段区分在线/批处理，最大化复用镜像、命令、环境变量、挂载、资源配置等字段：
  - `deploy_type`：`online`（默认，现状）| `batch`
  - `schedule`：cron 表达式，仅 `deploy_type='batch'` 时使用
- 数据流理解（对齐用户说明）：数据集放在 NFS 上（只读挂载，如 `.../dataset(nfs-ro):/mnt/admin/datasets`），模型命令**逐次/流式读取**（避免一次性加载超大数据集），结果写回可写挂载（PVC workspace）。因此**不需要**额外的「输入/输出路径」专用字段——复用现有 `volume_mount` + `command` + `model_path` 即可，用户按 pipeline task 的写法自己写命令。

### 决策 4：触发方式 = CronJob + 手动 Job
- 用户已确认「两者都要」。
- CronJob：按 `schedule` 定时创建 Job。
- 手动触发：新增 `run_batch` 端点，点一次创建一次性 Job。

### 决策 5：前端 = FAB 表单扩展（用户已确认）
- 功能 1：扩展 `PlatformConfig` 管理表单（`view_platform_config.py`）。
- 功能 2：扩展 `InferenceService` 表单（`view_inferenceserving.py`）+ 列表列 + 批量运行操作按钮。

---

## 三、后端改动清单

### 3.1 数据库模型

**`myapp/models/model_platform_config.py`** — 新增一列：
```python
notebook_volume_mount = Column(Text, default='',
    comment='notebook 全局挂载，格式同 volume_mount，每行或逗号分隔，如 kubeflow-user-workspace(pvc):/mnt,10.240.125.39/bdm/share_bdm/kubeflow/dataset(nfs-ro):/mnt/admin/datasets')
```
并补充 `label_columns['notebook_volume_mount']`。

**`myapp/models/model_serving.py`** — `InferenceService` 新增两列：
```python
deploy_type = Column(String(50), default='online', comment='部署方式: online在线/batch批处理')
schedule = Column(String(200), default='', comment='批处理cron表达式，如 0 2 * * *')
```
`clone()` 方法补充这两个字段。

### 3.2 配置懒加载

**`myapp/__init__.py`** — `_load_platform_config()` 增加：
```python
conf['NOTEBOOK_GLOBAL_VOLUME_MOUNT'] = config_row.notebook_volume_mount or ''
```
（`get_platform_config` 无需改，已通用。）

### 3.3 Notebook 挂载合并注入

**`myapp/views/view_notebook.py`**：
- 新增辅助方法（放在 `Notebook_ModelView_Base`）：
```python
def get_merged_volume_mount(self, notebook):
    global_mount = get_platform_config('NOTEBOOK_GLOBAL_VOLUME_MOUNT', '')
    return core.merge_volume_mount(notebook.volume_mount or '', global_mount)
```
- `reset_theia()`：`volume_mount = self.get_merged_volume_mount(notebook)`（替换现有第 604 行 `volume_mount = notebook.volume_mount`）。
- `entry_jupyter()`：`make_pod(volume_mount=self.get_merged_volume_mount(notebook))`（替换现有第 512 行 `volume_mount=notebook.volume_mount`）。
- 顶部 import `get_platform_config`（`from myapp import ... get_platform_config`）。

### 3.4 K8s 客户端新增 CronJob / Job

**`myapp/utils/py/py_k8s.py`**：
- `__init__` 增加 `self.batch_v1 = client.BatchV1Api(api_client)`。
- 新增 `create_cronjob(...)`：复用 `make_pod`（`restart_policy='OnFailure'`）得到 `pod_spec`，包装成 `V1CronJob`，含 `schedule`、`concurrency_policy='Forbid'`、`successful_jobs_history_limit`/`failed_jobs_history_limit`。
- 新增 `create_job(...)`：同上，包装成 `V1Job`（`backoff_limit`）。
- 新增 `delete_cronjob(...)` / `delete_job(...)`：仿照 `delete_deployment` 的 404 忽略写法。
- 说明：`make_pod` 返回 `(pod, pod_spec)`，`pod_spec` 是 `V1PodSpec`，可直接作为 `V1PodTemplateSpec(spec=pod_spec)`，无需复制 make_pod 内部逻辑。

### 3.5 推理服务视图

**`myapp/views/view_inferenceserving.py`**：
- `columns` / `show_columns` / `add_form_extra_fields` 增加 `deploy_type`（SelectField，`online`/`batch`）与 `schedule`（StringField，仅 batch 显示）。
- `list_columns` 增加 `deploy_type` 列（展示在线/批处理）。
- `deploy()` 开头分支：
  - `service.deploy_type == 'batch'` → 走批处理部署：清理旧在线资源（若有）→ `create_cronjob(...)`（若 `schedule` 非空），跳过 Deployment/Service/ingress/HPA 逻辑，`model_status='online'`（或新增 `batch` 状态）。
  - 否则走原在线部署逻辑（不变）。
- 新增 `@expose_api('/run_batch/<service_id>')`：手动创建一次性 `create_job(...)` 运行。
- `delete_old_service()` 增加 `delete_cronjob` / `delete_job` 清理。
- `operate_html` 增加「批处理运行」链接（batch 类型时显示）。

### 3.6 数据库迁移

新建 `myapp/migrations/versions/<revision>_add_notebook_global_mount_and_batch_inference.py`：
- `down_revision = 'f1x2m3e4r5g6'`（当前 head）
- `upgrade()`：`batch_alter_table('platform_config')` 加 `notebook_volume_mount`；`batch_alter_table('inferenceservice')` 加 `deploy_type`、`schedule`。
- `downgrade()`：对应删列。

---

## 四、前端改动清单（FAB 表单）

### 4.1 平台配置页
- `view_platform_config.py`：`list_columns`/`add_columns`/`edit_columns`/`show_columns` 加 `notebook_volume_mount`；`edit_form_extra_fields` 加 TextArea 字段（description 写清格式，参考 notebook 表单里的挂载说明）；`_refresh_config` 同步 `conf['NOTEBOOK_GLOBAL_VOLUME_MOUNT']`。

### 4.2 推理服务表单
- 新增 `deploy_type` 下拉（在线/批处理）、`schedule` 输入框（cron 表达式，description 说明格式与仅在批处理时生效）。
- 列表新增「部署方式」列；批处理类型记录新增「批处理运行」操作链接。

---

## 五、验证方案

1. **Notebook 全局挂载**：管理员在平台配置填写全局挂载 → 用户新建/重置 notebook → 查看 pod 的 `volumeMounts` 包含 `/mnt/admin/datasets`（只读 NFS），且用户已有 `/mnt` 不被覆盖；容器内 `ls /mnt/admin/datasets` 可读到数据。
2. **批处理推理**：
   - 创建 `deploy_type=batch` + cron 表达式 → 部署 → `kubectl get cronjob` 有对应 CronJob，等待调度产生 Job/Pod 并正常结束。
   - 点「批处理运行」→ 立即产生一次性 Job，跑完退出，结果写回挂载目录。
   - 清理 → CronJob/Job 被删除。

---

## 六、风险与注意点

- `merge_volume_mount` 按容器路径去重；若管理员全局挂载的目标路径与用户自定义路径冲突，用户自定义优先（符合预期）。
- CronJob 的 `restart_policy` 必须为 `Never`/`OnFailure`（不能用 Always），`make_pod` 需显式传 `restart_policy='OnFailure'`。
- 批处理类型服务无常驻 pod，`ready`/`status_url` 等在线状态逻辑需对 batch 类型降级（显示 k8s 链接即可），避免调用 `read_namespaced_endpoints` 报错。
