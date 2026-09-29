# Cube Studio Python 3.12 迁移评估报告

> 版本:**v1.1(2026-09-08 实测修订)** | 日期:2026-09-07
> ◎ **实测驱动修订**(替代 v1.0 的推断部分):依赖链已实测并升级为**评审优先版本**(FAB 5.2.2/Flask 3.1.3/SQLAlchemy 2.0.52/Flask-Babel 4.0.0/kubernetes 29.0.0 等),本地镜像 `cube312:local` 验证通过(import 96 模块、迁移链路、gunicorn+gevent、celery worker),D1 落定为 **Flask 3.1.3 路线**。完整实测记录见 `py312/验证记录与行内组装指引.md`。
> 配套文档:`fix/镜像安全整改方案与建议.md`(总方案,轨道 A/B)、`fix/镜像安全评估分析报告.md`(旧链归因底账)
> 本报告定位:**总方案中"轨道 B:项目 py3.12 适配"的落地评估**——基于全仓库代码扫描、依赖矩阵分析与调用点定位,回答"怎么迁、改哪里、风险多大、干多久"。
> 扫描范围:仓库根 `cube-studio-master` 全量(约 400+ 个 Python 文件、26+ 个 Dockerfile、16 个 job-template、3 个前端应用、K8s 部署资产)。

---

## 0. 结论摘要(先说结论)

1. **代码层对 py3.12 的阻碍极小,真正的风险在依赖层**。全仓库代码扫描仅发现 **2 处阻断级代码**(`config.py` 的 `import imp`),以及约 57 处警告级改动(46 处正则转义告警、FAB 私有导入 7 处、其他 4 处)。项目代码干净(Python 2 遗留、distutils、pkg_resources、asyncio 旧 API 全部 0 命中,无内置二进制)。
2. **依赖层有三个大项**:celery 5.2.2 必须升级(依赖 distutils,py3.12 已移除);Flask-AppBuilder 4.3.7→4.8.1 是最大回归面(连带 Flask-SQLAlchemy/WTForms/Flask 组合决策);发现 5 个**纯死依赖**(elasticsearch、pyhive、thrift、thrift-sasl、sasl、gmssl 共 6 个包代码零调用),删除后反而解开 urllib3 安全升级的死结。
3. **行内"零编译"约束可满足**:主应用 65 个依赖中除 tiktoken 的 cp312 wheel 需实测外,全部有 cp312 manylinux2014 预编译 wheel;sasl 这个最大编译风险包是死依赖,直接删除而非编译。
4. **范围决策需拍板 3 件事**(见 §5):Flask 2.3.3 还是 3.x、jupyter 镜像(TF 2.12 整链)是否同步重锁、job-template 16 个业务模板镜像(81 处 `python:3.9`)是否纳入本次迁移。
5. **工作量估算**:后端主应用 15~20 人天(jupyter 与 job-template 另计,各 1~2 周),与总方案轨道 A(基座先行,3~5 天)并行推进,合流后 1 周内可达送评状态。

---

## 1. 背景与约束

### 1.1 信创要求

- 行内强制要求项目运行于 **Python 3.12**,py3.9 不再允许(决策记录 2026-09-04,见 `fix/镜像安全整改方案与建议.md`)。
- 镜像须通过行内安全评估(奇安信开源卫士),门禁为**超危/高危清零**(豁免项除外)。
- 行内统一麒麟基座:自带源码自编译 **py3.12.10**(`/opt/python3.12.10-x86_64-bin`,pip 25.0.1 + venv,PATH 置顶),**无 conda、无 Miniconda**;遗留 python3.7 仅为 dnf 依赖链(处置见总方案 §4.1b)。
- **零编译原则**:行内基座不装 gcc/-devel 编译链,pip 依赖全部用 cp312 预编译 wheel 行外采购、行内 `pip install --no-index`。
- yum 实测可用(2026-09-07 二次测试),但行内 updates 源滞后于基座,安装时须 `--exclude` 防降级(总方案 §4 ⚠)。
- 前端:node 不进生产镜像,仅行外构建静态产物,行内 nginx 组装(总方案已定)。

### 1.2 评估方法与范围

本次评估通过 5 个并行探查维度完成:①现状盘点(镜像/版本/构建链)②代码层 py3.12 破坏性变更全量扫描(16 类模式)③依赖兼容性矩阵(4 个 requirements 文件逐包)④高风险依赖调用点定位(11 个依赖)⑤前端构建链与 K8s 部署面。全部结论带 `文件:行号` 证据。

---

## 2. 现状盘点

### 2.1 当前 Python 版本全景

| 链路 | Python 版本 | 形态 | 证据 |
|---|---|---|---|
| **后端生产链**(已上线) | **3.9** | 麒麟 rpm 系,实际为 Miniconda 结构(base + envs/python39,真实构建脚本未入库) | K8s 引用 `kubeflow-dashboard:kylin-20260730-v6`;`fix/镜像安全评估分析报告.md:11` |
| 后端仓库链 a(Ubuntu) | 3.9 | apt deadsnakes | `install/docker/Dockerfile-base:6,21,22` |
| 后端仓库链 b(麒麟) | 3.9 | yum python39 + 软链 | `install/docker/Dockerfile-base.kylin:31,61-64` |
| 后端仓库链 c(增量) | 3.9 | 从基座 `...:20260703` 直接 COPY myapp | `build_backend.sh:12`、`update/Dockerfile.backend:8` |
| **notebook 麒麟链** | **3.7.4** | conda env python37 | `domestic-jupyter/Dockerfile.hdfs:32-39`、`Dockerfile.spark:33-40` |
| notebook 官方链 | 3.9 | Miniconda + conda env python39 | `images/jupyter-notebook/build.sh:7,11,15`、`Dockerfile-ubuntu-conda:77` |
| notebook spark-client | 3.7.4 | 老基座 | `images/jupyter-notebook/spark-client/Dockerfile:1` |
| GPU 老镜像(mul-cuda) | 3.6/2.7 | apt | `images/mul-cuda/ubuntu/Dockerfile-base:25-26` |
| theia 镜像 | 3.8.3 | 源码编译 | `images/theia/Dockerfile-cpu-theia:24,31-39` |
| wait_pod 工具镜像 | 3.9 | 官方镜像 | `images/wait_pod/Dockerfile:3` |
| **py3.12 草案** | 3.12 | **Miniconda 方案(与"无 conda"约束冲突)** | `docs/Dockerfile.kylin-py312:37-43` |

