# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note**: `CLAUDE.md` and `AGENTS.md` at the repo root are kept byte-identical except for the title and the "Codex" vs "Claude Code" line. If you change one, change the other.

## Project Overview

Cube Studio is an open-source cloud-native machine learning platform (一站式云原生机器学习平台) providing end-to-end MLOps: pipeline orchestration (Argo Workflows), Jupyter notebooks, model training/serving, dataset management, AI Hub, ChatGPT/RAG integration, and data middleware (SQLLab, metadata management, HDFS). Built on Kubernetes with Flask+React.

`README.md` is a one-line placeholder (`# MLOps`) — it carries no information.

## Architecture

### Backend (Python/Flask + Flask-AppBuilder)
- **Framework**: Flask with Flask-AppBuilder (FAB) for admin UI, RBAC, and REST API generation
- **Database**: MySQL 8.0 (primary via SQLAlchemy 1.4), Redis (cache + Celery broker)
- **Async Tasks**: Celery with Redis broker; beat scheduler for cron jobs
- **K8s Integration**: `kubernetes` Python client; all workload types (jobs, notebooks, services, inference) are created as K8s pods via `myapp/utils/py/py_k8s.py`

### Frontend (React/TypeScript)
Three separate apps built into static files served by nginx:
- **myapp/frontend**: Main platform UI (React 17, Ant Design 4, TypeScript)
- **myapp/vision**: AI Pipeline visual DAG editor (workflow orchestration)
- **myapp/visionPlus**: Data ETL Pipeline visual editor

`myapp/frontend/package.json` exposes `start`, `build` (aliases `buildSelf`, `APP_ENV=frontend`) and a separate `buildFab` (`APP_ENV=fab`) — two distinct build targets, not one.

### Container Startup (`install/docker/entrypoint.sh`)
The `STAGE` env var controls what the container does on start:
- `build`: Runs `npm install && npm run build` for all three frontends, then exits
- `dev`: Runs `python myapp/run.py` (Flask dev server on port 80)
- `prod`: Runs `gunicorn --workers 20 --worker-class=gevent --timeout 300 myapp:app`

Before `dev`/`prod` it always runs, in order: create symlinks for workspace/dataset/aihub → `create_db.py` → Redis-locked `db upgrade` → `fab create-admin` → `myapp init` → `myapp/check_tables.py`.

Two consequences worth internalizing:

- **`myapp init` runs on every backend start** (it is suffixed `|| true`, so failures are swallowed). It re-seeds demo data from `myapp/init/*.json`. **Deleting a seeded record from the database is not enough to remove a feature — the seed source must be edited too, or it comes back on the next restart.**
- **`myapp/check_tables.py` gates startup**: it asserts all 40 expected tables exist and calls `exit(1)` otherwise, printing "table X 不完整，请 1、mysql: drop database, 2、重启当前pod". A partially-migrated database therefore presents as a crash-looping pod, not as a runtime error.

### HA: Redis Distributed Lock for DB Migrations
In `entrypoint.sh`, before `myapp db upgrade`, the container acquires a Redis lock (`cube:db-upgrade-lock`) with `nx=True, ex=120`. Only one pod holds the lock at a time; others retry up to 30 times (60s). This prevents concurrent migration races when multiple backend pods start simultaneously.

### Config System — TWO diverging copies
The main config is **not** `myapp/config.py` (that file is 0 bytes). There are **two** real config files, and **they have diverged** — which one applies depends on how the platform is deployed:

