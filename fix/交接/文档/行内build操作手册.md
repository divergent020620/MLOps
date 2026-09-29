# 行内 Build 操作手册(M1 后端镜像,v1)

> 对象:行内组装同事 | 对照:`fix/组装交接文档.md` M1 章节
> 关键认知:行内 Nexus pip 源(`user-bdas.bdm` + `BDAS.BDM-PY-PUBLIC`)**装上 95% 的依赖(requirements-final 全是 wheel, 源上都有)**;**只有 6 个 wheel 必须离线带入**(源上无 wheel 或 pip 拒绝的):

## 0. 材料清单

### 0.1 必须离线带入(仅 6 个文件)

| # | 文件 | 为什么必须离线 |
|---|---|---|
| 1 | `gssapi-1.9.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` | 源上只有 sdist(需 gcc 编译,行内无编译链) |
| 2 | `decorator-5.3.1-py3-none-any.whl` | gssapi 的传递依赖(顺手带上,防解析) |
| 3 | `docopt-0.6.2-py2.py3-none-any.whl` | 源上 Requires-Python<3.7,pip 在 py3.12 直接拒绝 |
| 4 | `wtforms_json-0.3.5-py3-none-any.whl` | 源上仅有 sdist |
| 5 | `jieba-0.42.1-py3-none-any.whl` | 源上仅有 sdist |
| 6 | `hdfs-2.7.3-py3-none-any.whl` | 源上仅有 sdist |

**打包命令(行外,py312/wheels/)**:
```bash
mkdir -p offline-wheels && cd py312/wheels && cp \
  gssapi-1.9.0-cp312* decorator-5.3.1* \
  docopt-0.6.2* wtforms_json-0.3.5* jieba-0.42.1* hdfs-2.7.3* ../../offline-wheels/ && \
tar czf offline-wheels.tar.gz offline-wheels   # 随交接包传入行内
```

### 0.2 走行内源安装但需特殊方式的(2 个,不用离线带)
| # | 包 | 为什么 |
|---|---|---|
| 1 | `requests-kerberos==0.15.0`(纯 py 源上有) | 依赖声明 `pyspnego[kerberos]`→gssapi,正常解析必挂 → 装时装 `--no-deps` |
| 2 | `pyspnego==0.12.2`(纯 py 源上有) | 同上,与 requests-kerberos 一并 --no-deps 装 |

> 剩余 ~140 个依赖全部:`pip install -r requirements-final.txt`(走行内源, --only-binary=:all:)即可,行外 150 个 wheel 是**兜底与行外验证用**,行内不需要带。

## 1. 行内:打开 M1 容器(基于 M0 app-base-test-v1)

```bash
docker run -d --name app-p312-01 10.240.125.39/cube-studio/kubeflow-dashboard:app-base-test-v1 bash -c "sleep 3600"

# 材料入容器
docker cp requirements-final.txt       app-p312-01:/tmp/requirements-final.txt
docker cp requirements-kerberos.txt    app-p312-01:/tmp/requirements-kerberos.txt
docker cp offline-wheels/              app-p312-01:/tmp/ow

# myapp 源码(仓库路径按实际)
docker cp myapp app-p312-01:/home/myapp/myapp
```

## 2. 行内:验证 pip 源 + 安装(顺序不能乱!)

```bash
PIP_IDX="http://user-bdas.bdm:bdasbdmPwdNexus@10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple"
docker exec -i app-p312-01 bash -c '
set -e
# 0) python3.12 = /opt/python3.12.10-x86_64/bin, 不要用 python3.7!
export PATH=/opt/python3.12.10-x86_64/bin:$PATH
python3.12 -m venv /opt/appenv

# ① SPNEGO 原生后端(离线, 行内 HDFS 用 gssapi 协商)
/opt/appenv/bin/pip install --no-index --find-links /tmp/ow gssapi decorator

# ② Kerberos 组:必须 --no-deps!
/opt/appenv/bin/pip install --no-deps --trusted-host 10.208.29.10 --index-url "'$PIP_IDX'" -r /tmp/requirements-kerberos.txt

# ③ 主依赖(全 wheel;如遇"找不到匹配版本"就是某个包在源上只有 sdist,见附录)
/opt/appenv/bin/pip install --only-binary=:all: --trusted-host 10.208.29.10 --index-url "'$PIP_IDX'" -r /tmp/requirements-final.txt 2>&1 | tail -8

# ④ 4 个 sdist-only 纯 py 包(离线 wheel 终装)
/opt/appenv/bin/pip install --no-index --find-links /tmp/ow wtforms_json jieba hdfs docopt

# ⑤ 冒烟(四个都过才算成功)
/opt/appenv/bin/python -c "import myapp; print(\"myapp import OK\")"
/opt/appenv/bin/python -c "import gssapi; from hdfs.ext.kerberos import KerberosClient; KerberosClient(\"http://x:50070\", timeout=10); print(\"HDFS-Kerberos 链 OK\")"
'
```

> ⚠️ 参照 `fix/jupyternotebook环境自建_utf8.md`:行内装包除 `--trusted-host` 外,**推荐 `CRYPTOGRAPHY_ALLOW_OPENSSL_102=1` 环境变量**(cryptography 老 OpenSSL 兼容,已有实践)。

## 3. 冒烟 + 入库

```bash
# 服务冒烟
docker exec -i app-p312-01 /opt/appenv/bin/python /home/myapp/myapp/run.py & 
sleep 8; curl -s http://localhost:80/health   # 期望 OK
# 建表/迁移链(若已有库, 跳过 create_db, 直接 upgrade)
docker exec -i app-p312-01 bash -c "cd /home/myapp && FLASK_APP=myapp:app /opt/appenv/bin/python myapp/create_db.py && /opt/appenv/bin/myapp db upgrade | tail -5"
# fab create-admin(补全参数, 否则交互会卡)
docker exec -i app-p312-01 bash -c "cd /home/myapp && /opt/appenv/bin/myapp fab create-admin --username admin --password admin --firstname admin --lastname admin --email admin@admin.com || true"

# ④ commit + save
docker stop app-p312-01 && docker commit app-p312-01 10.240.125.39/cube-studio/kubeflow-dashboard:app-p312-v1
docker save -o app-p312-v1.tar 10.240.125.39/cube-studio/kubeflow-dashboard:app-p312-v1 && docker rm app-p312-01
```

## 4. 常见失败对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| `No matching distribution found for gssapi` | 没走①(离线)或 /tmp/ow 未挂载 | 检查 `docker cp offline-wheels/` 后目录名 |
| `ResolutionImpossible: pyspnego[kerberos]...` | ②没加 `--no-deps` | 严格按 ② |
| `No module named ''hdfs''` | ④没装 hdfs(docopt 卡住所致) | 检查④是否报错 |
| `cannot import name 'Markup' from 'flask'` | myapp 源码用错旧版 | COPY 最新 myapp(已做 py3.12 适配) |
| `import myapp` 报 `No module named 'imp'` | 用了行内旧 config.py | 使用最新 myapp;config.py 由 ConfigMap 覆盖 |
| 迁移 `Duplicate column...` | **设计内(try/except 吞掉)**,正常 | 忽略,继续 |
| `SyntaxWarning: invalid escape sequence` | 正常提示(py3.12 对老正则) | 已批改(或忽略) |

## 5. 交付物(对照送评)

- `app-p312-v1.tar`
- 每容器 `rpm -qa > /root/rpm_after.txt`(送评对照)
- 实际 Python 版本清单:`/opt/appenv/bin/pip freeze > backend-pip-freeze.txt`
