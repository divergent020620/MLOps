# TDSQL MySQL 集中式安装教程

> 目标机器：192.168.11.15 (k8s-worker2)  
> OS: Kylin Linux Advanced Server V10, x86_64  
> TDSQL: 10.3.22.1 / MySQL 8.0.24  
> 数据目录: `/data/tdsql`

## 前置准备

```bash
# 1. 确认机器规格
ssh root@192.168.11.15
free -h        # 建议 ≥ 8G
df -h          # 建议 /data ≥ 100G
uname -m       # 确认 x86_64
cat /etc/os-release
```

## 安装步骤

### 步骤 1：上传安装包到目标机器

```bash
# 从你的本机上传（根据实际包名调整）
scp <tdsql-rpm包或tar.gz> root@192.168.11.15:/tmp/
```

### 步骤 2：安装（根据包格式二选一）

**如果是 RPM 包：**
```bash
ssh root@192.168.11.15
cd /tmp
rpm -ivh tdsql-mysql-*.rpm
```

**如果是 tar.gz 包：**
```bash
ssh root@192.168.11.15
cd /tmp
tar -xzf tdsql-mysql-*.tar.gz -C /usr/local/
cd /usr/local/tdsql-mysql
./install.sh   # 或查看 README
```

### 步骤 3：初始化数据目录

```bash
mkdir -p /data/tdsql/{data,binlog,log,tmp}
chown -R mysql:mysql /data/tdsql

# 初始化 MySQL
mysqld --initialize --user=mysql \
  --basedir=/usr/local/tdsql-mysql \
  --datadir=/data/tdsql/data

# 记录临时密码
grep 'temporary password' /data/tdsql/log/mysqld.log
```

### 步骤 4：配置 my.cnf

```bash
cat > /etc/my.cnf << 'EOF'
[mysqld]
# 基础
port=3306
bind-address=0.0.0.0
datadir=/data/tdsql/data
socket=/data/tdsql/mysql.sock
pid-file=/data/tdsql/mysql.pid
log-error=/data/tdsql/log/mysqld.log

# 字符集
character-set-server=utf8mb4
collation-server=utf8mb4_general_ci

# InnoDB
innodb_buffer_pool_size=8G
innodb_log_file_size=512M
innodb_flush_log_at_trx_commit=1
innodb_file_per_table=1

# 连接
max_connections=500
max_connect_errors=10000
wait_timeout=600
interactive_timeout=600

# binlog
log-bin=/data/tdsql/binlog/mysql-bin
binlog_format=ROW
expire_logs_days=7

# 慢查询
slow_query_log=1
slow_query_log_file=/data/tdsql/log/slow.log
long_query_time=2

# 兼容 Cube Studio
default_authentication_plugin=mysql_native_password
sql_mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
EOF
```

### 步骤 5：启动

```bash
systemctl start mysqld
systemctl enable mysqld
systemctl status mysqld
```

### 步骤 6：修改密码 & 创建库

```bash
# 用临时密码登录
mysql -u root -p

ALTER USER 'root'@'localhost' IDENTIFIED BY 'admin';
CREATE DATABASE kubeflow CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER 'root'@'%' IDENTIFIED BY 'admin';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
EXIT;

# 验证
mysql -u root -padmin -e "SELECT @@version; SHOW DATABASES;"
```

### 步骤 7：导入数据

```bash
# 从 K8s 旧 MySQL 导出
kubectl exec -n infra deploy/mysql -- mysqldump -u root -padmin \
  --single-transaction --databases kubeflow > /tmp/kubeflow_dump.sql

# 传到 worker2 并导入
scp /tmp/kubeflow_dump.sql root@192.168.11.15:/tmp/
ssh root@192.168.11.15
mysql -u root -padmin < /tmp/kubeflow_dump.sql
```

### 步骤 8：切换 Cube Studio 连接

```bash
# 改 ConfigMap
kubectl edit configmap deploy-config -n infra

# 改这一行：
#   MYSQL_SERVICE: mysql+pymysql://root:admin@192.168.11.15:3306/kubeflow?charset=utf8mb4

# 重启所有组件
kubectl rollout restart deployment -n infra
```

---

## 待确认

**把安装包放到** `/bdm/share_bdm/` **下**，然后告诉我路径，我把上面的步骤改成针对你具体包的脚本。
