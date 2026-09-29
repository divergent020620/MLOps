# MySQL 8.0.24 原生安装 & 集群剥离方案

> 目标机器：192.168.11.15 (k8s-worker2)  
> OS: Kylin Linux Advanced Server V10, x86_64 (glibc 2.28)  
> 目标：原生二进制安装，替换 K8s Pod 方式的 MySQL

---

## 一、下载

从 MySQL 官方归档页面下载 **Compressed TAR Archive, Minimal Install**：

```
https://downloads.mysql.com/archives/community/
→ Product Version: 8.0.24
→ Operating System: Linux - Generic
→ OS Version: Linux - Generic (glibc 2.17) (x86, 64-bit)
→ 选: Compressed TAR Archive, Minimal Install (48.8M)
```

文件名：`mysql-8.0.24-linux-glibc2.17-x86_64-minimal.tar.xz`

> Kylin V10 的 glibc 是 2.28，选 2.17 完全兼容。Minimal 版去掉了 debug 符号，功能和完整版一样。

```bash
# 传到 worker2
scp mysql-8.0.24-linux-glibc2.17-x86_64-minimal.tar.xz root@192.168.11.15:/usr/local/
```

---

## 二、解压 & 安装

```bash
# === 在 k8s-worker2 上执行 ===

cd /usr/local

# 解压（-x 解包 -J xz解压 -f 文件）
tar -xJf mysql-8.0.24-linux-glibc2.17-x86_64-minimal.tar.xz

# 创建软链接
ln -s mysql-8.0.24-linux-glibc2.17-x86_64-minimal mysql

# 删掉多余的 router/test 和压缩包
rm -f mysql-router-*.tar.xz mysql-test-*.tar.xz mysql-8.0.24-linux-glibc2.17-x86_64-minimal.tar.xz

# 验证
/usr/local/mysql/bin/mysqld --version
# → mysqld  Ver 8.0.24 for Linux on x86_64 (MySQL Community Server - GPL)
```

---

## 三、创建用户 & 数据目录

```bash
# 1. 先创建用户（必须先于 chown）
groupadd mysql
useradd -r -g mysql -s /bin/false mysql
id mysql

# 2. 创建数据目录（放在 /bdm 下，100G 空间）
mkdir -p /bdm/mysql/{data,binlog,log,tmp}
chown -R mysql:mysql /bdm/mysql
chmod 750 /bdm/mysql/data
```

---

## 四、配置 my.cnf

```bash
cat > /etc/my.cnf << 'EOF'
[client]
port=3306
socket=/bdm/mysql/mysql.sock
default-character-set=utf8mb4

[mysqld]
port=3306
bind-address=0.0.0.0
basedir=/usr/local/mysql
datadir=/bdm/mysql/data
socket=/bdm/mysql/mysql.sock
pid-file=/bdm/mysql/mysql.pid
log-error=/bdm/mysql/log/mysqld.log
character-set-server=utf8mb4
collation-server=utf8mb4_general_ci
default_authentication_plugin=mysql_native_password
innodb_buffer_pool_size=8G
innodb_log_file_size=512M
max_connections=500
log-bin=/bdm/mysql/binlog/mysql-bin
binlog_format=ROW
expire_logs_days=7
slow_query_log=1
slow_query_log_file=/bdm/mysql/log/slow.log
long_query_time=2
EOF
```

---

## 五、初始化 & 启动

```bash
# 初始化数据目录
/usr/local/mysql/bin/mysqld --initialize --user=mysql \
  --basedir=/usr/local/mysql --datadir=/bdm/mysql/data

# 记下临时密码
grep 'temporary password' /bdm/mysql/log/mysqld.log

# 配置 systemd
cat > /etc/systemd/system/mysqld.service << 'EOF'
[Unit]
Description=MySQL Server
After=network.target

[Service]
Type=forking
User=mysql
Group=mysql
ExecStart=/usr/local/mysql/bin/mysqld --daemonize
ExecStop=/usr/local/mysql/bin/mysqladmin -u root shutdown
Restart=on-failure
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 启动
systemctl daemon-reload
systemctl start mysqld
systemctl enable mysqld
systemctl status mysqld

# 加入 PATH
echo 'export PATH=/usr/local/mysql/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

---

## 六、修改密码 & 创建库

```bash
# 用临时密码登录
mysql -u root -p_pslcS3Kwrnk

# 在 MySQL 里执行：
ALTER USER 'root'@'localhost' IDENTIFIED BY 'admin';
CREATE USER 'root'@'%' IDENTIFIED BY 'admin';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
CREATE DATABASE kubeflow CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
EXIT;

# 验证
mysql -u root -padmin -e "SELECT @@version; SHOW DATABASES;"
```

---

## 七、迁移数据（从 K8s Pod）

```bash
# === 在 k8s-master1 上执行 ===

# 导出
kubectl exec -n infra deploy/mysql -- \
  mysqldump -u root -padmin --single-transaction --databases kubeflow \
  > /tmp/kubeflow_dump.sql

# 传到 worker2
scp /tmp/kubeflow_dump.sql root@192.168.11.15:/tmp/

# === 在 k8s-worker2 上执行 ===

# 导入
mysql -u root -padmin kubeflow < /tmp/kubeflow_dump.sql

# 校验表数量
mysql -u root -padmin -e "SELECT COUNT(*) table_count FROM information_schema.tables WHERE table_schema='kubeflow';"
```

---

## 八、切换 Cube Studio 连接

```bash
# === 在 k8s-master1 上执行 ===

kubectl edit configmap deploy-config -n infra
# 找到 MYSQL_SERVICE，改为：
#   MYSQL_SERVICE: mysql+pymysql://root:admin@192.168.11.15:3306/kubeflow?charset=utf8mb4

# 重启所有后端
kubectl rollout restart deployment -n infra

# 验证连通性
kubectl exec -it -n infra deploy/kubeflow-dashboard -- \
  python -c "from myapp import db; db.engine.execute('SELECT 1'); print('OK')"
```

---

## 九、清理旧 MySQL Pod

```bash
# 确认新 MySQL 稳定运行后
kubectl delete deploy,svc,pvc -n infra mysql
kubectl delete pv infra-mysql-pv
```
