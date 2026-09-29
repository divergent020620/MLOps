# 给装配同事:行内 M1 后端镜像(py3.12)交接说明

> 你只需要完成:**在行内把"后端镜像 app-p312-v1"装出来**(基于已就绪的 M0 基础基座 app-base-test-v1)
> 全程**只装不改**:命令按文档原样执行,出问题截图发回交接人,不要自行换版本/降级。

## 你手上有什么(本目录)

| 路径 | 用途 |
|---|---|
| `文档/行内build操作手册.md` | ⭐ **主手册**:带你从 0 装到 1(含 pip 源命令、顺序、失败对照表) |
| `文档/组装交接文档.md` | 全局流程(4 个镜像全景/时间表)与边界,可作背景 |
| `backend/requirements-final.txt` | 主依赖锁定清单(py3.12) |
| `backend/requirements-kerberos.txt` | HDFS Kerberos 组(必须 `--no-deps` 装) |
| `materials/offline-wheels.tar.gz` | **6 个必须离线装的 wheel**(解压后 `docker cp` 进容器 `/tmp/ow`) |
| `jupyter/` `materials/fe-caddy-kylin.tgz` | 其他镜像材料(M2/M3),本次用不到 |

## 一句话流程(详细命令见主手册)

1. 起 M1 容器 `app-p312-01`(FROM app-base-test-v1)
2. 拷入:`requirements-final.txt` `requirements-kerberos.txt` `offline-wheels/`(解压后的目录)+ myapp 源码 + **HDFS 认证原料(`ai_general.keytab` → `/home/myapp/`、`krb5.conf` → `/etc/`,真实配置,与旧链一致)**
3. **按顺序执行**(顺序不可乱):
   - ① `pip install --no-index --find-links /tmp/ow gssapi decorator`(离线,SPNEGO 原生后端)
   - ② `pip install --no-deps ... -r requirements-kerberos.txt`(走行内源,--no-deps 是关键)
   - ③ `pip install --only-binary=:all: ... -r requirements-final.txt`(走行内源,~140 个依赖全在源上)
   - ④ `pip install --no-index --find-links /tmp/ow wtforms_json jieba hdfs docopt`(离线)
   - ⑤ 冒烟
4. commmit + save: `app-p312-v1.tar` → 交回

## 4 条红线(踩了就回不来)

1. **python3.12 必须是 `/opt/python3.12.10-x86_64/bin`,不用 python3.7**
2. **② 必须带 `--no-deps`**(少了它 pip 解析必报 `pyspnego[kerberos]` 冲突)
3. **不要装 krbcontext / sasl / gmssl / elasticsearch**(已从需求删除,是死依赖)
4. **任何 `ERROR` / `ResolutionImpossible` / 装不起来 → 截图发回,别自己想办法**
   (备注: `Duplicate column name 'nickname'` 这类是迁移脚本设计内输出,直接忽略)

## 验收标准(两点都过才算完成)

```bash
/opt/appenv/bin/python -c "import myapp; print('OK1')"
/opt/appenv/bin/python -c "import gssapi; from hdfs.ext.kerberos import KerberosClient; KerberosClient('http://x:50070', timeout=10); print('OK2')"
```

## 交付物(交回交接人)

- `app-p312-v1.tar`
- `/opt/appenv/bin/pip freeze > backend-pip-freeze.txt`(送评对照用)
- `rpm -qa > /root/rpm_after.txt`(送评对照用)

---
*交接人侧已完成:依赖版本定版/实测、gssapi manylinux2014 wheel 编译、全链 import 与 CRUD 回归。你只需照本文执行。*
