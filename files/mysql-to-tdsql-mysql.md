# Cube Studio 迁移 TDSQL MySQL（10.3.22.1 / MySQL 8.0.24）

## 零、先确认：集中式还是分布式？

**这是唯一决定改造量的关键问题。**

| | 集中式 | 分布式 |
|------|--------|--------|
| 外键 | ✅ 可能支持（原生 MySQL 8.0 内核） | ❌ 不支持 |
| 存储过程/触发器 | ✅ 可能支持 | ❌ 不支持 |
| 窗口函数 | ✅ 可能支持（MySQL 8.0 原生） | ❌ 不支持 |
| 聚合函数 | ✅ 全部 | ⚠️ 仅 5 个（SUM/COUNT/AVG/MIN/MAX） |
| 改造量 | **仅改连接串** | **大改（外键全部要拆）** |

> 确认方法：连上去执行 `SELECT @@version; SHOW VARIABLES LIKE '%shard%';`

---

## 一、如果集中式 → 几乎零改造

只需改 3 个地方：

### 1. 连接串（K8s ConfigMap）

```diff
# 原来
- MYSQL_SERVICE=mysql+pymysql://root:admin@mysql-service.infra:3306/kubeflow?charset=utf8mb4

# 改为
+ MYSQL_SERVICE=mysql+pymysql://root:admin@tdsql-vip:3306/kubeflow?charset=utf8mb4
```

### 2. pymysql 版本确认

当前 `requirements.txt` 有 `pymysql==1.1.0`，MySQL 8.0 完全兼容，无需升级。

### 3. 认证插件

MySQL 8.0 默认用 `caching_sha2_password`，pymysql 1.1.0 已支持。如果连不上，TDSQL 侧执行：

```sql
ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'admin';
FLUSH PRIVILEGES;
```

### 需要验证的点

| 验证项 | 说明 |
|--------|------|
| 建库 DDL | `CREATE DATABASE ... CHARACTER SET utf8 COLLATE utf8_general_ci` — TDSQL 集中式支持 |
| information_schema | `SELECT table_name FROM information_schema.tables WHERE table_schema='kubeflow'` — 完全相同 |
| Alembic 迁移 | `mysql_default_charset` / `mysql_engine` — 原生 MySQL 8.0 支持 |
| 30 个 FK 约束 | 集中式原生 MySQL 支持 FK |
| 连接池 300 | TDSQL 集中式默认连接数够大 |

**结论：集中式几乎零风险，改个 IP 就行。**

---

## 二、如果分布式 → 需要大改

TDSQL 分布式有三大硬伤：

### 硬伤 1：不支持外键（影响最大）

Cube Studio 30 张表中有 **15+ 个 ForeignKey**：

```
project ← images ← job_template ← task
project ← pipeline ← task
project ← pipeline ← run
project ← notebook
project ← docker
project ← service
project ← inferenceservice
project ← training_model
project ← nni
project ← service_pipeline
project ← etl_pipeline ← etl_task
project ← project_user ← ab_user
logs ← ab_user
user_attribute ← ab_user
```

**必须全部拆除**，改为应用层维护引用完整性：

```diff
# 模型层（model_job.py）
- project_id = Column(Integer, ForeignKey('project.id'))
+ project_id = Column(Integer)

# 业务层：手动级联删除
+ Project_User.query.filter_by(project_id=project.id).delete()
+ Task.query.filter(Task.pipeline.has(project_id=project.id)).delete()
  db.session.delete(project)
```

> 迁移文档中"不支持外键"是 TDSQL 分布式版最明确的大特性限制。

### 硬伤 2：仅 5 种聚合函数

搜索 Cube Studio 是否有使用 `GROUP_CONCAT`、`STDDEV`、`BIT_AND` 等：

```bash
grep -rn 'GROUP_CONCAT\|STDDEV\|VARIANCE\|BIT_AND\|BIT_OR\|BIT_XOR\|JSON_ARRAYAGG\|JSON_OBJECTAGG' myapp/ --include='*.py'
```

如果有用到，需要改为应用层聚合。

### 硬伤 3：shardkey 约束

INSERT 必须包含 shardkey 字段，否则报错。需要为每张表选合适的 shardkey（通常是 `id` 或 `project_id`），并确保所有 INSERT 语句都包含该字段。

---

## 三、迁移步骤（两种模式通用）

### 1. 数据迁移

```bash
# 从当前 MySQL 导出
mysqldump -h mysql-service.infra -u root -padmin \
  --single-transaction --routines --triggers \
  --databases kubeflow > kubeflow_dump.sql

# 导入 TDSQL
mysql -h <tdsql-vip> -u root -padmin < kubeflow_dump.sql
```

### 2. 改连接串

```bash
kubectl edit configmap deploy-config -n infra
# 改 MYSQL_SERVICE 的值
```

### 3. 重启 Pod

```bash
kubectl rollout restart deployment -n infra
```

### 4. 验证

```bash
kubectl exec -it -n infra deploy/kubeflow-dashboard -- bash
python myapp/check_tables.py   # 验证 30 张表都存在
```

---

## 四、结论

| 模式 | 改造量 | 风险 | 预估工时 |
|------|--------|------|---------|
| 集中式 | 改 1 个 ConfigMap + 重启 | 极低 | 半天 |
| 分布式 | 拆 15+ FK + 应用层改造 + 测试 | 高 | 2-3 周 |

**你先确认一下是集中式还是分布式，结果完全不同。**