### 2.2 镜像资产与构建链

**后端镜像链(需全部重建为 py3.12)**:

```
kubeflow-dashboard:2026.03.01 (ccr, Ubuntu py3.9)
kubeflow-dashboard:base-python3.9-{20260301,20250701,kylin} (三套基座)
kubeflow-dashboard:20260703 (内网增量基座)
kubeflow-dashboard:kylin-20260730-v6 (生产, 5 个 K8s deployment 引用)
kubeflow-dashboard-frontend:2026.03.01 / kylin-base / kylin-20260730 / kylin-20260730-v6 (前端, 无 Python)
```

**K8s 镜像引用点(换 tag 必改清单)**:

| 位置 | 内容 |
|---|---|
| `install/kubernetes/cube/base/deploy-backend.yaml:107` | `kubeflow-dashboard:kylin-20260730-v6` |
| `install/kubernetes/cube/base/deploy-schedule.yaml:89` | 同上(独立 `celery beat`) |
| `install/kubernetes/cube/base/deploy-worker.yaml:108` | 同上(`celery worker --pool=prefork -Ofair -c 20`) |
| `install/kubernetes/cube/base/deploy-watch.yaml:93` | 同上(supervisord) |
| `install/kubernetes/cube/base/deploy-frontend.yaml:125` | `frontend:kylin-20260730-v6` |
| `install/kubernetes/cube/overlays/kustomization.yml:33-40` | images 块 newTag(**注意前端 newTag `kylin-20260730` 与后端 `...-v6` 不一致,改 tag 时易漏**) |
| `build_frontend.sh:12`、`install/docker/update/build.sh:21`、`update/Dockerfile.{frontend:7,backend:6}` | 写死 tag |

### 2.3 依赖清单概览

| 文件 | 行数 | 现状 |
|---|---|---|
| `install/docker/requirements.txt` | 65 | 全部 `==` 锁死;仅 `pyarrow>=14.0.0` 未锁(且无上限);**未锁 setuptools/numpy/greenlet/MarkupSafe(间接依赖漂移风险)** |
| `images/jupyter-notebook/requirements.txt` | 286 | 全部 `==` 锁死,**py3.9 时代版本**(TF 2.12、numpy 1.23.5、jupyterlab 3.6.3、pyzmq 19.0.2、greenlet 2.0.2 等,大量无 cp312 wheel) |
| `myapp/translations/requirements.txt` | 1 | `Babel==2.5.3`(行外翻译工具链,与 FAB 4.8.1 冲突,见 §4.6) |
| `install/docker/Dockerfile` pip 行 | — | `hdfs==2.7.3 requests_kerberos krbcontext pyarrow` 直接 pip 装,**未锁版本**,需并入 requirements 统一锁死 |

**主应用 65 行依赖中,迁移后不需要的(死依赖,见 §4.2)**:elasticsearch、pyhive、thrift、thrift-sasl、sasl、gmssl 共 6 行。

---

## 3. Python 3.12 破坏性变更代码扫描结果

> 扫描 16 类模式(3.10/3.11/3.12 三个版本的破坏性变更全覆盖),逐类给出命中与定性。

### 3.1 阻断项(不修则无法启动/运行)

| # | 位置 | 问题 | 修法 |
|---|---|---|---|
| 1 | `install/docker/config.py:3,351` | `import imp` + `imp.load_source(...)` —— imp 模块 py3.12 已移除 | `importlib.util.spec_from_file_location` + `module_from_spec` + `exec_module` |
| 1b | `install/kubernetes/cube/overlays/config/config.py:3,351` | 同款副本 | 同上 |
| 2(依赖级) | `install/docker/requirements.txt:23` | `celery==5.2.2` 运行时依赖 distutils(setuptools),py3.12 移除 → 升级 celery ≥5.3.1(方案目标 5.4.x) | 升级(§4.1) |

### 3.2 警告/需改项(3.12 可跑但须整改)

| 类别 | 数量 | 典型位置 | 处理 |
|---|---|---|---|
| 无效转义序列(SyntaxWarning) | **46 处** | `myapp/security.py:185,202`、`myapp/utils/core.py:1576`、`myapp/views/view_serving.py:85-94`、`view_nni.py`、`view_docker.py`、`baseApi.py:2076` 等(完整清单见扫描报告) | 正则字面量加 `r` 前缀,机械改动,无行为风险 |
| `imghdr`(3.13 移除,3.12 弃用) | 1 | `myapp/models/model_dataset.py:117-118` | 换 `mimetypes` 或 Pillow 判断 |
| `cgi.escape` 回退分支 | 1 | `myapp/forms.py:59`(try/except 回退,3.12 不会执行) | 删除回退分支 |
| `datetime.utcnow`(3.12 DeprecationWarning) | 1 | `myapp/utils/dates.py:18` | 改 `datetime.now(timezone.utc)` |
| FAB 私有导入 `flask_appbuilder._compat.as_unicode` | 4 | `myapp/security.py:45`、`views/base.py:52`、`views/baseApi.py:30`、`forms.py:294` | 升级 FAB 4.8 前替换为 `str` |
| FAB 非公开模块 `flask_appbuilder.urltools` | 1 | `myapp/views/base.py:27` | 升级 FAB 时改新路径(实测 4.8 实际模块名) |
| FAB `flask_appbuilder.security.decorators` 旧路径 | 2 | `myapp/views/baseApi.py:68`、`view_notebook.py:15` | 改 `flask_appbuilder.decorators` |
| WTForms 老路径 `wtforms.widgets.core` / `wtforms.compat` | 2 | `myapp/forms.py:54,60` | 仅在升 WTForms 3.x 时必改(§4.1 决策) |
| `from flask import Markup / escape`(Flask 3 移除) | **25 个文件** | `views/baseApi.py:10`、`utils/core.py:28`、`models/model_job.py:27` 等 24 个 + `helpers.py:8` | 仅在升 Flask 3.x 时必改(改 `from markupsafe import Markup/escape`,机械);保 Flask 2.3.3 则不动(§5 D1) |
| `u'...'` 前缀字符串 | 11 | `myapp/__init__.py:182`、`forms.py` 多处 | 记录级,3.12 合法,顺手清理 |

