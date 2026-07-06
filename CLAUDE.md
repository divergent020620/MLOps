# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cube Studio is an open-source cloud-native machine learning platform (一站式云原生机器学习平台) that provides end-to-end MLOps capabilities including:
- AI pipeline orchestration (workflow DAG)
- Jupyter notebook environments
- Model training and serving
- Dataset management
- AI Hub for model inference services
- ChatGPT integration with knowledge base
- Data middleware integration (SQLLab, metadata management)

The platform is built on Kubernetes and supports both private deployment and edge computing scenarios.

## Architecture

### Backend (Python/Flask)
- **Framework**: Flask with Flask-AppBuilder (FAB) for admin UI and RBAC
- **Database**: MySQL (primary), Redis (cache/celery), PostgreSQL support
- **ORM**: SQLAlchemy 1.4.49
- **Async Tasks**: Celery with Redis broker
- **K8s Integration**: kubernetes Python client for orchestrating jobs/services

### Frontend (React/TypeScript)
Three separate frontend applications:
- **myapp/frontend**: Main platform UI (React 17, Ant Design 4, TypeScript)
- **myapp/vision**: AI Pipeline visual editor (workflow DAG for ML tasks)
- **myapp/visionPlus**: Data ETL Pipeline visual editor

### Key Models (myapp/models/)
- **model_job.py**: Repository, Images, Job_Template, Pipeline, Task - core workflow entities
- **model_team.py**: Project, Project_User - multi-tenancy and RBAC
- **model_notebook.py**: Notebook - Jupyter environments
- **model_serving.py**: InferenceService, Service - model serving
- **model_dataset.py**: Dataset management
- **model_aihub.py**: AI model hub
- **model_chat.py**: ChatGPT integration

### Views (myapp/views/)
- **baseApi.py**: Base REST API classes (93KB - core API logic)
- **home.py**: Main dashboard and workflow APIs (155KB - largest view)
- **view_chat.py**: ChatGPT/LLM integration (80KB)
- Views follow Flask-AppBuilder patterns with ModelView/RestApi classes

## Development Commands

### Local Development (Docker Compose)

**Prerequisites**:
- Docker Desktop
- Python 3.9.16
- Node 16.15.0+ (for frontend development)
- Git configured with `git config --global core.autocrlf false` (Windows)

**Install Python dependencies**:
```bash
pip3 install --upgrade setuptools pip
pip3 install -r install/docker/requirements.txt
```

**Start development environment**:
```bash
cd install/docker
docker-compose up
```

Backend runs on port 80, accessible at http://localhost/frontend/
Default credentials: admin/admin

**Backend debugging**:
For faster iteration, start backend with sleep and exec into container:
```bash
# Modify docker-compose.yml command to: ['bash','-c','sleep 1000000']
docker-compose up -d
docker exec -it docker-myapp-1 bash
# Inside container:
/entrypoint.sh  # First time setup
python myapp/run.py  # Subsequent runs
```

**Database initialization** (first time only):
```bash
# Inside myapp container
export FLASK_APP=myapp:app
python myapp/create_db.py
myapp db upgrade
myapp fab create-admin --username admin --firstname admin --lastname admin --email admin@tencent.com --password admin
myapp init
```

### Frontend Development

**Main frontend (myapp/frontend)**:
```bash
cd myapp/frontend
npm install
npm run start  # Dev server on http://localhost:3000
npm run build  # Production build
```

Configure proxy in `myapp/frontend/src/setupProxy.js` to point to backend.

**Vision pipeline editor (myapp/vision)**:
```bash
cd myapp/vision
npm install
npm run start
npm run build
```

**VisionPlus ETL editor (myapp/visionPlus)**:
```bash
cd myapp/visionPlus
yarn
npm run build
```

### Testing

**Check database tables**:
```bash
python myapp/check_tables.py
```

**Run backend directly** (for debugging):
```bash
export FLASK_APP=myapp:app
python myapp/run.py  # Development mode
```

**Production mode**:
```bash
gunicorn --bind 0.0.0.0:80 --workers 20 --worker-class=gevent --timeout 300 myapp:app
```

### Building Images

**Backend base image**:
```bash
docker build --network=host -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:base-python3.9 -f install/docker/Dockerfile-base .
```

