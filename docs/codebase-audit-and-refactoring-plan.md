# Cube Studio 代码库调研报告：问题清单与重构方案

> 调研日期：2026-08-14
> 范围：后端 (Python/Flask + Flask-AppBuilder)、前端 (React/TypeScript)、基础设施 (Docker/K8s 部署)
> 方法：代码库全面扫描 + 架构模式分析 + 外部参考架构对比

---

## 目录

1. [核心架构问题](#1-核心架构问题)
2. [代码质量问题](#2-代码质量问题)
3. [可维护性问题](#3-可维护性问题)
4. [可扩展性问题](#4-可扩展性问题)
5. [重构方案](#5-重构方案)
6. [问题优先级矩阵](#6-问题优先级矩阵)

---

## 1. 核心架构问题

### 1.1 前后端不完全分离（混杂渲染模式）

**严重程度：高 | 影响范围：全局**

项目使用了 **Flask-AppBuilder (FAB)** 框架，该框架原生支持服务端渲染（SSR）。虽然前端有 React SPA（`myapp/frontend/`），但后端视图层仍然大量使用 `render_template()` 直接返回 HTML 页面。

**SSR 与 API 混杂的视图文件：**

| 文件 | 行数 | `render_template` 调用 | `jsonify` 调用 | 结论 |
|------|------|------------------------|----------------|------|
| `view_k8s.py` | 581 | **12** | 6 | ❌ 严重混杂 |
| `view_pipeline.py` | 1,339 | 4 | 17 | ❌ 混杂 |
| `view_task.py` | 879 | 3 | 8 | ❌ 混杂 |
| `view_notebook.py` | 899 | 1 | 4 | ❌ 混杂 |
| `view_docker.py` | 404 | 1 | 2 | ⚠️ 轻微混杂 |
| `view_nni.py` | 770 | 1 | 3 | ⚠️ 轻微混杂 |

**服务端渲染的模板页面（`myapp/templates/`）：**

| 模板 | 用途 | 渲染位置 |
|------|------|----------|
| `log.html` | K8s Pod 日志查看 | `view_k8s.py:watch_log()` |
| `terminal.html` | K8s Pod 终端 | `view_k8s.py:watch_exec()` |
| `pods.html` | Pod 列表 | `view_k8s.py:web_search()` |
| `link.html` / `external_link.html` | 外部链接嵌入 | `view_k8s.py:web_debug()` |
| `close.html` | 操作结果关闭页 | `view_task.py`、`view_pipeline.py` |
| `k8s_tail_log.html` | 实时日志 tail | 独立页面 |

**根因分析：** FAB 框架提供两种视图类——`ModelView`（SSR，生成 HTML）和 `ModelRestApi`（REST API，返回 JSON）。项目初期使用 `ModelView` 快速构建了管理后台，后期引入 React 后部分功能迁移到了 API，但 `K8s_View` 等类仍然完全基于 `ModelView` 的 SSR 模式，导致一个项目中同时存在两种渲染范式。

**影响：**
- 后端同时承担 API 和模板渲染双重职责，违反了单一职责原则
- 前端无法完全接管 UI 渲染，用户体验不一致
- 每次新增页面需要在两端协调，降低开发效率

### 1.2 MVC 模式严重违反

**严重程度：高 | 影响范围：模型层 + 视图层**

#### 1.2a HTML 代码嵌入在 Model 层

Model 文件中直接包含 HTML 标签、CSS 样式、SVG 图标，将展示逻辑混入数据层：

**`model_aihub.py:56-73`** — 完整的 HTML 卡片模板在 Model 中：
```python
return Markup(f'''
<div style="border: 3px solid rgba({'29,152,29,.6' if self.status=='online' else '0,0,0,.2'});border-radius: 3px;">
    <img src="{pic_url}" onerror="this.src='/static/assets/images/aihub_loading.gif'"
         style="height:200px;width:100%" alt="{self.describe}"/>
    <div class="p16" alt="{self.describe}">
        <div class="p-r card-popup ellip1">
```

**`model_nni.py:73`** — 操作链接 HTML 在 Model 中：
```python
ops_html = f'<a target=_blank href="/nni_modelview/api/run/{self.id}">{__("运行")}</a> | ...'
return Markup(ops_html)
```

**`model_job.py:691-699`** — SVG 图标字典在 Model 中：
```python
default = '<svg t="1669360410529" class="icon" viewBox="0 0 1024 1024"...>'
status_icon = {
    "Running": '<svg t="1669360051741"...>',
    "Error": '<svg t="1669359973288"...>',
    ...
}
return Markup(f'<div style="display: flex; align-items: center;">{status_icon.get(status,default)}&nbsp;&nbsp;{status}</div>')
```

**涉及的文件：** `model_aihub.py`、`model_nni.py`、`model_job.py`、`model_notebook.py`、`model_etl_pipeline.py`、`model_chat.py`、`model_metadata_metric.py`、`helpers.py`

#### 1.2b SVG 图标硬编码在 Python 代码中

`view_k8s.py:21-31` 和 `model_job.py:691-699` 中硬编码了完整的 SVG 字符串（每个约 500-800 字符），这些应该放在前端图标组件中或 CSS sprite 中。

#### 1.2c Presenter 逻辑在 Model 中

`model_helpers.py:327-352` 中定义了 `_user_link()`、`changed_by_name()` 等方法，返回 HTML 链接，属于 View/Presenter 层的职责。

### 1.3 长参数列表与巨型函数

**严重程度：中 | 影响范围：多个视图文件**

**参数最多的函数：**

| 函数 | 参数数量 | 所在位置 | 问题 |
|------|----------|----------|------|
| `make_pod()` | **29 个参数** | `py_k8s.py:1223` | 缺少 DTO/Builder 模式 |
| `run_pod()` | **9 个参数** | `view_task.py:413` | 缺少请求对象 |
| `chatgpt()` | **7 个参数** | `view_chat.py:1295` | 缺少配置对象 |
| `query_list()` | **6 个参数** | `view_total_resource.py:356` | 缺少分页查询对象 |
| `make_workflow_yaml()` | **6 个参数** | `view_pipeline.py:79` | 缺少上下文对象 |
| `generate_prompt()` | **4 个参数** | `view_chat.py:1176` | 尚可接受 |
| `watch_log()` | **4 个参数** | `view_k8s.py:37` | URL 路径参数映射，尚可接受 |

**注意：** `make_pod()` 的 29 个参数是 K8s `V1PodSpec` API 映射的产物，不是 FAB 框架导致的。但缺少 Builder 模式或 PodSpec 配置对象，使得调用方需要记住参数顺序，易出错。

---

## 2. 代码质量问题

### 2.1 巨型文件（Monolith 反模式）

**严重程度：高 | 影响范围：多个文件**

| 文件 | 行数 | 职责 | 建议拆分 |
|------|------|------|----------|
| `baseApi.py` | **2,324** | REST API 基础类（CRUD、权限、序列化、导出、字段映射、响应合并） | 5-6 个模块 |
| `view_chat.py` | **1,535** | ChatGPT 集成、RAG 知识库、流式响应、对话管理、提示词 | 3-4 个模块 |
| `view_pipeline.py` | **1,339** | Pipeline CRUD、DAG 转换、运行、YAML 生成、状态管理 | 3-4 个模块 |
| `view_inferenceserving.py` | **1,357** | 推理服务管理、Prometheus 配置、服务网格、监控仪表盘 | 2-3 个模块 |
| `view_dimension.py` | **1,066** | 数据维度管理、元数据 | 2 个模块 |
| `schedules.py` | **1,222** | 所有 Celery 定时任务 + 异步任务 | 2-3 个模块 |
| `cli.py` | **930** | 初始化、数据导入、模板注册、胶水代码 | 2-3 个模块 |
| `utils/core.py` | **2,291** | 邮件、日期、文件、缓存、国际化、HTML 清理等大杂烩 | 5-6 个模块 |

**`baseApi.py` 的 `MyappModelRestApi` 类（2,000+ 行）问题尤为突出：**

- 30 个 `merge_*` 方法（15 个重写 FAB 内置 + 14 个自定义）
- 5 个 `_init_*` 方法（titles、label_columns、properties、model_schemas、cols_width）
- 自定义 CSV 导出、文件发送、响应格式化
- 权限检查、字段映射、UI 元数据生成

### 2.2 ETL 视图大面积重复代码

**严重程度：高 | 影响范围：3 个文件，共 2,949 行**

三个几乎相同的 ETL 视图文件，仅类名、默认 host URL、少数字段标签不同：

| 文件 | 行数 | 差异点 |
|------|------|--------|
| `view_etl_pipeline_airflow.py` | 985 | 类名 `AIRFLOW_ETL_PIPELINE`，默认 host `http://airflow.oa.com` |
| `view_etl_pipeline_azkaban.py` | 982 | 类名 `AZKABAN_ETL_PIPELINE`，默认 host `http://azkaban.oa.com` |
| `view_etl_pipeline_dolphinscheduler.py` | 982 | 类名 `DOLPHINSCHEDULER_ETL_PIPELINE`，默认 host 不同 |

**重复代码比例：~95%**。三个文件仅有：
- 类名不同
- 默认 host URL 不同
- 少数字段 label 翻译不同
- 个别 placeholder 文案不同

### 2.3 两个前端 App 高度重复

**严重程度：中 | 影响范围：myapp/vision/ + myapp/visionPlus/**

| 项目 | 总行数 | 用途 |
|------|--------|------|
| `myapp/vision/` | 6,088 TS | AI Pipeline 可视化 DAG 编辑器 |
| `myapp/visionPlus/` | 4,825 TS | 数据 ETL Pipeline 可视化编辑器 |

两个 App 的目录结构**完全相同**（`components/FlowEditor`、`components/ModuleTree`、`models/`、`types/`、`utils/`），组件有大量重叠但各自独立维护，未共享代码。

### 2.4 调试代码遗留在生产代码中

**严重程度：中 | 影响范围：多个文件**

```python
# myapp/__init__.py:20
import pysnooper        # 调试工具作为生产依赖引入
# __init__.py:54
# @pysnooper.snoop()   # 注释掉的调试代码遍布代码库
```

`pysnooper` 被 import 的文件：`__init__.py`、`forms.py`、`cli.py`、`schedules.py` 等。大量 `@pysnooper.snoop()` 被注释掉，既影响代码可读性，也表明代码质量管控不足。

### 2.5 缺少代码质量工具

**严重程度：中 | 影响范围：前端**

- 前端没有 ESLint 配置（`.eslintrc` 不存在）
- 没有 Prettier 配置（`.prettierrc` 不存在）
- 后端函数缺少类型提示
- 没有统一的 API 错误处理模式
- 三个前端 App 各自独立管理依赖，没有统一的代码风格

---

## 3. 可维护性问题

### 3.1 过大的 FAB 基础类

**严重程度：高 | 影响范围：所有视图类**

`MyappModelRestApi`（`baseApi.py:240`）试图成为"万能基础类"，导致所有子类都继承了大量复杂逻辑：

- `merge_cols_width()`、`merge_ops_data()`、`merge_exist_add_args()` 等 30 个 merge 方法
- `columnsfield2info()`、`filed2ui()` 等 UI 元数据生成方法
- 自定义的 CSV 导出、文件发送响应
- 响应合并装饰器模式

**`merge_response_func` 模式（`baseApi.py:200-222`）：**
```python
def merge_response_func(func, key):
    # 装饰器模式：将多个响应合并函数注册到同一个端点
    def wrap(f):
        ...
        return f
    return wrap
```

这是 FAB 框架提供的官方扩展机制，但项目过度使用这一模式，导致单个端点可能关联 5-6 个 merge 函数，调试困难。

### 3.2 配置系统的双重维护

**严重程度：中 | 影响范围：部署**

- 主配置文件：`install/docker/config.py`（~928 行）
- K8s 部署配置：`install/kubernetes/cube/overlays/config/config.py`

两份配置存在差异风险，需要手动同步。

### 3.3 启动入口的复杂性

**严重程度：中 | 影响范围：部署**

`install/docker/entrypoint.sh` 中混杂了：
- 基础设施（符号链接创建）
- 数据库迁移（`create_db.py` + Redis 分布式锁的 `db upgrade`）
- 用户创建（`fab create-admin`）
- 数据初始化（`myapp init`）
- 应用启动（根据 `STAGE` 选择 build/dev/prod 模式）

### 3.4 缺少自动化测试

**严重程度：高 | 影响范围：全局**

- 根目录下没有 `tests/` 目录
- 没有 `pytest` 配置
- 没有 `jest` 测试
- `myapp/frontend/src/App.test.tsx` 只是 CRA 默认模板的占位文件
- 风险：核心功能（Pipeline 运行、DAG 转换、K8s 交互）无任何测试覆盖

---

## 4. 可扩展性问题

### 4.1 CRD 信息的硬编码引用

**严重程度：低 | 影响范围：config.py**

`CRD_INFO`、`CLUSTERS`、`GLOBAL_ENV`、`HDFS_CONFIG` 等都在 `config.py` 中硬编码，但被许多视图文件直接引用（`from myapp import conf`; `conf.get('CLUSTERS')`）。添加新的 CRD 类型需要修改核心配置文件和多个视图文件。

### 4.2 三个前端独立构建的维护成本

**严重程度：中 | 影响范围：构建流程**

| 项目 | 构建工具 | 依赖数量 | 构建脚本 |
|------|----------|----------|----------|
| `frontend/` | Webpack 5 | 113 deps | `npm run build` |
| `vision/` | Vite | 33 deps + 16 devDeps | `npm run build` |
| `visionPlus/` | Vite | 25 deps + 15 devDeps | `npm run build` |

三个 App 各自有独立的 `package.json`、`tsconfig`、构建流程，但共享大量组件逻辑却又没有共享代码库（monorepo 或 shared package）。

### 4.3 缺少国际化一致性

**严重程度：低 | 影响范围：多个文件**

项目中同时存在 `gettext as __` 和 `lazy_gettext as _` 两种别名，使用不一致。部分地方直接使用中文硬编码字符串，没有走国际化流程。

---

## 5. 重构方案

### 第一阶段：基础架构分离（1-2 个月）

**目标：建立清晰的 API 层，消除服务端渲染**

#### 1.1 API 优先重构

**涉及文件：`view_k8s.py`、`view_task.py`、`view_pipeline.py`、`view_notebook.py`**

**步骤：**

1. **`K8s_View` 类（`view_k8s.py`）拆分：**
   - 创建 `K8sApi` 类（纯 REST API，JSON 响应）
   - 保留 `K8s_View` 的 API 端点，移除 `render_template()` 调用
   - 前端创建 React 组件替换 `log.html`、`pods.html`、`terminal.html` 的展示

2. **模板页面迁移：**
   - `log.html` → React 组件 `PodLogViewer`（使用 WebSocket 或轮询 API）
   - `pods.html` → React 组件 `PodList`（使用 REST API）
   - `terminal.html` → React 组件 `PodTerminal`（使用 WebSocket API）
   - `close.html` → 前端 Toast/Notification 组件

3. **删除非必要的 FAB 模板：**
   - 保留 `appbuilder/base.html`（FAB 框架必需）
   - 删除 `log.html`、`pods.html`、`terminal.html`、`close.html`、`link.html`、`external_link.html`

**预计效果：** 消除 12+ 个 `render_template` 调用，所有页面通过 API 驱动

#### 1.2 消除 Model 层中的 HTML

**涉及文件：`model_aihub.py`、`model_nni.py`、`model_job.py`、`model_notebook.py`、`model_etl_pipeline.py`、`model_chat.py`、`helpers.py`**

**步骤：**

1. **替换 `Markup()` 返回：**
   - 将 `model_aihub.py` 中的 HTML 卡片模板改为返回结构化数据字典
   - 前端 React 组件渲染卡片 UI
   - 示例：`model_job.py` 的 `status_icon()` 改为返回状态字符串，由前端决定图标

2. **SVG 图标迁移：**
   - 将 `view_k8s.py:21-31`、`model_job.py:691-699` 中的 SVG 字符串移到前端
   - 创建前端图标组件（如 `StatusIcon`），根据状态渲染不同图标

3. **`helpers.py` 清理：**
   - `_user_link()` → 改为返回用户 ID，由前端渲染链接
   - `changed_by_name()` → 改为返回纯文本时间戳

**预计效果：** 消除 9 个文件中的 HTML/SVG 代码，真正实现 Model 层只关注数据

### 第二阶段：模块拆分与代码复用（2-3 个月）

**目标：解决巨型文件和重复代码**

#### 2.1 拆分巨型文件

**`baseApi.py`（2,324 行）→ 拆分为：**

| 新文件 | 职责 | 行数预估 |
|--------|------|----------|
| `base_api.py` | 核心 CRUD 基类 | ~400 |
| `base_export.py` | CSV 导出、文件下载 | ~200 |
| `base_merge.py` | 响应合并装饰器 | ~300 |
| `base_permissions.py` | 权限检查 | ~200 |
| `base_ui.py` | UI 元数据生成（`filed2ui`、`columnsfield2info`） | ~300 |
| `base_init.py` | 初始化方法（`_init_titles`、`_init_properties` 等） | ~300 |

**`view_chat.py`（1,535 行）→ 拆分为：**

| 新文件 | 职责 |
|--------|------|
| `chat_api.py` | API 端点定义 |
| `chat_service.py` | 业务逻辑（RAG、知识库检索、提示词处理） |
| `chat_stream.py` | 流式响应处理 |
| `chat_models.py` | 数据模型 / DTO |

**`utils/core.py`（2,291 行）→ 拆分为：**

| 新文件 | 职责 |
|--------|------|
| `utils/date_utils.py` | 日期时间工具 |
| `utils/email_utils.py` | 邮件发送 |
| `utils/cache_utils.py` | 缓存管理 |
| `utils/file_utils.py` | 文件操作 |
| `utils/html_utils.py` | HTML 清理（bleach 相关） |

#### 2.2 合并 ETL 视图

**涉及文件：`view_etl_pipeline_airflow.py`、`view_etl_pipeline_azkaban.py`、`view_etl_pipeline_dolphinscheduler.py`**

**方案：策略模式**

```python
# 策略接口
class EtlPipelineStrategy(ABC):
    @abstractmethod
    def get_host(self) -> str: ...
    @abstractmethod
    def run_pipeline(self, pipeline): ...
    @abstractmethod
    def delete_pipeline(self, pipeline): ...
    @abstractmethod
    def get_log(self, pipeline): ...

# 具体策略
class AirflowStrategy(EtlPipelineStrategy): ...
class AzkabanStrategy(EtlPipelineStrategy): ...
class DolphinSchedulerStrategy(EtlPipelineStrategy): ...

# 统一视图
class EtlPipelineView(MyappModelRestApi):
    def __init__(self, strategy: EtlPipelineStrategy):
        self.strategy = strategy
```

**预计效果：** 3 个文件 ~2,949 行 → 1 个文件 ~1,200 行，减少 ~1,700 行重复代码

#### 2.3 合并 Vision 和 VisionPlus 前端

**方案：Monorepo + 共享组件库**

```
myapp/
  shared/                 # 共享组件库
    components/
      FlowEditor/         # 通用 DAG 编辑器
      ModuleTree/         # 模块树
    models/               # 通用状态管理
    types/                # 共享类型定义
  vision/                 # AI Pipeline 编辑器（依赖 shared）
  visionPlus/             # 数据 ETL 编辑器（依赖 shared）
```

**步骤：**
1. 提取公共的 `FlowEditor`、`ModuleTree` 等组件到 `myapp/shared/`
2. 两个 App 通过配置/插件机制差异化（如不同的节点类型、颜色主题）
3. 使用 Turborepo 或 Nx 管理构建

### 第三阶段：架构现代化（3-4 个月）

**目标：真正的分层架构，提升可测试性**

#### 3.1 引入 Service 层

**当前架构：**
```
View (Flask) → Model (SQLAlchemy ORM)
```

**目标架构：**
```
View (Flask) → Service (业务逻辑) → Model (ORM)
```

**实施：**
- 从 `view_chat.py` 开始，将 RAG 检索、提示词生成等逻辑抽取到 `ChatService`
- 从 `view_pipeline.py` 开始，将 DAG 转换、YAML 生成逻辑抽取到 `PipelineService`
- Service 层可独立测试，不依赖 Flask 请求上下文

#### 3.2 添加类型提示和 DTO

**模式：使用参数对象（Parameter Object）消除长参数列表**

```python
# 重构前（29 个参数）
def make_pod(self, namespace, name, labels, command, args, volume_mount,
             working_dir, node_selector, resource_memory, resource_cpu, ...):

# 重构后（使用 DTO + Builder 模式）
@dataclass
class PodConfig:
    namespace: str
    name: str
    labels: dict
    command: list[str]
    args: list[str]
    volumes: list[VolumeMount]
    resources: ResourceRequirements
    node_selector: dict | None = None
    ...

class PodBuilder:
    def __init__(self, config: PodConfig):
        self.config = config
    def build(self) -> V1PodSpec: ...
```

#### 3.3 建立自动化测试体系

**后端（pytest）：**

```python
# 项目结构
tests/
  conftest.py           # Flask app fixture
  test_services/
    test_chat_service.py
    test_pipeline_service.py
  test_views/
    test_chat_api.py
    test_pipeline_api.py
  test_models/
    test_pipeline.py
    test_task.py
```

**前端（jest + @testing-library/react）：**

```json
{
  "jest": {
    "collectCoverageFrom": ["src/**/*.{ts,tsx}"],
    "testPathPattern": "src/**/*.test.{ts,tsx}"
  }
}
```

#### 3.4 清理技术债务

- 删除所有 `import pysnooper` 和注释掉的 `@pysnooper.snoop()`
- 添加 ESLint + Prettier 配置
- 统一 `gettext` / `lazy_gettext` 的别名使用
- 统一错误处理格式（统一的 JSON 错误响应结构）

### 第四阶段：长期演进（6 个月+）

#### 4.1 评估脱离 Flask-AppBuilder

FAB 框架耦合了前端模板和 ORM，限制了前后端分离的深度。

**可行性评估：**
- 保留 FAB 的认证和 RBAC 系统（`SecurityManager`）
- 逐步替换 `ModelRestApi` 为 Flask 原生路由或 FastAPI
- 保持 FAB 的数据库模型不变，仅替换视图层

#### 4.2 配置中心化

将 `config.py` 中的配置迁移到外部配置中心（Consul / K8s ConfigMap），减少硬编码引用。

#### 4.3 前端 Monorepo 搭建

- 使用 Turborepo 或 Nx 管理三个前端 App
- 共享组件、类型、工具函数
- 统一构建配置和代码风格

---

## 6. 问题优先级矩阵

| 优先级 | 问题 | 影响 | 工作量 | 建议阶段 |
|--------|------|------|--------|----------|
| 🔴 P0 | 前后端混杂（SSR + API 混合） | 用户体验、维护成本 | 大 | 第一阶段 |
| 🔴 P0 | MVC 违反（Model 含 HTML） | 架构腐化、安全性 | 中 | 第一阶段 |
| 🔴 P0 | 缺少自动化测试 | 质量风险 | 大 | 第三阶段 |
| 🟠 P1 | 巨型文件/单块类 | 可维护性 | 中 | 第二阶段 |
| 🟠 P1 | ETL 视图重复（~2,000 行重复） | 维护成本、bug 风险 | 小 | 第二阶段 |
| 🟠 P1 | 调试代码遗留（pysnooper） | 代码质量 | 小 | 第三阶段 |
| 🟠 P1 | `make_pod()` 29 参数无 DTO | 可读性、可测试性 | 中 | 第三阶段 |
| 🟡 P2 | 前端 Vision/VisionPlus 重复 | 构建/维护成本 | 大 | 第二阶段 |
| 🟡 P2 | 缺少类型提示 | 开发效率 | 中 | 第三阶段 |
| 🟢 P3 | 缺少 ESLint/Prettier | 代码风格一致性 | 小 | 第三阶段 |
| 🟢 P3 | 配置双重维护 | 配置同步风险 | 小 | 第四阶段 |
| 🟢 P3 | 国际化不一致 | 本地化难度 | 小 | 第三阶段 |

---

## 附录 A：代码库统计总览

| 类别 | 统计项 | 数值 |
|------|--------|------|
| **后端 Python** | 文件数 | 172 |
| | 总行数 | 43,871 |
| | 最大文件 | `baseApi.py` (2,324) |
| | 最大模块 | `utils/core.py` (2,291) |
| **前端 Frontend** | 总行数 (TS/TSX) | 14,925 |
| | 页面数 | 8 个页面 |
| | 依赖数 | 113 |
| **前端 Vision** | 总行数 (TS/TSX) | 6,088 |
| | 依赖数 | 33 + 16 devDeps |
| **前端 VisionPlus** | 总行数 (TS/TSX) | 4,825 |
| | 依赖数 | 25 + 15 devDeps |
| **模板** | Jinja2 模板文件 | 34 个 |
| **模型** | SQLAlchemy 模型文件 | 17 个 |
| **视图** | Flask 视图文件 | 28 个 |
| **测试** | 测试文件 | 0 |

## 附录 B：参考架构

- **Kubeflow Dashboard**：Angular/React SPA + REST API 微服务，严格的前后端分离。每个组件（Pipelines、Notebooks、Katib、KServe）有独立的 backend service 和明确定义的 API 边界。
- **MLflow**：React SPA + REST API，纯 API 驱动。Tracking Server 提供 REST API，Python client 和 React UI 都通过 API 调用。
- **Apache Airflow 2.x**：（**与本项目场景最相似**）Airflow 1.x 也是 Flask + FAB + Jinja2 SSR，2.x 完成了从 Flask SSR 到 React SPA 的完整迁移。迁移路径包括：引入 REST API 层 → 逐步替换前端页面 → 最终完全移除 SSR 模板。迁移过程中面临的核心挑战与本项目一致：保持 RBAC 权限系统、兼容已有插件生态、增量迁移而非一次性重写。
- **ZenML**：FastAPI + React SPA，完整的 OpenAPI/Swagger 文档，强调 Stack 概念的干净抽象。

## 附录 C：Deep Research 验证摘要

在调研过程中，我们通过代码库扫描 + 外部资源搜索 + 对抗性验证（Adversarial Verification）对关键发现进行了交叉验证：

| 发现 | 验证结果 | 说明 |
|------|----------|------|
| FAB ModelView 使用 SSR 渲染 HTML | ✅ **确认** | 通过 FAB 4.3.7 源码确认 `list()`、`show()`、`add()`、`edit()` 均调用 `render_template()` |
| `make_pod()` 参数数量 | ✅ **29 个参数（修正）** | 不是 21 个，也不是 FAB 导致的问题——它是 K8s V1PodSpec API 映射的产物 |
| `MyappModelRestApi` merge 方法数量 | ✅ **30 个（修正）** | 15 个重写 FAB 内置 + 14 个自定义，不是 "~50+" |
| `merge_response_func` 模式 | ✅ **FAB 官方扩展机制** | 这是 FAB 框架设计的标准扩展方式，不是项目独有的 hack |
| 长参数列表与 FAB 的关联 | ✅ **部分相关** | FAB 的 `_get_list_widget()` 确实传递 12 个 keyword arguments，但 `make_pod()` 的 29 参数是 K8s API 问题 |
| FAB 的 `extra_args` 机制 | ✅ **标准模式** | 等同于 Django context processors，不是耦合缺陷 |

---

> **建议的立即行动：**
> 1. 从 `view_k8s.py` 的 SSR 页面开始迁移到前端 React 组件 + JSON API（影响力最大，影响范围最小）
> 2. 同步清理 Model 层中的 HTML 代码（改动较小，能快速提升架构清晰度）
> 3. 建立 `pytest` 基础框架，对新代码要求测试覆盖
> 4. 合并三个 ETL 视图文件（投入最小，收益最明显）