### 3.3 确认无风险项(扫描为 0 命中)

- **distutils / pkg_resources**(代码层 0 命中;风险仅在 celery 5.2.2 依赖链,升级即消)
- **Python 2 遗留**(print 语句、`except X, e`、xrange、iteritems、unicode() 等 0 命中)
- **3.12 已移除标准库**(smtpd/asyncore/asynchat/telnetlib/crypt/sre_*/nntplib 等 0 命中)
- **asyncio 旧 API / inspect.getargspec / threading 旧名 / typing Match-Pattern**(0 命中)
- **内置二进制**(全仓库无 `.so`/`.pyd`,myapp 为纯 Python 源码)
- **旧式 collections ABC 导入**(0 命中)

> 结论:代码层整体干净。**必改代码仅 4 行(imp×2 文件)+ 机械清理 46 处转义 + 6 处杂项**;其余全部改动由"依赖升级"驱动(FAB/Flask/WTForms 组合,见 §5 D1)。

---

## 4. 第三方依赖 py3.12 兼容性矩阵

### 4.1 主应用依赖逐包矩阵(`install/docker/requirements.txt`)

> 基线目标来自总方案 §3.1(不推翻);本矩阵补充:死依赖删除、FAB 4.8 连带的隐藏升级、间接依赖锁定。

| 包 | 现版本 | 建议目标 | 决策依据 |
|---|---|---|---|
| flask | 2.3.3 | 2.3.3 或 3.0.3 | **§5 D1 决策项**;升 3.x 须改 25 处 Markup/escape |
| flask-appbuilder | 4.3.7 | **4.8.1** | 4.5 起支持 py3.12;最大回归面(§4.3.3) |
| Flask-SQLAlchemy | 2.5.1 | 2.5.1 或 3.1.1 | FAB 4.8 依赖约束需实测(有说法强制 ≥3.0);若升 3.x,`views/base.py:540` `db.create_scoped_session()` 必改 `db.create_session()` |
| Flask-Migrate | 4.0.5 | 4.0.5(实测 FS3 兼容性,必要时 4.0.7) | `myapp db upgrade` 启动链依赖 |
| Flask-OpenID | 1.3.0 | **删除** | FAB 4.2 起无 OpenID;项目仅 AUTH_DB,零调用 |
| Flask-WTF | 1.2.1 | 保持(与 WTForms 3 兼容性实测) | 启动链 CSRF 依赖 |
| WTForms | 2.3.3 | 2.3.3 或 3.1.2 | FAB 4.8 据称要求 ≥3.0(实测确认);升 3.x 须改 `forms.py:54,60` 老路径 |
| wtforms-json | 0.3.5 | 保持,实测与 WTForms 3 兼容;备选 wtforms-json-fork | `__init__.py:24` 使用 |
| Jinja2 | 3.1.2 | 3.1.6 | 安全目标;连带 MarkupSafe ≥2.1.5(2.1.1 无 cp312 wheel) |
| Werkzeug | 2.3.7 | **3.1.6** | 安全目标;直接使用点仅 5 处且均稳定 API(§4.3.6);scrypt 默认 hash 影响 `security.py:252` 判断(无害) |
| gunicorn | 21.2.0 | 23.0.0 | 参数全兼容;gevent worker 需实测 SSE/长连接(§4.3.10) |
| celery | 5.2.2 | **5.4.0** | distutils 阻断;连带 kombu 5.3.7、billiard 4.2.0、vine 5.1.0、amqp 5.2.0(均纯 py) |
| kombu | 5.3.2 | 5.3.7 | celery 5.4 要求 ≥5.3.4 |
| SQLAlchemy | 1.4.49 | **1.4.54** | 1.4.50 起支持 greenlet 3 / py3.12;保持 1.4 系零代码改动 |
| SQLAlchemy-Utils | 0.41.1 | 保持 | 纯 py |
| greenlet | (间接) | **显式锁 3.1.1** | 2.x 全线无 cp312 wheel;3.1.1 有 manylinux2014 双 tag 轮(实证) |
| pandas | 2.1.2 | 2.2.3 | 2.1.2 无 cp312 wheel;代码无版本敏感 API(DataFrame.append/iteritems 0 命中) |
| numpy | (间接) | **显式锁 1.26.4** | cp312 轮自 1.26 起;1.26.4 与 pandas 2.2/pyarrow 16/17 兼容,避免解析漂到 2.x |
| pyarrow | >=14.0.0 | **16.1.0 或 17.0.0 `==` 锁死** | cp312 wheel 实证;消除"未锁死"缺陷;API 使用(ParquetFile/read_table)长期稳定 |
| psycopg2-binary | 2.9.8 | 2.9.10 | 2.9.9 起才有 cp312 wheel;仅示例脚本直连,主库走 pymysql |
| cryptography | 43.0.0 | 45.x(46.0.5 备选,需实测 manylinux2014 轮是否保留) | cp312 wheel |
| urllib3 | 1.26.20 | **2.5.x / 2.6.3(受 kubernetes 约束,见 §4.3.1)** | 安全目标 2.6.3 与 kubernetes 25.3.0 冲突 |
| elasticsearch | 7.12.1 | **删除** | 死依赖(§4.2),删除后 urllib3 死结解开 |
| pyhive / thrift / thrift-sasl / sasl | 0.7.0 / 0.20.0 / 0.4.3 / 0.3.1 | **删除**(如确需 Hive 能力则走 pyhive[hive-pure-sasl]+pure-sasl+thrift 0.20.0,§5 D3) | 死依赖;sqllab 实际只分发 mysql/postgres(`utils/sqllab/base_impl.py:71-73`) |
| gmssl | 3.2.2 | **删除** | 死依赖(§4.2);SSO 实际走 AUTH_REMOTE_USER+JWT |
| flask-cors | 3.0.10 | 6.0.0 | 全仓库唯一调用点 `__init__.py:165-168`,语义不变 |
| Markdown | 3.4.4 | 3.8.1 | 安全目标 |
| PyMySQL | 1.1.0 | 1.1.1 | 安全目标 |
| gevent | 25.5.1 | 保持 | cp312 wheel 已确认 |
| tiktoken | 0.9.0 | 保持,**cp312 manylinux2014 轮需实测(最高优先实测项 1)** | Rust 编译包,零编译约束下必须买到轮 |
| openai | 1.34.0 | 保持(连带 pydantic-core Rust 轮,cp312 有) | 纯 py |
| kubernetes | 25.3.0 | **28.1.0(PyPI 28 系唯一版本,匹配集群 v1.28.x)**(见 §4.3.1a) | 纯 py;**25.3.0 是 PyPI 客户端包版本(对应 K8s 1.25 API),不是集群版本**——集群基线 v1.28.2;urllib3≥2.6 的 get_headers 移除点 |
| minio | 7.1.17 | 保持(实测 urllib3 2.x 兼容) | 纯 py |
| PySnooper / jieba / xlrd / pydub / openpyxl / wechatpy / humanize / emoji / statsd / ldap3 / hdfs / jwcrypto / redis / contextlib2 / parsedatetime / bleach / beautifulsoup4 / sseclient-py / simplejson / croniter | 各现行版 | 保持或小升(simplejson→3.19.3、clickhouse-driver→0.2.11、cffi→1.17.1、pycryptodome→3.20+、pylint→3.x) | 纯 py 或 cp312 wheel 已确认;croniter 1.4.1 与 celery 5.4 无冲突 |
| supervisor / requests_kerberos / krbcontext | 未锁(Dockerfile pip 行) | **并入 requirements `==` 锁定** | 防漂移;watch 部署 supervisord 依赖 |
| MarkupSafe | (间接) | **显式锁 2.1.5** | 2.1.1 无 cp312 wheel;Jinja2 3.1.6 要求 |
| setuptools / wheel | (未锁) | 行内离线带 setuptools 75.x + wheel 0.43+ | 仅构建期;全 wheel 链时非必需但无害 |

