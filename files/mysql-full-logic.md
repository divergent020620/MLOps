# Cube Studio MySQL 逻辑全链路

## 一、启动链路（按时间顺序）

### 阶段 1：容器启动

```
entrypoint.sh
│
├─1. 创建软链接（静态资源、数据集、AIHub 目录）
│
├─2. python myapp/create_db.py        ← 建库
│     └─ 读 MYSQL_SERVICE 环境变量
│     └─ 解出 host/port/user/password/dbname
│     └─ pymysql.connect(host, port, user, password, charset='utf8mb4')
│     └─ CREATE DATABASE IF NOT EXISTS `xxx` DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci
│
├─3. myapp db upgrade                 ← 建表（Alembic 迁移）
│     └─ 读 SQLALCHEMY_DATABASE_URI (= MYSQL_SERVICE)
│     └─ 执行 migrations/versions/*.py（17个历史迁移脚本）
│     └─ 每个脚本含 mysql.INTEGER / mysql_default_charset / mysql_engine
│
├─4. myapp fab create-admin           ← 创建管理员账号
│     └─ 写入 ab_user 表
│
├─5. myapp init                       ← 平台初始化
│     └─ 创建默认角色、权限、菜单视图
│     └─ SQLAlchemy ORM 写入 ab_permission / ab_role / ab_view_menu 等
│
└─6. python myapp/check_tables.py     ← 完整性校验（仅 dev 模式）
      └─ pymysql.connect(host, port, user, password, charset='utf8')
      └─ SELECT table_name FROM information_schema.tables WHERE table_schema='kubeflow'
      └─ 校验 30 张表是否全部存在
```

### 阶段 2：Flask 应用初始化（myapp/__init__.py）

```python
# 第 36 行：加载配置
app.config.from_object('myapp.config')   # → install/docker/config.py

# 第 129 行：初始化 SQLAlchemy
db = SQLA(app)
  └─ SQLA 从 app.config['SQLALCHEMY_DATABASE_URI'] 读取连接串
  └─ 连接串来自 os.getenv('MYSQL_SERVICE')  
  └─ 值: mysql+pymysql://root:admin@mysql:3306/kubeflow?charset=utf8mb4
  └─ 底层引擎: pymysql（MySQL 驱动）
  └─ 连接池: pool_size=300, max_overflow=800, pool_recycle=300

# 第 137 行: 悲观连接处理
pessimistic_connection_handling(db.engine)

# 第 141 行: Alembic 迁移管理
migrate = Migrate(app, db, directory='myapp/migrations')
```

---

## 二、运行时数据访问层

### 2.1 ORM 层（主力，99% 的业务逻辑走这条路）

```
请求 → View 函数
  │
  ├── db.session.query(Model).filter(...).all()    ← 查询
  ├── db.session.add(obj)                          ← 新增
  ├── db.session.delete(obj)                       ← 删除
  ├── db.session.commit()                          ← 提交
  └── db.session.rollback()                        ← 回滚
```

**所有 View 都用的模式**：
- `baseSQLA.py`：封装了 `query()`、`get()`、`post()`、`put()`、`delete()`，底层全是 `self.session.query(self.obj)`
- `baseApi.py`（93KB）：最重的 API 层，包含 ID 过滤、CSV 导出、收藏、关联删除

### 2.2 pymysql 直连（5 处，不走 ORM）

| # | 文件 | 函数 | SQL | 目的 |
|---|------|------|-----|------|
| 1 | `create_db.py` | `init_db()` | `CREATE DATABASE IF NOT EXISTS ... CHARACTER SET utf8 COLLATE utf8_general_ci` | 应用启动前建库 |
| 2 | `check_tables.py` | `check_tables()` | `SELECT table_name FROM information_schema.tables WHERE table_schema='...'` | dev 模式校验表完整性 |
| 3 | `view_dimension.py:367` | 同步数据 | `TRUNCATE TABLE xxx` | 外部数据源全量同步前清表 |
| 4 | `view_dimension.py:494` | `create_external_table()` | `CREATE TABLE ... id BIGINT PRIMARY KEY AUTO_INCREMENT ...` | 为外部数据源动态建表 |
| 5 | `example/pipeline/ml/init.py:20` | 示例 | `CREATE DATABASE / CREATE TABLE` | 示例 Pipeline 的数据初始化 |

### 2.3 SQLAlchemy create_engine（3 处，不走应用连接池）

| # | 文件 | 用途 | 连接方式 |
|---|------|------|---------|
| 1 | `baseApi.py:1707` | CSV 下载（按表名读取） | `create_engine(uri)` → pandas.read_sql_query |
| 2 | `view_dimension.py:345` | 外部数据源读取 | `create_engine(uri)` → pandas.read_sql_query |
| 3 | `view_dimension.py:394` | 外部数据源写入 | `create_engine(uri)` → sessionmaker → dbsession |

