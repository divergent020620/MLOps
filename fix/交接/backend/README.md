# 后端依赖说明(py3.12 迁移最终版)

## 本目录内容

| 文件 | 说明 |
|---|---|
| `requirements-final.txt` | **最终锁定版(py3.12 实测通过, 已就绪, 替换原版使用)** |
| `requirements-kerberos.txt` | HDFS Kerberos 组(requests-kerberos+pyspnego, 单独装配, 见下) |
| `requirements.txt` | 原版(py3.9, 仅留作对照不要用) |
| `Dockerfile-base.kylin` | 旧链基座构建(仅背景) |

## requirements-final.txt 相对原版的变更(交接要求, 勿再改)

### 1. 删除(死依赖, 代码零 import)
```text
elasticsearch==7.12.1   # 平台代码无任何 ES 调用(EFK 基础设施与 myapp 无关)
pyhive / thrift / thrift-sasl / sasl   # sqllab 实际只分发 mysql/postgres
gmssl==3.2.2            # SM2/3/4 零调用(SSO 走 AUTH_REMOTE_USER+JWT)
Flask-OpenID==1.3.0     # FAB 5 无 OpenID
krbcontext              # 死依赖!hdfs.ext.kerberos 不 import 它
                        # (其依赖 gssapi: C 扩展 Linux 无 wheel, 装了必炸)
```

### 2. 升级(评审优先, 全部 py3.12 实测通过)
```text
Flask 2.3.3 -> 3.1.3              FAB 4.3.7 -> 5.2.2         Flask-SQLAlchemy 2.5.1 -> 3.1.1
SQLAlchemy 1.4.49 -> 2.0.52       Flask-Babel -> 4.0.0       Flask-JWT-Extended -> 4.6.0
flask-caching 2.0.2 -> 2.5.1      flask-compress 1.14 -> 1.24 Flask-Login -> 0.6.3
celery 5.2.2 -> 5.4.0 (kombu 5.3.7)  gunicorn -> 23.0.0      Werkzeug 2.3.7 -> 3.1.6
Jinja2 -> 3.1.6 / Markdown -> 3.8.1 / PyMySQL -> 1.1.1 / flask-cors -> 6.0.0
pandas -> 2.2.3 / numpy -> 1.26.4 / pyarrow -> 16.1.0(锁死) / psycopg2-binary -> 2.9.10
cryptography -> 45.0.4 / urllib3 -> 2.6.3 / kubernetes 25.3.0 -> 29.0.0
greenlet -> 3.5.5(gevent 25.5.1 要求 >=3.2.2) / tiktoken 0.9.0(cp312 轮已确认)
supervisor -> 4.3.0(原裸装未锁, 已并入) / MarkupSafe 2.1.5(显式锁)
```
> ⚠️ **版本是"实测通过组合",行内直接按此安装,不要自行升降级**

### 3. 关键安装纪律(防编译/防解析失败)
```bash
# ① Kerberos 组必须 --no-deps 先行(requests-kerberos 的 metadata extra 会拉 gssapi → 解析必挂)
pip install --no-deps -r requirements-kerberos.txt
# ② 主依赖(离线 wheels 或行内 pypi 源, --only-binary=:all:)
pip install -r requirements-final.txt
# ③ 以下 4 个纯 py 包只有 sdist 无 wheel, 必须离线 wheel(find-links):
#    wtforms-json==0.3.5  jieba==0.42.1  hdfs==2.7.3  docopt==0.6.2(放开 Requires-Python<3.7)
#    krbcontext 不需要(删除);这些 wheel 已在 py312/wheels/ 随行外包交付
```

### 4. HDFS/Kerberos 运行真相(migration 2026-09-08 实测定论)
- `myapp/utils/hdfs_client.py` 认证 = **kinit 子进程**(krb5-workstation 已由基座/系统 yum 装)+ `hdfs.ext.kerberos.KerberosClient(url, timeout=...)`
- 运行链(已全链实测): kinit → **gssapi 原生后端**(manylinux2014 wheel 已备)+ requests-kerberos 0.15.0 + pyspnego 0.12.2(纯 py)→ KerberosClient 实例化 OK / SecurityContext OK
- **native 后端 gssapi wheel 已编译交付**(py312/wheels/):
  `gssapi-1.9.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`(auditwheel 修复, 麒麟 glibc 2.28 直接可装)+ `decorator-5.3.1`(其传递依赖)
- **kinit 与 SPNEGO 的关系**: 配套两步非替代——kinit 只"整票"; 把票据封装成 SPNEGO token 必须 gssapi 绑定。行内"先 kinit"模式符合标准链路, 无需改动
- **不要装 krbcontext**(死依赖, hdfs 不 import; 且拉 gssapi 编译风险, 已删除)
- 行内若 HDFS 未来用 RPC 原生协议(libhdfs/pyarrow)则改走 pyarrow 实现, 与本组无冲突(当前代码只用 HTTP/WebHDFS)

### 5. 行内 pypi 源装配(如可达; 规则与组装交接文档 §第三部分一致)
```bash
PIP_IDX="http://user-bdas.bdm:bdasbdmPwdNexus@10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple"
python3.12 -m venv /opt/appenv
/opt/appenv/bin/pip install --no-deps --trusted-host 10.208.29.10 --index-url "$PIP_IDX" -r requirements-kerberos.txt
/opt/appenv/bin/pip install --only-binary=:all: --trusted-host 10.208.29.10 --index-url "$PIP_IDX" -r requirements-final.txt
/opt/appenv/bin/pip install --no-index --find-links ./offline-wheels wtforms_json-0.3.5-py3-none-any.whl jieba-0.42.1-py3-none-any.whl hdfs-2.7.3-py3-none-any.whl docopt-0.6.2-py2.py3-none-any.whl
```
(前 4 个纯 py sdist 包走 find-links wheel;其余全部 --only-binary)
