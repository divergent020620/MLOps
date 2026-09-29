# Cube Studio 定时批处理（CronJob）实施方案 —— 方案 B

## 一、改动总览

| 文件 | 改动 | 行数 |
|---|---|---|
| `myapp/utils/py/py_k8s.py` | 新增 `create_cronjob()` + `delete_cronjob()` | ~80行 |
| `myapp/models/model_serving.py` | Service 模型加 2 个字段 | ~10行 |
| `myapp/views/view_serving.py` | `deploy()` 分支 + `clear()`/`pre_delete()` 适配 | ~60行 |
| `myapp/tasks/schedules.py` | 可选：定时检查 CronJob 状态 | ~20行 |

---

## 二、`myapp/utils/py/py_k8s.py` —— 新增 CronJob K8s 操作

### 2.1 初始化 BatchV1Api

在 `__init__` 方法中（第59行附近）加一行：

```python
self.BatchV1Api = client.BatchV1Api(api_client)
```

### 2.2 新增 `create_cronjob()` 方法

在 `create_deployment` 方法后面添加。核心逻辑：用现有的 `make_pod()` 生成 Pod 模板，包进 CronJob。

```python
def create_cronjob(self, namespace, name, schedule, labels, command, args,
                   volume_mount, working_dir, node_selector, resource_memory,
                   resource_cpu, resource_gpu, image_pull_policy,
                   image_pull_secrets, image, hostAliases, env, privileged,
                   accounts, username, ports=None, annotations={},
                   successful_jobs_history_limit=3,
                   failed_jobs_history_limit=1,
                   concurrency_policy='Forbid'):
    """
    创建 K8s CronJob，用于定时批处理。
    CronJob 到时间自动创建 Job，Job 创建 Pod，Pod 跑完自动销毁。
    非执行时间 0 资源占用。
    """
    # 1. 复用现有 make_pod 生成 Pod 模板
    pod, pod_spec = self.make_pod(
        namespace=namespace, name=name, labels=labels,
        command=command, args=args, volume_mount=volume_mount,
        working_dir=working_dir, node_selector=node_selector,
        resource_memory=resource_memory, resource_cpu=resource_cpu,
        resource_gpu=resource_gpu, image_pull_policy=image_pull_policy,
        image_pull_secrets=image_pull_secrets, image=image,
        hostAliases=hostAliases, env=env, privileged=privileged,
        accounts=accounts, username=username, ports=ports,
        restart_policy='Never',  # 跑完不重启，Pod 自动终止
        annotations=annotations
    )

    # 2. 包装成 PodTemplateSpec
    pod_template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels, annotations=annotations),
        spec=pod_spec
    )

    # 3. 包装成 JobTemplateSpec
    job_template = client.V1JobTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=client.V1JobSpec(
            template=pod_template,
            backoff_limit=0,          # 失败不重试（定时任务下次自己跑）
            completions=1,            # 跑 1 次就完成
            parallelism=1,
            ttl_seconds_after_finished=3600  # Job 完成后 1 小时自动清理
        )
    )

    # 4. 包装成 CronJob
    cronjob_spec = client.V1CronJobSpec(
        schedule=schedule,  # 例如 "0 3 7 * *" (每月7号3点)
        job_template=job_template,
        successful_jobs_history_limit=successful_jobs_history_limit,
        failed_jobs_history_limit=failed_jobs_history_limit,
        concurrency_policy=concurrency_policy,  # Forbid: 上次没跑完下次不跑
        suspend=False
    )

    cronjob = client.V1CronJob(
        api_version='batch/v1',
        kind='CronJob',
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
            annotations=annotations
        ),
        spec=cronjob_spec
    )

    # 5. 创建或更新
    try:
        self.BatchV1Api.read_namespaced_cron_job(name=name, namespace=namespace)
        self.BatchV1Api.replace_namespaced_cron_job(
            name=name, namespace=namespace, body=cronjob)
    except ApiException as e:
        if e.status == 404:
            self.BatchV1Api.create_namespaced_cron_job(namespace, cronjob)
        else:
            raise
```

### 2.3 新增 `delete_cronjob()` 方法

```python
def delete_cronjob(self, namespace, name=None, labels=None):
    """删除 CronJob 及其关联的 Job"""
    if name:
        try:
            self.BatchV1Api.delete_namespaced_cron_job(
                name=name, namespace=namespace, grace_period_seconds=0)
        except ApiException as e:
            if e.status != 404:
                print(e)
    if labels:
        try:
            label_selector = ','.join(f"{k}={v}" for k, v in labels.items())
            # 删 CronJob
            cronjobs = self.BatchV1Api.list_namespaced_cron_job(
                namespace=namespace, label_selector=label_selector).items or []
            for cj in cronjobs:
                self.BatchV1Api.delete_namespaced_cron_job(
                    name=cj.metadata.name, namespace=namespace, grace_period_seconds=0)
            # 删孤儿 Job（CronJob 删了但 Job 可能还在）
            jobs = self.BatchV1Api.list_namespaced_job(
                namespace=namespace, label_selector=label_selector).items or []
            for job in jobs:
                self.BatchV1Api.delete_namespaced_job(
                    name=job.metadata.name, namespace=namespace, grace_period_seconds=0)
        except ApiException as e:
            if e.status != 404:
                print(e)
```

---

## 三、`myapp/models/model_serving.py` —— 模型扩展

在 `Service` 类中新增 2 个字段（约第58行 `expand` 字段附近）：