### 4.2 死依赖发现(本次评估最重要发现之一)

全仓库代码调用点定位结论——**6 个包在 requirements 里但代码零 import**:

| 包 | 证据 | 处置 |
|---|---|---|
| elasticsearch 7.12.1 | 全仓库 `import elasticsearch` 0 命中;ES 仅存在于 EFK 基础设施侧(`install/kubernetes/efk/es-all.yaml`、`init-service.json:66-67`),与 myapp 无关 | **删除**,零代码影响;同时解开 urllib3 死结(§4.3.1) |
| pyhive / thrift / thrift-sasl / sasl | `import pyhive/thrift/sasl` 0 命中;sqllab 引擎表有 hive:// URI 样例(`view_sqllab.py:36-46`)但执行分发只走 mysql/postgres(`base_impl.py:71-73`);真实 Kerberos 走 `hdfs.ext.kerberos`(纯 py)+ `kinit` 子进程(`hdfs_client.py:78-106`) | **删除 4 件套**;如需保留 Hive 能力走 pure-sasl 路线(§5 D3) |
| gmssl 3.2.2 | 全仓库 SM2/SM3/SM4/gmssl 调用 0 命中;注释"sm4加解密,单点登录"未落地,SSO 实际为 AUTH_REMOTE_USER(`project.py:44`)+ JWT(`security.py:303-313`) | **删除**;无需 tongsuopy 迁移(总方案 §3.2 的风险包清单可相应缩减) |

> 影响:总方案 §3.2 的"必须实测编译的高风险包"从 3 个(sasl/thrift-sasl/gmssl)缩减为 **0 个**——sasl 是唯一真正的 C 扩展编译风险,而它是死依赖。这是本次评估对总方案的最大优化。

### 4.3 依赖冲突与解套

#### 4.3.1 urllib3 死结(删除 ES 后仍剩一半,须注意)

```
elasticsearch 7.12.1 要求 urllib3<1.26   → 删除 ES 死依赖后此冲突消失 ✓
kubernetes==25.3.0(PyPI 客户端包,对应 K8s 1.25 API;集群基线 v1.28.2,见 §4.3.1a)
              运行时依赖 urllib3.get_headers() → urllib3≥2.6.0 移除该 API,必崩(Airflow PR #59108 实证)
安全目标 urllib3==2.6.3
```

**解套路线**:①kubernetes 客户端先匹配集群基线锁定 **28.1.0**(见 §4.3.1a,纯 py 升级成本低,PyPI 28 系唯一版本),再实测其内部调用在 urllib3 2.6.3 下是否触发 get_headers(修复版主要在 30+/31+ 客户端,若 28.1.0 实测仍崩则走 ②);②或 urllib3 锁 2.5.x + 安全豁免沟通。minio 7.1.17 对 urllib3 2.x 兼容性一并实测。

#### 4.3.1a 版本概念澄清:集群版本 vs Python 客户端版本(重要)

`kubectl version` 显示的是**集群/Kubectl 版本(v1.28.2)**,`requirements.txt:38` 的 `kubernetes==25.3.0` 是**PyPI 上的 Python 客户端库版本**——两者是不同维度,不冲突(客户端向下兼容旧集群):

| 维度 | 你的环境 | 说明 |
|---|---|---|
| 集群 / kubectl | **v1.28.2**(`kubectl version` 实测) | K8s 本身版本,与 Python 无关 |
| Python 客户端库 | **kubernetes==25.3.0**(当前锁) | 25.x 对应 K8s **1.25** API;与 1.28.2 集群差 3 个 minor,超出官方"±1 minor"支持范围 |
| 建议迁移目标 | **kubernetes==28.1.0** | 28.x 对应 K8s **1.28** API(PyPI 28 系仅 28.1.0 一个版本,与集群 1.28.2 匹配),消除兼容性风险 |

**代码使用面确认**(升级零代码改动):`py_k8s.py:58-66` 仅用 `CoreV1Api / AppsV1Api / BatchV1Api / NetworkingV1Api / CustomObjectsApi / RbacAuthorizationV1Api / AutoscalingV1Api/V2Api` + `config.load_kube_config / load_incluster_config`(`:34,19`)+ `kubernetes.stream.stream`(`:12`)+ `watch`(`tools/watch_workflow.py:8,watch_service.py:7`),这些 API 在 25.x/28.x 完全稳定;`view_pipeline.py:36` 的模型导入同理。

#### 4.3.2 celery 5.4.0 连带升级

celery 5.4.0 要求 kombu≥5.3.4 / billiard≥4.2.0 / vine≥5.1.0 / click≥8.1.2(全部纯 py,行外 wheel 采购清单需包含)。celery 任务面(19 个任务、prefork+beat、无 chord/group/chain)与 5.4 兼容,风险低;注意两点:`core.py:991-998` 的 `set_default()` 已弃用(5.4 仍可用,6.0 移除,顺手改);py3.12 需确认镜像内有 tzdata(Asia/Shanghai 调度)。