| File | Used by | Distinctive values |
|---|---|---|
| `install/docker/config.py` | `install/docker/docker-compose.yml` | Registry defaults point at Tencent `ccr.ccs.tencentyun.com/cube-studio/`; `SQLALCHEMY_POOL_SIZE=300`, `SQLALCHEMY_MAX_OVERFLOW=800`; has `HDFS_CONFIG` |
| `install/kubernetes/cube/overlays/config/config.py` | K8s, injected as ConfigMap `kubeflow-dashboard-config` via `install/kubernetes/cube/overlays/kustomization.yml` | Registry points at internal Harbor `192.168.11.12/cube-studio/`; `SQLALCHEMY_POOL_SIZE=100`, `SQLALCHEMY_MAX_OVERFLOW=300` (tuned so 2+2 pods don't exhaust MySQL `max_connections`); **no `HDFS_CONFIG`** |

If you edit one, check whether the other needs the same change — a fix in `install/docker/config.py` has no effect on the K8s deployment.

Both define:
- Loads env vars for DB (`MYSQL_SERVICE`), Redis, and `ENVIRONMENT`
- `CRD_INFO` — **10** custom resources: `workflow`, `tfjob`, `pytorchjob`, `mpijob`, `mxjob`, `paddlejob`, `xgbjob`, `sparkjob`, `vcjob`, `virtualservice`. Each entry carries a `timeout` used to garbage-collect stale instances.
- `CLUSTERS` dict mapping `ENVIRONMENT` → kubeconfig path + service domain — this is how multi-cluster works
- `GLOBAL_ENV`: template variables (`{{pipeline_id}}`, `{{creator}}`, `{{uuid.uuid4().hex}}`, etc.) injected as env vars into every pipeline task
- K8s namespace constants: `PIPELINE_NAMESPACE='pipeline'`, `SERVICE_PIPELINE_NAMESPACE='service'`, `SERVICE_NAMESPACE='service'`, `NOTEBOOK_NAMESPACE='jupyter'`, `AUTOML_NAMESPACE='automl'`, `AIHUB_NAMESPACE='aihub'`
- Container runtime abstraction: `CONTAINER_CLI='nerdctl'` (or `docker`), with separate socket mount paths
- `CeleryConfig`, including `beat_schedule` — **the cron schedule lives here, in config, not in `myapp/tasks/`**. Adding a periodic task means adding the `@celery_app.task` in `myapp/tasks/` **and** a `beat_schedule` entry in config.py.
- At bottom: `myapp_config` import overrides (local `config_local.py`)
- Lazy-loads `PlatformConfig` from DB via `_load_platform_config()` in `__init__.py`

### App Initialization (`myapp/__init__.py`)
Creates the Flask app, initializes SQLAlchemy, cache (Redis), Migrate, AppBuilder (FAB), CORS, CSRF, Talisman, and Compress. Key hooks:
- `@app.before_request`: Authentication check — allows `/static/`, `/login`, `/health`, etc. unauthenticated; supports cross-domain cookie auth (`myapp_username` cookie) and header-based auth (`Authorization` header)
- `@app.after_request`: Sets `myapp_username` cookie and applies HTTP headers
- `get_platform_config(key, default)`: Lazy-loads PlatformConfig from DB on first access

### Key Models (`myapp/models/`)
- **model_job.py**: `Repository`, `Images`, `Job_Template`, `Pipeline`, `Task` — core workflow entities. Pipeline has a `dag_json` defining task graph; Task references a Job_Template.
- **model_team.py**: `Project`, `Project_User` — multi-tenancy with org/project groups. Projects have types: `org`, `job-template`, `service`, etc.
- **model_notebook.py**: `Notebook` — Jupyter/VSCode environments
- **model_serving.py**: `InferenceService`, `Service` — model serving and internal services
- **model_dataset.py**: `Dataset` management
- **model_aihub.py**: `Aihub` — AI model hub (pre-built models with one-click deploy)
- **model_chat.py**: `Chat` — ChatGPT/LLM integration with knowledge base (RAG)
- **model_docker.py**: `Docker` — online image building
- **model_etl_pipeline.py**: `ETL_Pipeline` — data ETL workflows (Airflow/Azkaban/DolphinScheduler)
- **model_nni.py**: `NNI` — hyperparameter search
- **model_train_model.py**: `Training_Model` — trained model registry
- **model_platform_config.py**: `PlatformConfig` — singleton table (id=1) for global DNS config (nameservers, searches, options) and host aliases
- **model_metadata.py**, **model_metadata_metric.py**, **model_dimension.py**: Data catalog/metadata management

### Key Views (`myapp/views/`)
- **baseApi.py** (2,324 lines): `MyappModelView`, `MyappModelRestApi` base classes extending FAB's `ModelView`/`ModelRestApi` with custom CRUD, export, schema validation, and permission logic. Most views inherit from these.
- **base.py** (30 lines): `MyappModelView` class definition, re-exports FAB base classes
- **home.py** (741 lines): Dashboard and workflow execution APIs
- **view_chat.py** (1,535 lines): ChatGPT/LLM integration with knowledge base RAG
- **view_task.py**: 任务 — single-job execution (see "Two execution paths" below)
- **view_pipeline.py**: 任务流 — pipeline CRUD, DAG→Argo Workflow compilation (see below)
- **view_notebook.py**: Jupyter notebook lifecycle
- **view_serving.py**, **view_inferenceserving.py**: Model serving management
- **view_platform_config.py**: Admin-only global DNS configuration with `dns_detect` and `dns_apply_all` endpoints
- **view_etl_pipeline.py** + variants: ETL pipeline management for Airflow/Azkaban/DolphinScheduler
- Other views: `view_dataset.py`, `view_docker.py`, `view_team.py`, `view_job_template.py`, `view_images.py`, `view_nni.py`, `view_aihub.py`, `view_train_model.py`, `view_metadata.py`, `view_metadata_metric.py`, `view_dimension.py`, `view_sqllab.py`, `view_k8s.py`, `view_hdfs.py`, `view_runhistory.py`, `view_workflow.py`, `view_log.py`, `view_link.py`, `view_total_resource.py`, `view_user_role.py`, `view_announcement.py`

The user-visible menu labels come from each view's `label_title`. Two are easy to confuse: `view_task.py` is **`任务`**, `view_pipeline.py` is **`任务流`**.

### Central K8s Utility (`myapp/utils/py/py_k8s.py`)
The **single injection point** for all business pods. `make_pod()` creates `V1PodSpec` and is called by:
- `create_debug_pod()` — debug pods (Docker, Task debugging)
- `create_deployment()` — services, inference services
- `create_ReplicationController()` — RC deployments
- `create_statefulset()` — stateful services
- `create_job()` — K8s jobs

This is where DNS config, hostAliases, resource limits, volumes, and environment variables are injected. All changes to pod configuration for ALL workload types go through this method.

The same module also owns Istio ingress: `create_istio_ingress()` / `delete_istio_ingress()` build the `networking.istio.io/v1alpha3` `VirtualService` objects that expose notebooks, services, and inference endpoints. Callers: `view_notebook.py`, `view_serving.py`, `view_inferenceserving.py`, `view_nni.py`, `view_total_resource.py`. **It self-disables for IP hosts** — `create_istio_ingress` starts with `if not host or core.checkip(host): return`, so configuring a bare IP instead of a domain silently skips VirtualService creation (and the workload then relies on whatever other exposure path exists).

Other utils: `py_network.py` (only two helpers — `get_public_ip()` and `get_ips(domain)`; it is **not** involved in Istio routing), `py_prometheus.py` (metrics queries), `py_markdown.py` (doc rendering).

### Celery Tasks (`myapp/tasks/`)
- **schedules.py** (1,222 lines): implementations of the beat-scheduled tasks — delete old workflows, check pipeline runs, watch GPU utilization, check pod termination, clean debug dockers, etc. The *schedule* for these is in config.py's `CeleryConfig.beat_schedule`.
- **async_task.py**: Async task definitions for check_docker_commit, check_notebook_commit, upgrade_service, get_k8s_resource, upload_workflow, etc.
- **celery_app.py**: Celery app configuration
- **hdfs_tasks.py**: HDFS-related async operations

`check_notebook_commit` is on the critical path of the high-code workflow: after a user hits "save image" in Jupyter, a `notebook-commit-*` pod does `docker/nerdctl commit && push`, and this **worker-side** task polls it for up to 30 minutes and writes the resulting image name back to `notebook.images`. Removing the worker breaks image saving.

### CLI (`myapp/cli.py`)
`myapp init` command initializes the database with default data, seeded from `myapp/init/`:

```
init-project.json      init-job-template.json   init-pipeline.json
init-dataset.csv       init-service.json        init-inference.json
init-aihub.json        init-image.json          init-train-model.json
init-chat.json         init-etl-pipeline.json   init-automl.json
```

Uses the `replace_git()` function (`myapp/cli.py:33`) to rewrite GitHub URLs and image registry references based on config.

### K8s Custom Resources Managed
The platform orchestrates 10 CRD types defined in `CRD_INFO`:
- **argoproj.io/Workflow** — Argo Workflows for pipeline DAG execution
- **kubeflow.org**: TFJob, PyTorchJob, MPIJob, PaddleJob, MXJob
- **xgboostjob.kubeflow.org/XGBoostJob**
- **sparkoperator.k8s.io/SparkApplication**
- **batch.volcano.sh/Job** — Volcano batch scheduling
- **networking.istio.io/VirtualService** — Istio traffic routing for inference services

Each CRD has a `timeout` for automatic cleanup of stale resources.

## Development Commands

There is **no backend test suite** — no `tests/`, no pytest/tox/setup.cfg/pyproject config anywhere in the repo. The frontend has only CRA's default `myapp/frontend/src/App.test.tsx` (`npm test` runs `node scripts/test.js`). Verify changes by exercising the running platform, not by running tests.

### Build and Deploy

**Backend** (`build_backend.sh`):
```bash
bash build_backend.sh [TAG]  # defaults to $(date +%Y%m%d)
```
Generates a Dockerfile inline, builds `FROM 192.168.11.12/cube-studio/kubeflow-dashboard:20260703`, COPYs `myapp/`, pushes to `192.168.11.12/cube-studio/kubeflow-dashboard:$TAG`, then `kubectl set image` on **four** deployments in namespace `infra` — `kubeflow-dashboard`, `kubeflow-dashboard-schedule`, `kubeflow-dashboard-worker`, `kubeflow-watch` — and waits for rollout. The frontend is a separate image and is not touched.

**Frontend** (`build_frontend.sh`):
```bash
bash build_frontend.sh [TAG]
```
Runs `npm run build` in `myapp/frontend`, builds Docker image from nginx base, pushes, updates deployment, waits for rollout.

### Local Development (Docker Compose)
```bash
cd install/docker
docker-compose up
```
Frontend on http://localhost:80, credentials admin/admin. For faster backend iteration, change the `myapp` container command to `sleep 1000000`, then `docker exec` in and run `/entrypoint.sh` or `python myapp/run.py` manually. `beat`/`worker`/`watch` are present in the compose file but commented out.

### Database
```bash
export FLASK_APP=myapp:app
python myapp/create_db.py        # Create tables
myapp db upgrade                  # Run migrations
myapp fab create-admin ...        # Create admin user
myapp init                        # Seed default data (templates, pipelines, etc.)
```

### Frontend Dev Servers
```bash
cd myapp/frontend && npm install && npm run start   # → localhost:3000
cd myapp/vision && npm install && npm run start     # Vision pipeline editor
cd myapp/visionPlus && yarn && npm run build        # VisionPlus ETL editor
```

### Production (gunicorn)
```bash
gunicorn --bind 0.0.0.0:80 --workers 20 --worker-class=gevent --timeout 300 --limit-request-line 0 --limit-request-field_size 0 myapp:app
```

### Debugging Tools
- `@pysnooper.snoop()` decorator for function tracing (widely used in codebase)
- `proxy.py` (repo root) — Flask proxy on port 8080 that logs all requests; useful for debugging API calls
- `tools/stress_test.py`, `tools/stress_and_monitor.sh` — load testing
- `scripts/ha_test.sh`, `scripts/ha_full_test.sh` — HA failover testing

## Key Design Patterns

### Two execution paths: 任务 vs 任务流
These are separate features that both consume the same `Job_Template` rows but take completely different execution routes. Confusing them leads to wrong conclusions about which components are required.

| | 任务 (`view_task.py`) | 任务流 (`view_pipeline.py`) |
|---|---|---|
| Unit | one Job_Template | a DAG of Tasks |
| Execution | creates the K8s resource directly (`create_job` / `create_crd` on the template's CRD) | compiles to an **Argo Workflow** CR |
| Lands in | the project's namespace | `PIPELINE_NAMESPACE` (`pipeline`) |
| Status sync | direct | `kubeflow-watch` polls the Argo workflow and writes back to the `Workflow` table |

The 任务流 chain, end to end: `dag_to_pipeline()` (`view_pipeline.py:127`) builds the Workflow JSON → `run_pipeline()` (`:545`) submits it with `create_crd(... CRD_INFO['workflow'] ...)` → `workflow-controller` executes each DAG node as a pod → `kubeflow-watch` (`myapp/tools/watch_workflow.py`, entered via `supervisord`) mirrors status into the `Workflow` table and pushes notifications. Artifacts passed between steps go through MinIO.

Only 任务流 needs Argo. Inference services, notebooks, and 任务 do not.

### Storage model
There is **no StorageClass and no CSI driver** in the default deployment. Every PVC binds a statically-provisioned `hostPath` PV with `storageClassName: ""`, declared per-namespace in `install/kubernetes/pv-pvc-<namespace>.yaml` (`infra`, `jupyter`, `pipeline`, `service`, `automl`, `kubeflow`). All paths resolve under `/data/k8s/kubeflow/...`.

Because capacity is hand-written in those PV manifests, the declared sizes are not enforced and bear no relation to the underlying filesystem. When changing anything storage-related, account for the fact that PVC/PV size numbers are decorative.

Dataset files are also filesystem-based, not object-store-based: uploads land in the notebook's `/mnt/<user>` volume, and the backup action copies to a hostPath directory. `view_dataset.py:370` has an object-storage branch (`conf.get('STORE_TYPE', 'minio')` → `importlib.import_module(f'myapp.utils.store.{store_type}')`), but **`myapp/utils/store/` does not exist** and `STORE_TYPE` is set to `""` in both configs, so that branch raises if reached.

### PlatformConfig Lazy Loading
Global platform config (DNS, host aliases) is stored in a singleton DB row and lazy-loaded into `app.config` on first access via `get_platform_config()`. This avoids circular imports (config → models → config) since `__init__.py` must import views, which import models.

### RBAC and Multi-Tenancy
- Roles: Admin, Gamma, Public (ROBOT_PERMISSION_ROLES)
- Projects (type=`org`) provide team isolation; `Project_User` links users to projects with roles
- Views check project membership via `project_id` filtering
- `AUTH_TYPE` supports DB, LDAP, and REMOTE_USER modes
- Cross-domain auth via `myapp_username` cookie and `Authorization` header

### Container Runtime Abstraction
The `CONTAINER_CLI` config (`nerdctl` or `docker`) determines which socket paths to mount. `DOCKER_SOCKET` for Docker, `CONTAINERD_SOCKET` for containerd/nerdctl. Image building pods use this to build and push containers from within the cluster.

## Internal Test Environment (行内测试环境)

### Server access via Tabby MCP

The five hosts below are reachable through the **Tabby MCP** tools (`mcp__Tabby_MCP__*`) — see `tabby-mcp-usage` memory for the `type: "http"` config gotcha. Workflow:

```
list_profiles()                        → get profileId for 服务器1..服务器5
open_profile(profileId="...")          → returns sessionId
exec_command(sessionId="...", command="...")
```

All hosts: user **`hacadm`**, OS **Kylin Linux Advanced Server V10 (Tercel)**, Kubernetes **v1.28.2**.

| Server | IP | Hostname | K8s Role | Notes |
|--------|-----|----------|----------|-------|
| 服务器1 | 192.168.11.11 | k8s-master1 | control-plane | Primary control node. Docker 24.0.9 **and** containerd both present. Source checkouts under `/bdm/share_bdm/`. Runs `buildkit`. |
| 服务器2 | 192.168.11.12 | k8s-master2 | control-plane | **Harbor** (docker-compose, HTTP :80 — no systemd unit, does not auto-start on reboot) and **Gitea** (:3000). Local RPM repo `/bdm/share_bdm/rpm-kilyn/` |
| 服务器3 | 192.168.11.13 | k8s-master3 | control-plane | |
| 服务器4 | 192.168.11.14 | k8s-worker1 | worker | Runs 4 of the notebooks |
| 服务器5 | 192.168.11.15 | k8s-worker2 | worker | **Also runs MySQL 8 natively** (`/usr/local/mysql/bin/mysqld`, systemd unit `mysqld`) — not a K8s workload. Also runs notebooks, so DB and workload share a node. |

Cluster layout: **3 control-plane + 2 worker**. Container runtime in K8s is **containerd** — inspect with `nerdctl -n k8s.io images` / `crictl`. Docker is installed on master1 for image builds. **No node has a GPU** (`nvidia.com/gpu` is unset everywhere).

### Cluster facts

- **Namespaces**: `aihub`, `automl`, `infra`, `istio-system`, `jupyter`, `kubeflow`, `logging`, `metallb-system`, `monitoring`, `pipeline`, `service` (+ `kube-*`). `aihub`/`automl`/`logging`/`pipeline`/`service` are created but hold no pods by default; EFK, ilogtail+Kafka, Alluxio, JuiceFS and Ceph exist as manifests under `install/kubernetes/` but are **not deployed**, and there is no Ingress controller (the objects in `install/kubernetes/ingress.yaml` are inert).
- **Ingress path**: MetalLB VIP `192.168.11.201` → `istio-ingressgateway` → Istio `VirtualService` routing. Istio is used **as a gateway only** — every namespace is labelled `istio-injection: disabled`, so there are no sidecars.
- **Registries**: `192.168.11.12/cube-studio/*` (internal Harbor on master2); `10.240.125.39/cube-studio/*` appears only in `demo-spark/` samples
- **Source checkouts on master1**: `/bdm/share_bdm/cube-studio-master`, `/bdm/share_bdm/cube-studio-bos-new`
- **行内 pip mirror**: `http://10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple` — credentials live in `fix/交接/backend/Dockerfile.backend-py312`, not here
- **Shared storage**: `/data/k8s` on every node is a symlink to `/bdm/share_bdm`, which 服务器1 exports over NFS (`/etc/exports`: `/bdm/share_bdm *(rw,no_root_squash,async)`) and all five nodes mount. Because it is a `hard` NFS mount sitting on top of a local directory, a failed mount degrades silently to an empty local directory rather than raising an error. See the storage section above for why the PV sizes are not meaningful.

### Safety constraints (user-mandated)

- **Never run `rm` on these servers.** No exceptions, including "safe-looking" cleanup.
- Prefer read-only inspection. When a write is genuinely needed, only create files under `/tmp`.
- SSH sessions auto-logout when idle and will appear hung — call `abort_command` or re-`open_profile` rather than retrying the same command.