**Backend production image**:
```bash
docker build --network=host -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard:2026.03.01 -f install/docker/Dockerfile .
```

**Frontend image**:
```bash
docker build --network=host -t ccr.ccs.tencentyun.com/cube-studio/kubeflow-dashboard-frontend:2026.03.01 -f install/docker/dockerFrontend/Dockerfile .
```

## Kubernetes Deployment

Deployment manifests are in `install/kubernetes/cube/`:
- **base/**: Core deployment YAMLs (backend, frontend, worker, schedule, watch)
- **overlays/**: Environment-specific configurations

Key deployments:
- **deploy-backend.yaml**: Main Flask application
- **deploy-frontend.yaml**: Nginx serving React apps
- **deploy-worker.yaml**: Celery workers for async tasks
- **deploy-schedule.yaml**: Celery beat for scheduled tasks
- **deploy-watch.yaml**: Kubernetes resource watcher

## Job Templates

Job templates define reusable task components for pipelines. Located in `job-template/job/`.

**Template structure**:
```
job-template/job/$template_name/
  ├── src/           # Source code
  ├── Dockerfile     # Image definition
  ├── build.sh       # Build script
  └── readme.md      # Documentation
```

**Build a template**:
```bash
sh job-template/job/$template_name/build.sh
```

**Template registration**: Done via UI at 训练 -> 任务模板 -> 添加

## Configuration

**Main config**: `myapp/config.py` (overridden by `install/docker/config.py` in dev)

Key environment variables:
- `MYAPP_CONFIG`: Config module path (default: "myapp.config")
- `STAGE`: "dev" | "prod" | "build"
- `MYSQL_SERVICE`: Database connection string
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`: Redis configuration
- `ENVIRONMENT`: DEV | PROD

**Custom project hooks**: `myapp/project.py` - customize message pushing, authentication

## Code Patterns

### Flask-AppBuilder Views
Views inherit from `MyappModelView` or `MyappRestApi` (defined in baseApi.py):
```python
class MyModelView(MyappModelView):
    datamodel = SQLAInterface(MyModel)
    list_columns = ['id', 'name', 'created_on']
    add_columns = ['name', 'describe']
```

### Kubernetes Job Creation
Use `myapp/utils/py/py_k8s.py` for K8s operations. Jobs are created from Job_Template definitions.

### Database Migrations
```bash
myapp db migrate  # Generate migration
myapp db upgrade  # Apply migration
```

### Celery Tasks
Async tasks in `myapp/tasks/`:
- **async_task.py**: Async task definitions
- **schedules.py**: Scheduled tasks (66KB - main scheduler logic)
- **celery_app.py**: Celery configuration

### Debugging
Use `@pysnooper.snoop()` decorator for function tracing (already imported in most files).

## Important Notes

- **Line endings**: Use LF, not CRLF (critical for shell scripts in containers)
- **Frontend hot reload**: Only works for local npm dev servers, not docker-compose
- **Database**: First run requires full initialization via entrypoint.sh
- **Permissions**: Platform uses RBAC with roles (Admin, Gamma, Public)
- **Multi-tenancy**: Projects (Project model) provide isolation between teams
- **Pipeline execution**: Tasks run as Kubernetes Jobs/CronJobs based on templates
- **Image registry**: Default is `ccr.ccs.tencentyun.com/cube-studio/` (Tencent Cloud)

## Common Issues

**Windows development**:
- Ensure `core.autocrlf false` in git config
- Use PowerShell for docker-compose commands
- Change CRLF to LF in VSCode for shell scripts if needed

**Frontend build errors on Windows**:
- In `myapp/visionPlus/.eslintrc`, comment out `"linebreak-style": ["error", "unix"]`
- Uncomment `"linebreak-style": ["error", "windows"]`

**Python package installation failures**:
- Install failed packages individually with matching versions from requirements.txt
- Use Aliyun mirrors if needed: `pip config set global.index-url https://mirrors.aliyun.com/pypi/simple`

## Documentation

- Wiki: https://github.com/tencentmusic/cube-studio/wiki
- Video tutorials: https://cube-studio.oss-cn-hangzhou.aliyuncs.com/video/