#### 4.3.3 FAB 4.8.1 升级面(最大回归风险)

| 变更面 | 影响 | 处置 |
|---|---|---|
| 私有导入 `_compat` / `urltools` / `security.decorators` | 4+1+2=7 处 ImportError 即启动失败 | 升级前机械替换(§3.2 已列) |
| `flask_appbuilder.const` 的 `API_*_RES_KEY/RIS_KEY` 常量批(~30 个,`baseApi.py:31-63`) | 4.6+ 部分常量重命名 | 待实测,最坏加 `.get(key, fallback)` |
| 自定义 `ModelRestApi`(`baseApi.py` ~500 行,重写 `_init_properties/_init_titles/_init_model_schemas`) | 4.8 marshmallow/校验链路实现变化 | **最高回归面**,需逐接口验证 |
| 自定义 `SecurityManager`(`security.py` 754 行,重写 `register_views` + AUTH_OID 分支) | 4.8 SM 内部结构变化 | AUTH_OID 分支(`security.py:40,343-348`)直接删(实际只用 AUTH_DB) |
| 强制 Flask-SQLAlchemy / WTForms 版本(需实测确认) | 若属实:FS 2.5.1→3.1(1 处必改)+ WTForms 2.3.3→3.x(2 处必改 + wtforms-json 实测) | §4.1 已列 |

#### 4.3.4 greenlet / MarkupSafe / numpy(隐藏的间接依赖)

- greenlet 2.x 全线无 cp312 wheel,**必须 ≥3.0.0**;SQLAlchemy 1.4.54 与 greenlet 3.x 兼容(1.4.50+ 官方支持);推荐 3.1.1(manylinux2014 双 tag 轮实证)。
- MarkupSafe 2.1.1 无 cp312 wheel → 2.1.5。
- numpy 未锁 → 显式锁 1.26.4(避免解析漂到 2.x 引发 pandas/pyarrow 连锁)。

### 4.4 零编译 wheel 采购清单(行内约束下的风险点)

| 包 | 结论 |
|---|---|
| sasl 0.3.1 | ❌ 仅 sdist 需编译 → **删除(死依赖)**,问题消失 |
| tiktoken 0.9.0 | ⚠ cp312 manylinux2014 x86_64 轮**需实测**(最高优先实测项);无轮则必须行外 cargo 编译带入 |
| cryptography 45.x | ✅ cp312 轮;46.x 是否保留 manylinux2014(glibc 2.17)轮**需实测** |
| thrift 0.20.0 | 纯 py;wheel 存在性实测(如保留) |
| pandas 2.2.3 / pyarrow 16.1.0 / psycopg2-binary 2.9.10 / gevent 25.5.1 / greenlet 3.1.1 / grpcio 1.59+ / numpy 1.26.4 / clickhouse-driver 0.2.11 / pydantic-core | ✅ cp312 manylinux2014 轮全部实证可用 |
| bcrypt / PyNaCl 类 | ✅ abi3 轮(cp36-abi3)直接兼容 cp312 |

> 行外采购命令模板(总方案 §4-2):`pip download -r requirements.txt --python-version 3.12 --platform manylinux2014_x86_64 --only-binary=:all:`,配合 tiktoken 实测。

### 4.5 jupyter/notebook 镜像独立矩阵(§5 D4 决策项)

`images/jupyter-notebook/requirements.txt` 286 行整体锚定 py3.9,**不是逐行升级能解决的**:

- **TF 整链**:tensorflow 2.12.0(仅支持到 py3.11)→ 2.16.1+ 带动 keras 3.x、tensorboard 2.16+、protobuf 4.25、grpcio≥1.59、numpy 1.26/2.x、scipy 1.11.3+ 联动脉,是大工程。
- **其他必须升级的大头**:numba 0.57→0.59+(llvmlite 0.42+)、matplotlib 3.7→3.8+、opencv-python 4.7→4.8.1+、pyzmq 19.0.2→25.1+、gevent 22.10.2→23.9.1+、greenlet 2.0.2→3.x、SQLAlchemy 2.0.12→2.0.23+、tornado 6.1→6.3.3+、PyYAML 6.0→6.0.2、h5py 3.8→3.10+、pydantic 1.10.7、gradio 3.11、jupyterlab 3.6.3/jupyter_server 1.23.6(3.12 下需实测或升 4.x/2.x)。
- **与行内约束的冲突面**:notebook 用户 pip 装机行为(总方案已确认 jupyter 用户不能自行 pip install)、docs/Dockerfile.kylin-py312 草案走 Miniconda(与"无 conda"约束冲突,仅借用其"kylin+py312"底子,不采用其 118 个未锁版本包)。
- 决策选项见 §5 D4。

### 4.6 翻译工具链(行外构建期,不进镜像)

`myapp/translations/requirements.txt` 的 `Babel==2.5.3` 与 FAB 4.8.1 强制(Flask-Babel 4.0.0 → Babel≥2.10)冲突,更新为 Babel 2.16.0 即可;另注意 `myapp/cli.py:5-6` import flask_babel,主应用需显式 pin Flask-Babel 4.0.0(当前 requirements 中该行被注释)。

---

## 5. 关键架构决策项(需拍板)