```python
# 新增：定时调度相关字段
schedule_type = Column(String(50), default='once',
    comment='调度类型: once(一次性服务) / cron(定时批处理)')
cron_expression = Column(String(100), default='',
    comment='Cron 表达式，如 0 3 7 * * (每月7号3点)')
```

字段说明：
- `schedule_type='once'` → 走现有 `create_deployment()` 逻辑（常驻服务）
- `schedule_type='cron'` → 走新增 `create_cronjob()` 逻辑（定时批处理）
- `cron_expression` → 标准 cron 5 段式

---

## 四、`myapp/views/view_serving.py` —— 视图逻辑适配

### 4.1 `deploy()` 方法分支（第198行）

只改方法中间的 K8s 创建部分（约第224-247行），在 `create_deployment` 调用处加分支：

```python
# === 分支：根据 schedule_type 决定创建 Deployment 还是 CronJob ===
if getattr(service, 'schedule_type', 'once') == 'cron' and \
   getattr(service, 'cron_expression', ''):
    # --- 定时批处理模式 ---
    k8s_client.create_cronjob(
        namespace=namespace,
        name=service.name,
        schedule=service.cron_expression,  # 例如 "0 3 7 * *"
        labels=labels, annotations=annotations,
        command=['bash', '-c', service.command] if service.command else None,
        args=None, volume_mount=volume_mount,
        working_dir=service.working_dir,
        node_selector=service.get_node_selector(),
        resource_memory=service.resource_memory,
        resource_cpu=service.resource_cpu,
        resource_gpu=service.resource_gpu if service.resource_gpu else '0',
        image_pull_policy=conf.get('IMAGE_PULL_POLICY', 'Always'),
        image_pull_secrets=image_pull_secrets,
        image=service.images,
        hostAliases=conf.get('HOSTALIASES', ''),
        env=env, privileged=None, accounts=None,
        username=service.created_by.username,
    )
    # CronJob 不需要 Service/Ingress，也不需要端口映射
    service.namespace = namespace
    expand = json.loads(service.expand) if service.expand else {}
    expand['status'] = 'online'
    service.expand = json.dumps(expand)
    db.session.commit()
    flash(__('定时批处理已部署，将在 %s 执行') % service.cron_expression, 'success')
    return redirect(conf.get("MODEL_URLS", {}).get("service", '/'))

# --- 一次性服务模式（现有逻辑不变）---
k8s_client.create_deployment(namespace=namespace, name=service.name, ...)
# ... 后续 create_service、create_istio_ingress、端口映射等不变 ...
```

### 4.2 `delete_old_service()` 方法（第152行）

新增一行 CronJob 清理：

```python
def delete_old_service(self, service_name, cluster, namespace):
    # ... 现有代码不变 ...
    k8s.delete_cronjob(namespace=namespace, name=service_name)  # ← 新增
```

### 4.3 表单字段配置

在 `add_form_extra_fields` 字典中新增两个字段：

```python
"schedule_type": StringField(
    _('调度类型'), default='once',
    description=_('once=一次性服务, cron=定时批处理'),
    widget=BS3TextFieldWidget(), validators=[Regexp('^(once|cron)$')]
),
"cron_expression": StringField(
    _('Cron表达式'), default='',
    description=_('格式: 分 时 日 月 周。例 0 3 7 * * = 每月7号3点'),
    widget=BS3TextFieldWidget(), validators=[Regexp('^[0-9*,/ \-]*$')]
),
```

`add_columns` 和 `edit_columns` 增加对应列：
```python
add_columns = columns + ['volume_mount', 'schedule_type', 'cron_expression']
edit_columns = add_columns
```

---

## 五、资源释放机制（保证不占资源）

CronJob 模式下的 Pod 生命周期：

```
非执行时间：
  K8s 控制平面仅有 CronJob 对象 (无 Pod) → CPU=0 内存=0

执行时间：
  CronJob Controller → Job → Pod(1个)
    └─ 执行命令 → exit 0 → Pod=Succeeded
      └─ ttl_seconds_after_finished=3600 → 1h 后自动清理
```

关键配置保证释放：
- `restart_policy='Never'` → 跑完就停，不重启
- `backoff_limit=0` → 失败不重试
- `ttl_seconds_after_finished=3600` → Job 完成后 1h 自动清理
- `concurrency_policy='Forbid'` → 上次没跑完则跳过本次
- `successful_jobs_history_limit=3` → 只保留最近 3 次 Job 记录

---

## 六、Cron 表达式参考

| 场景 | 表达式 |
|---|---|
| 每小时执行 | `0 * * * *` |
| 每2小时执行 | `0 */2 * * *` |
| 每天凌晨3点 | `0 3 * * *` |
| 每月7号3点 | `0 3 7 * *` |
| 每周一9点 | `0 9 * * 1` |
| 每5分钟（调试） | `*/5 * * * *` |

格式：`分 时 日 月 周`

---

## 七、前端适配

Flask-AppBuilder 会根据模型列的变更自动生成表单字段，无需新建前端页面。

可选后续迭代：
- `schedule_type` 改为下拉框
- 选 `cron` 时才显示 `cron_expression`（前端联动）
- 列表页显示 CronJob 最近执行状态

---

## 八、部署执行顺序

```bash
# 1. 改代码（上述文件）

# 2. 数据库迁移（新增 2 列）
myapp db migrate -m "add schedule_type and cron_expression to service"
myapp db upgrade

# 3. 重启后端
kubectl delete pod -n infra -l app=kubeflow-dashboard

# 4. 验证
# UI: 新建服务，schedule_type=cron，cron_expression=*/5 * * * * (每5分钟)
# 部署后 kubectl get cronjob -n service-<project> 确认创建成功
```