---

## 三、数据库配置入口

### 3.1 环境变量链路

```
K8s ConfigMap (deploy-config)
  └─ key: MYSQL_SERVICE
  └─ value: mysql+pymysql://root:admin@mysql-service.infra:3306/kubeflow?charset=utf8mb4
       │
       ├── config.py:396 → SQLALCHEMY_DATABASE_URI = os.getenv('MYSQL_SERVICE','')
       │     └── 给 Flask-AppBuilder / SQLAlchemy ORM 使用
       │
       ├── create_db.py:7 → SQLALCHEMY_DATABASE_URI = os.getenv('MYSQL_SERVICE','')
       │     └── 给 pymysql 直连建库使用
       │
       └── check_tables.py:7 → SQLALCHEMY_DATABASE_URI = os.getenv('MYSQL_SERVICE','')
             └── 给 pymysql 直连校验表使用
```

### 3.2 连接串格式

```
mysql+pymysql://root:admin@mysql-service.infra:3306/kubeflow?charset=utf8mb4
│    │        │    │     │                       │    │       │
│    │        │    │     │                       │    │       └── 字符集（MySQL 特有）
│    │        │    │     │                       │    └── 数据库名
│    │        │    │     │                       └── 端口
│    │        │    │     └── 主机名（K8s Service）
│    │        │    └── 密码
│    │        └── 用户名
│    └── 驱动名
└── 协议
```

---

## 四、30 张业务表的完整 ER 关系

```
project ──1:N──→ images
project ──1:N──→ job_template
project ──1:N──→ pipeline
project ──1:N──→ notebook
project ──1:N──→ docker
project ──1:N──→ service
project ──1:N──→ inferenceservice
project ──1:N──→ training_model
project ──1:N──→ nni
project ──1:N──→ service_pipeline
project ──1:N──→ etl_pipeline
project ──1:N──→ project_user

images ──1:N──→ job_template

job_template ──1:N──→ task

pipeline ──1:N──→ task
pipeline ──1:N──→ run (RunHistory)

etl_pipeline ──1:N──→ etl_task

ab_user ──1:N──→ project_user
ab_user ──1:N──→ logs
ab_user ──1:N──→ user_attribute

独立表（无 FK）:
  repository, chat, chat_log, dataset, metadata_table, 
  metadata_metric, sqllab_query, dimension, aihub, 
  announcement, favorite, workflow
```

---

## 五、MySQL 特有语法汇总

### DDL 层面（建库/建表/改表）

| 语法 | 出现位置 | 作用 |
|------|---------|------|
| `CREATE DATABASE ... CHARACTER SET utf8 COLLATE utf8_general_ci` | create_db.py:19 | 建库 |
| `CREATE TABLE ... id BIGINT PRIMARY KEY AUTO_INCREMENT` | view_dimension.py:494 | 动态建表 |
| `TRUNCATE TABLE xxx` | view_dimension.py:369 | 清表（PG 也支持） |
| `mysql.INTEGER(display_width=11)` | migrations/*.py | Alembic 迁移文件 |
| `mysql_default_charset='utf8mb3'` | migrations/*.py | Alembic 迁移文件 |
| `mysql_engine='InnoDB'` | migrations/*.py | Alembic 迁移文件 |

### Model 类型层面

| SQLAlchemy 类型 | 底层 MySQL 实现 | 表数 |
|----------------|----------------|------|
| `Enum('a','b')` | MySQL ENUM | 5 张表，8 列 |
| `Boolean()` | TINYINT(1) | 6 张表，10 列 |
| `Text(65536)` | MEDIUMTEXT | 几乎所有表 |
| `Text(655360)` | LONGTEXT | 2 张表，3 列 |
| `BigInteger` | BIGINT | 1 张表，2 列 |
| `autoincrement=True` | AUTO_INCREMENT | 1 列（announcement.id） |

### 查询层面

| 语法 | 出现位置 | 作用 |
|------|---------|------|
| `information_schema.tables WHERE table_schema='dbname'` | check_tables.py:19 | 查表列表 |
| `?charset=utf8mb4` | 连接串 | 字符集参数 |
| `func.count("*")` | baseSQLA.py:36 | 聚合函数（PG 兼容） |

### 特殊列

| 列名 | 所在表 | 说明 |
|------|------|------|
| `skip` (quote=True) | task | MySQL 保留字需要反引号 |
| `engine` 默认值 'mysql' | sqllab_query | SQLLab 引擎类型 |