| # | 决策项 | 选项 | 推荐与理由 |
|---|---|---|---|
| **D1** | **Flask 版本组合** | A:Flask 2.3.3 + Werkzeug 3.1.6 + FAB 4.8.1(代码改动最小,但 Flask 2.3.3 与 Werkzeug 3.x 组合非官方验证,须首日实测);B:Flask 3.0.x + Werkzeug 3.1.6 + FAB 4.8.1(官方配套组合,代价为 25 处 flask.Markup/escape 机械改写 + 核查 json_encoder 定制) | **B(Flask 3.0.3)**,与安全目标(Werkzeug 3.1.6)一致、官方配套;25 处改写机械无风险。首日实测裁决:若 A 实测通过也可用 |
| **D2** | **elasticsearch 处置** | 删依赖(推荐)/升 7.17.x/升 8.x | **删**:代码零调用,EFK 侧 ES 是独立基础设施与 myapp 无关;删后 urllib3 死结解开 |
| **D3** | **Hive/SASL 能力处置** | 删 4 件套(推荐)/保留走 pyhive[hive-pure-sasl]+pure-sasl 0.6.2+thrift 0.20.0 | **删**:sqllab 执行分发不支持 hive;若业务确认有 Hive 数据源需求,走 pure-sasl 路线(PLAIN 可用,GSSAPI 不可用) |
| **D4** | **jupyter/notebook 镜像策略** | ①本次同步重锁 286 行(TF 2.16 整链,1~2 周);②先重锁轻量子集、TF 链延后/砍掉;③notebook 镜像维持 py3.9/3.10 单独走豁免,与行内确认 | **与行内确认范围后再定**;从送评口径看 notebook 镜像也是自制镜像,建议 ②(轻量部分先行,TF 链单独立项) |
| **D5** | **job-template 业务模板镜像(16 个,81 处 `python:3.9` 注册)** | ①本次全量重建为 py3.12;②仅改注册默认值(`init-job-template.json` 81 处 + `init-image.json:8` + `config.py:738,740` USER_IMAGE),模板镜像分批跟进 | **②先行**(改注册指向 py3.12 变体/用户自填),16 个模板镜像(Dataset/DataX/Demo/PyTorch/TF/Volcano/XGB/Ray/YOLOv8 等)逐个重建测试是 1~2 周的独立工作,建议单独排期 |
| **D6** | **前端构建与镜像** | 按总方案已定:行外构建三应用 → 行内基座+nginx 组装;行外 node 版本建议 16.13(frontend README 标注)或实测 18/20(vision/visionPlus 的 react-app-rewired 2.1.9+react-scripts 5.0.0 较老) | 无新增决策,执行要点见 §6.3 |
| **D7** | **urllib3 / kubernetes 客户端版本** | ①客户端锁 **28.1.0**(匹配集群 v1.28.x)+ urllib3 2.6.3(安全目标达成,需实测 get_headers);②kubernetes 升 30+/31+ + urllib3 2.6.3;③urllib3 锁 2.5.x + 豁免 | **①优先实测**;客户端 28.1.0 与集群零版本差,纯 py 升级成本低(代码使用面确认零改动,见 §4.3.1a);实测 get_headers 若崩则依次走 ②③ |
| **D8** | **gmssl 国密能力** | 删除(推荐)/保留换 tongsuopy | **删**:零调用点;若未来接国密 SSO,再评估 tongsuopy |

---

## 6. 分阶段迁移路线(与总方案轨道 B 对齐、细化)

### 阶段 0:决策 + 风险实测(第 1 天,行外)

1. 拍板 §5 D1~D8(本报告 §5 给出推荐,用户确认)。
2. **最高优先实测项**(总方案 §3.2 已定"第一天先做",结合本报告更新):
   - tiktoken 0.9.0 的 cp312 manylinux2014 x86_64 wheel 能否 `pip download --only-binary=:all:` 购得;
   - cryptography 45.x(46.0.5 备选)的 cp312 manylinux2014 轮存在性;
   - Flask 2.3.3 + Werkzeug 3.1.6 + FAB 4.8.1 组合 import 冒烟(裁决 D1);
   - FAB 4.8.1 对 flask-sqlalchemy / wtforms 的真实版本约束(裁决 FS3/WTForms3 是否被迫);
   - kubernetes 升级版 + urllib3 2.6.3 兼容性(裁决 D7);
   - 行外验证环境:麒麟 v10 sp3 + py3.12 容器(repo 已有 `docs/Dockerfile.kylin-py312` 草案可借用底子,不采用其未锁版本包)。

### 阶段 1:requirements 升级 + wheel 采购(2~3 天,行外)

1. 按 §4.1 矩阵改写 `install/docker/requirements.txt`:
   - 删除 6 个死依赖(elasticsearch/pyhive/thrift/thrift-sasl/sasl/gmssl);
   - 升级 15 个基线包 + 连带包(kombu/billiard/vine/amqp);
   - 新增显式锁定:greenlet==3.1.1、numpy==1.26.4、MarkupSafe==2.1.5、Flask-Babel==4.0.0(取消注释)、supervisor/requests_kerberos/krbcontext 并入并锁死、pyarrow==16.1.0(或 17.0.0);
   - 删除 Flask-OpenID==1.3.0。
2. `pip download --python-version 3.12 --platform manylinux2014_x86_64 --only-binary=:all:` 采购全量 wheel,验证 0 编译。
3. 同步更新 `myapp/translations/requirements.txt`(Babel 2.16.0)。
4. jupyter 镜像 requirements 按 D4 决策执行(或独立立项)。

### 阶段 2:代码适配(3~5 天,行外)

| 工作量 | 改动 | 位置 |
|---|---|---|
| 0.5 天 | imp → importlib(2 文件 4 行) | `install/docker/config.py:3,351` + `install/kubernetes/cube/overlays/config/config.py:3,351` |
| 0.5~1 天 | FAB 4.8 导入适配 7 处(_compat→str ×4、urltools、security.decorators ×2)+ AUTH_OID 分支删除 | `security.py:40,45,343-348`、`views/base.py:27,52`、`views/baseApi.py:30,68`、`forms.py:294`、`view_notebook.py:15` |
| 1~2 天 | (若 D1 选 B)Flask 3 适配:25 处 `flask.Markup/escape` → markupsafe + json_encoder 核查 | §3.2 清单 |
| 0.5 天 | (若被迫 FS3)`base.py:540` create_scoped_session → create_session | — |
| 0.5 天 | (若被迫 WTForms3)`forms.py:54,60` 老路径 + wtforms-json 实测/备选 | — |
| 0.5 天 | 杂项:dates.py utcnow、model_dataset.py imghdr、forms.py cgi 回退删除、core.py set_default() 弃用清理 | §3.2 |
| 0.5 天 | 46 处正则转义加 r 前缀(机械) | §3.2 清单 |
| 0.5 天 | entrypoint.sh 删除 STAGE=build 三段 + 后端基座不再装 nodejs/npm/yarn;保留 `update/Dockerfile.backend:22-24` 的 migrations rm 逻辑 | `install/docker/entrypoint.sh:55-59`、`Dockerfile-base:26`、`Dockerfile-base.kylin:52-53` |

