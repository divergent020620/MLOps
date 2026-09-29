# 实现计划

## 功能 1：Notebook 数据集动态挂载（对标 workspace PVC）

### 改动清单

| # | 文件 | 改动 | 行数 |
|---|------|------|------|
| 1 | `myapp/utils/py/py_k8s.py` | 新增 `(pvc-ro)` 挂载类型 | +12 |
| 2 | `myapp/models/model_team.py` | `project.volume_mount` 自动补 `kubeflow-dataset(pvc-ro):/mnt/datasets` | +8 |
| 3 | `install/kubernetes/pv-pvc-jupyter.yaml` | 新增 PV+PVC：`kubeflow-dataset`（ReadOnlyMany，hostPath→/data/k8s/kubeflow/dataset） | +30 |

### 验证
- 新建 notebook → `kubectl get pod <name> -o yaml` 能看到 `kubeflow-dataset` PVC 挂载，`readOnly: true`
- 容器内 `ls /mnt/datasets` 可读、`touch /mnt/datasets/test` 失败

---

## 功能 2：批处理推理服务

### 改动清单

| # | 文件 | 改动 |
|---|------|------|
| 1 | `myapp/utils/py/py_k8s.py` | `__init__` 加 `BatchV1Api`；新增 `create_cronjob`/`delete_cronjob`/`create_job`/`delete_job` |
| 2 | `myapp/models/model_serving.py` | `InferenceService` 加 `deploy_type`（online/batch）+ `schedule` 列，更新 `clone()` |
| 3 | `myapp/views/view_inferenceserving.py` | 表单加 `deploy_type`/`schedule`；`deploy()` 分支 batch；新增 `run_batch` 端点；`delete_old_service` 加 cronjob/job 清理 |
| 4 | `myapp/migrations/versions/` | 新建迁移：`inferenceservice` 表加 `deploy_type`、`schedule` 列 |

### 验证
- 创建 `deploy_type=batch` + cron 表达式 → 部署 → `kubectl get cronjob` 有对应 CronJob
- 点击「批处理运行」→ 立即产生一次性 Job，跑完退出
- 清理 → CronJob/Job 被删除