### 阶段 3:行外验证环境跑通(3~5 天,行外)

1. 全量 import 冒烟(全部 views/models/tasks 模块);
2. 启动链整条:`create_db.py` → Redis 锁 `myapp db upgrade` → `myapp fab create-admin` → `myapp init` → gunicorn 启动;
3. FAB 全量 CRUD 回归(重点 `baseApi.py` 自定义 ModelRestApi ~500 行、`security.py` 自定义 SecurityManager 754 行)——**最大回归面**;
4. celery 冒烟:beat 定时调度 + 19 个任务抽样执行(工作流提交/notebook/训练任务);
5. gunicorn 23 + gevent worker 实测:并发上传、长连接、SSE(openai 流式 `view_chat.py`);
6. HDFS Kerberos 链路冒烟(kinit 子进程 + `hdfs.ext.kerberos` + requests_kerberos 纯 py 链);
7. pandas/pyarrow 数据链路冒烟(sqllab 导出、HDFS parquet 读取)。

### 阶段 4:行内组装与合流(2~3 天,与总方案轨道 A 并行后合流)

按总方案 §5:FROM 行内 py12 基座(应用基座 v1)→ `python3.12 -m venv` → `pip install --no-index --find-links ./wheels` → COPY myapp → 送评(超危/高危清零)→ 灰度。

K8s 面改动清单:5 个 deploy yaml 镜像行 + overlays/kustomization.yml images 块(注意前端 newTag 不一致陷阱)+ `config.py` 两份 + `init-job-template.json`/`init-image.json` 注册默认值(按 D5)。

### 阶段 5:灰度切换(1~2 周,行内)

`kubectl set image` 灰度 → 观察 rollout → 全量;与基座团队落地月度补丁 SLA(总方案 §6)。

### 6.3 前端镜像执行要点(与后端并行)

1. 行外构建三应用:**myapp/frontend**(npm run build,webpack5 自写脚本)、**myapp/vision**(react-app-rewired build)、**myapp/visionPlus**(yarn 或统一 npm);node 版本实测(16.13 起步);
2. 产物路径锁死不可改名:`.env.production.frontend`(PUBLIC_URL=/frontend/、BUILD_PATH=../static/appbuilder/frontend)、vision 输出 `vison`(**拼写无 i**)、visionPlus 输出 `visonPlus`——后端 4 处视图硬编码引用(`view_pipeline.py:1174,1193`、`view_etl_pipeline.py:460` 等);
3. 前端镜像 = 行内基座 + nginx rpm + COPY 静态产物(总方案 §5);
4. **修复已知缺陷**:kylin 前端 Dockerfile(`dockerFrontend/Dockerfile.kylin:15`)只 COPY appbuilder/frontend,漏了 `/data/web/static`(FAB 静态 + vison/visonPlus),需补 COPY;
5. nginx 路由(`/frontend/`、`/static/appbuilder/`、`/`→`kubeflow-dashboard.infra` 反代)依赖固定路径,镜像替换无需改路由;
6. 前端镜像单独送评(此前从未评过,nginx 版本为主要风险点,总方案已定)。

---

## 7. 风险清单 Top 10(升级风险排序)

| # | 风险项 | 说明 | 工作量 |
|---|---|---|---|
| 1 | **FAB 4.8 + Flask-SQLAlchemy 3.x 强制迁移** | `db.create_scoped_session()` 已删必改;db.session 语义回归;全量 CRUD 回归 | 3~5 人天 + 2 天回归 |
| 2 | **自定义 ModelRestApi(baseApi.py ~500 行)** | 重写 _init_properties/_init_titles/model2schemaconverter + 30 个 const API_* 常量;4.8 marshmallow 链路变化 | 3~5 人天(逐接口验证) |
| 3 | **FAB 内部导入路径变更** | _compat(4)/urltools(1)/security.decorators(2),任一 ImportError 即启动失败 | 0.5~1 人天 |
| 4 | **Flask 3 的 Markup/escape 移除(25 文件)** | 若选 D1-B,机械改写;若 D1-A 可规避 | 1~2 人天(D1-B) |
| 5 | **SecurityManager 手写扩展(security.py 754 行)** | register_views/header_loader 定制面大,4.8 SM 内部重构 | 1~2 人天 |
| 6 | **tiktoken cp312 wheel 采购** | Rust 包,零编译约束下若购不到轮则需行外 cargo 编译带入 | 0.5 人天实测 |
| 7 | **WTForms 3 + wtforms-json 0.3.5** | FAB 4.8 约束迫使升级;wtforms-json 兼容存疑,备选 fork | 1 人天 |
| 8 | **celery 5.4 升级** | beat/annotations/apply_async 兼容;set_default() 弃用;需 tzdata;调度回归 | 1 人天 |
| 9 | **gunicorn 23 + gevent worker** | 参数兼容;重点实测 SSE(openai 流式)与长连接 | 1 人天 |
| 10 | **Werkzeug 3 行为变化** | scrypt 默认 hash(security.py:252 判断失真,无害);ProxyFix 默认信任 1 跳代理 | 0.5 人天 |

低风险确认项:elasticsearch(死依赖删除)、pandas/numpy/pyarrow(无敏感 API)、psycopg2(仅版本号)、flask-cors(单一调用点)、SQLAlchemy 1.4(全部合规用法)、HDFS Kerberos(纯 py 链 + kinit 子进程)。

---

## 8. 工作量估算

| 工作包 | 工期(人天) | 前置 |
|---|---|---|
| 阶段 0:决策 + 风险实测 | 1~2 | 无 |
| 阶段 1:requirements 升级 + wheel 采购 | 2~3 | 阶段 0 |
| 阶段 2:代码适配 | 3~5 | 阶段 0/1 |
| 阶段 3:验证环境跑通(含 FAB CRUD 回归 2 天) | 3~5 | 阶段 1/2 |
| 阶段 4:行内组装合流 | 2~3 | 轨道 A 基座定版 |
| 阶段 5:灰度切换 | 1~2 周(挂机观察为主) | 阶段 4 |
| **后端主应用小计** | **15~20 人天 + 灰度** | |
| jupyter/notebook 镜像重锁(如做,D4) | 10~15(独立立项) | 阶段 0 |
| job-template 16 个模板镜像 py3.12 化(如做,D5) | 8~15(独立立项) | 阶段 0 |
| 前端镜像(行外构建 + 行内组装 + 送评) | 2~3 | 与阶段 4 并行 |

与总方案排期对齐:轨道 A(基座先行,3~5 天)与轨道 B(本报告阶段 0~3)并行;合流后 1 周内可达送评状态,整体满足"先搓基座、再跑应用、两条轨道并行"的既定节奏。

---

## 9. 验收标准

1. **安全门禁**:py3.12 新镜像送评超危/高危清零(豁免项除外);旧链 py3.9 的 8 超危/45 高危随迁移自然消失(总方案 §决策记录)。
2. **启动链**:`create_db.py` → Redis 锁 `db upgrade` → `fab create-admin` → `myapp init` → gunicorn 全链通过;`pip check` 无依赖冲突。
3. **功能回归**:FAB 全量 CRUD 通过;celery beat 调度 + 19 个任务抽样冒烟(工作流提交/notebook/训练任务);SSE 流式(chat)与文件上传/下载通过。
4. **零编译**:行内 `pip install --no-index --find-links ./wheels` 全程无编译器调用。
5. **前端**:三应用产物路径不变(`/frontend/`、`/static/appbuilder/vison*` 可达);`/data/web/static` 补拷缺陷修复。
6. **探针**:schedule readiness(`python3 tools/check_celery.py`)、worker liveness(`celery inspect ping`)、后端 `/health` 在 py3.12 PATH 下全部通过。
7. **灰度**:`kubectl set image` 灰度 → rollout 成功 → 全量,无 P0 事故。

---

## 10. 附录 A:需要改动的资产文件清单

**requirements(3 个)**:
- `install/docker/requirements.txt`(删 6 行死依赖、升级 15 包、新增 7 个显式锁定)
- `myapp/translations/requirements.txt`(Babel 2.16.0)
- `images/jupyter-notebook/requirements.txt`(按 D4 决策)

**代码(约 15 个文件)**:
- `install/docker/config.py:3,351` + `install/kubernetes/cube/overlays/config/config.py:3,351`(imp 阻断)
- `myapp/security.py`、`myapp/views/base.py`、`myapp/views/baseApi.py`、`myapp/forms.py`、`myapp/views/view_notebook.py`(FAB 4.8 适配)
- `myapp/utils/dates.py:18`、`myapp/models/model_dataset.py:117`、`myapp/utils/core.py:991-998`
- (若 Flask 3)25 个文件的 Markup/escape 导入
- 46 处正则转义的 30+ 个文件

**Dockerfile / 脚本(约 10 个)**:
- `install/docker/Dockerfile-base`、`Dockerfile-base.kylin`、`Dockerfile`、`Dockerfile.kylin`、`entrypoint.sh`、`dockerFrontend/Dockerfile.kylin`(补 /data/web/static)
- `build_backend.sh:12`、`build_frontend.sh:12`、`install/docker/update/build.sh`、`update/Dockerfile.{backend,frontend}`
- `install/kubernetes/cube/overlays/config/entrypoint.sh`

**K8s / 注册(约 10 个)**:
- `install/kubernetes/cube/base/deploy-{backend,frontend,schedule,watch,worker}.yaml`
- `install/kubernetes/cube/overlays/kustomization.yml:33-40`
- `myapp/init/init-job-template.json`(81 处)、`myapp/init/init-image.json:8`
- `install/docker/config.py:738` / `overlays/config/config.py:740`(USER_IMAGE)

---

## 11. 附录 B:升级版本对照总表(py3.12 新镜像)

| 组件 | 现版本 | 目标版本 | 备注 |
|---|---|---|---|
| Python | 3.9(conda) | **3.12.10(行内基座,venv)** | 无 conda |
| flask | 2.3.3 | 3.0.3(D1-B)或 2.3.3(D1-A) | §5 D1 |
| flask-appbuilder | 4.3.7 | 4.8.1 | 最大回归面 |
| Flask-SQLAlchemy | 2.5.1 | 2.5.1 或 3.1.1(实测 FAB 约束) | |
| WTForms / wtforms-json | 2.3.3 / 0.3.5 | 2.3.3 或 3.1.2 / 实测 | |
| Werkzeug | 2.3.7 | 3.1.6 | 安全目标 |
| Jinja2 / MarkupSafe | 3.1.2 / (隐) | 3.1.6 / **2.1.5(新增锁定)** | |
| SQLAlchemy / greenlet | 1.4.49 / (隐) | 1.4.54 / **3.1.1(新增锁定)** | |
| celery / kombu | 5.2.2 / 5.3.2 | 5.4.0 / 5.3.7 | distutils 阻断 |
| gunicorn / gevent | 21.2.0 / 25.5.1 | 23.0.0 / 25.5.1 | |
| pandas / numpy / pyarrow | 2.1.2 / (隐) / >=14.0.0 | 2.2.3 / **1.26.4(新增锁定)** / **16.1.0 或 17.0.0 `==`** | |
| psycopg2-binary | 2.9.8 | 2.9.10 | |
| cryptography | 43.0.0 | 45.x(46.0.5 备选实测) | |
| urllib3 | 1.26.20 | 2.6.3(配 kubernetes 客户端 28.1.0,D7) | |
| kubernetes(PyPI 客户端) | 25.3.0(对应 K8s 1.25 API) | **28.1.0(PyPI 28 系唯一版本,对应 K8s 1.28,匹配集群基线 v1.28.2)** | 代码使用面零改动(§4.3.1a) |
| flask-cors / Markdown / PyMySQL | 3.0.10 / 3.4.4 / 1.1.0 | 6.0.0 / 3.8.1 / 1.1.1 | 安全目标 |
| elasticsearch | 7.12.1 | **删除** | 死依赖 |
| pyhive / thrift / thrift-sasl / sasl | 0.7.0 / 0.20.0 / 0.4.3 / 0.3.1 | **删除**(或 pure-sasl 路线,D3) | 死依赖 |
| gmssl | 3.2.2 | **删除** | 死依赖 |
| Flask-OpenID | 1.3.0 | **删除** | FAB 无 OpenID |
| supervisor / requests_kerberos / krbcontext | 未锁 | **`==` 锁定** | 防漂移 |
| tiktoken | 0.9.0 | 保持,**cp312 轮实测(最高优先)** | |
| node / npm | 16.x(镜像内) | **不进镜像**,行外构建 | 总方案 |
