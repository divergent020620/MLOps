# Jupyter/Notebook 镜像(py3.12)行内组装与上线交接手册

> 技术储备文档,基于 2026-09 行内组装实操记录整理。
>
> **⚠️ 重要声明:文中所有具体地址(如 Harbor `10.240.125.39`、Nexus `10.208.29.10:8087`、`jupyter` 命名空间、镜像 tag `jupyter-p312-test-v1/v2/v3`、容器名 `nb-p312-01` 等)均为 2026-09 本次操作的实例值,仅作示例;其他操作者必须按自己环境的实际值逐项替换核对后方可使用。**
>
> **⚠️ Nexus 凭证(user-bdas.bdm / bdasbdmPwdNexus 等字样)以行内实际凭证为准,本文不作为凭证来源。**

---

## 一、概述与技术路线定稿

### 1.1 任务定位

M3 任务:在行内麒麟信创环境组装 Cube Studio 的 Jupyter/Notebook 镜像,基于 M0 基础基座(行内 py3.12 基座 + kinit 二进制 + kadm5srv 库 + 中文字体,tag `app-base-test-v1`),叠加:

- py3.12 venv(`/opt/nbenv`)内的 JupyterLab 4.x + Notebook 7.x + ipykernel + 数据科学全家桶(numpy/pandas/sklearn/scipy/matplotlib 等 110+ 包);
- Cube Studio 数据集定制应用层(hadoop-conf、init 脚本、dataset_helper、cube_studio_dataset 服务端扩展 + JL4 预构建前端扩展);
- HDFS Kerberos 认证依赖闭(requests-kerberos / pyspnego / gssapi / decorator / cryptography)。

最终生产 tag:`jupyter-p312-test-v3`(镜像 `10.240.125.39/cube-studio/notebook:jupyter-p312-test-v3`,实例值)。

### 1.2 技术路线:py3.12 原生 + JupyterLab 4.x

2026-09-07 定稿口径(交接包 `交接/jupyter/README.md`):

- **原生 py3.12.10**(行内基座自带,PATH 优先的 `python3` 即 py3.12;系统 python3.7 是 dnf 依赖,勿动勿用);
- **JupyterLab 4.x + Notebook 7.x**(实际装得 jupyterlab 4.6.3 / notebook 7.6.2 / ipykernel 7.3.0 / Jupyter Server 2.21.0);
- **数据集定制应用层全部保留**(配置/脚本/扩展)。

### 1.3 零 conda / 零 node / 零 gcc 的理由

| 排除项 | 理由 |
|---|---|
| conda | 旧链用 Miniconda 4.7.12 + python 3.7.4,属 py3.7 移植路线;新路线直接用基座 py3.12 建 venv,无需 conda,减少一层运行时与审计面 |
| node/npm | 旧链在镜像内 `npm install && npm run build && jupyter lab build` 编译前端扩展;新路线改由迁移线行外交付 **JL4 预构建(prebuilt)扩展 wheel**(remoteEntry.js 联邦模块),镜像内零 node |
| gcc/编译链 | 行内用户不能自装包,且引入编译链会放大安全审计面;唯一例外是 `--no-binary docopt`(见 3.4 节)——docopt 是纯 Python 包,源码构建 wheel 不需要 gcc |

结论:**镜像无额外 rpm、无 node、无编译链**,系统层与 M0 完全一致(rpm 零变化,送评可直接复用 M0 结论)。

### 1.4 与旧链 Dockerfile.hdfs 的技术栈差异

旧链参考文件:`交接/jupyter/Dockerfile.hdfs`(麒麟 v10-sp3-2403 基座):

| 维度 | 旧链 Dockerfile.hdfs | 新链(本手册) |
|---|---|---|
| Python | Miniconda3 4.7.12 + conda env python=3.7.4 | 基座原生 python3.12 + venv `/opt/nbenv` |
| Jupyter | jupyterlab==3.4.8 / notebook==6.4.12 | jupyterlab 4.6.3 / notebook 7.6.2(Jupyter Server 2.21.0) |
| 前端扩展 | 镜像内 npm install + npm run build + `jupyter lab build` | 行外预构建 wheel(cube_studio_dataset-2.0.0,remoteEntry.js 联邦扩展),`pip install` + `--force-reinstall` 覆盖 |
| 系统包 | yum 装 nodejs/npm/gcc/cyrus-sasl-devel/krb5-devel 等一大串 | **零新增 rpm**(Kerberos 二进制/库在 M0 已就位) |
| pip 源 | aliyun 公网镜像 | 行内 Nexus(10.208.29.10:8087,实例值) |
| 构建方式 | docker build | 容器 + docker commit(应对 Nexus 回源 404 抖动,容器内 pip 缓存可累积;见 3.1/八.4) |
| sitecustomize | 无此步 | 交接文档一度要求注入,实操证实 py3.12 下有害,已**停用留档**(见八.1) |
| hdfs 版本 | hdfs(2.7.0,隐含) | **hdfs==2.7.3**(2.7.0 顶层 `import imp`,py3.12 必炸,见八.3) |
| 环境变量 | HADOOP_CONF_DIR + conda PATH | `--change` 注入 `PATH=/opt/nbenv/bin:...`、`HADOOP_CONF_DIR=/etc/hadoop/conf` |

---

## 二、材料清单

### 2.1 交接包 `交接/jupyter/` 目录各文件用途

| 项 | 用途 | 组装中怎么用 |
|---|---|---|
| `hadoop-conf/`(core/hdfs/yarn/ssl-client-site.xml + krb5.conf) | HDFS 数据集配置 | 复制到 `/etc/hadoop/conf/`(注意先 `mkdir -p /etc/hadoop`) |
| `krb5.conf` | Kerberos 客户端配置 | **组装阶段不放占位**;部署时由行内 COPY 真实版到 `/etc/krb5.conf` |
| `init.sh` / `init-spark.sh` / `dataset_init.sh` | 启动/spark/数据集初始化脚本 | COPY 到 `/init.sh`、`/init-spark.sh`、`/init-dataset.sh` 并保留执行位 |
| `dataset_helper.py` | 数据集辅助脚本 | COPY 到 `/opt/dataset_helper.py` |
| `sitecustomize.py` | 旧补丁(py3.8+Spark2.4 cloudpickle 的 types.CodeType 替换) | **py3.12 下停用留档**,不放入 site-packages(见八.1) |
| `cube_studio_dataset/` | 数据集服务端扩展 Python 源(**JL3 旧版,仅应急占位**) | 迁移线正式版为 2.0.0 wheel(见 2.2);源码 `--no-deps` 可装但 JL4 前端面板不生效 |
| `labextension/` | JL3 旧前端扩展源 | **仅参考**,不可用于 JL4;正式版为预构建 wheel 内嵌 |
| `Dockerfile.hdfs` / `Dockerfile.spark` | 旧版构建参考 | 仅对照技术栈差异(见 1.4) |
| `ip-binary` | 旧链遗留二进制 | 核对用途,不需要则丢弃 |

### 2.2 迁移线交付物

| 交付物 | 状态(2026-09 终态) | 说明 |
|---|---|---|
| `jupyter-requirements.txt`(23 包) | ✅ 已交付 | jupyterlab>=4.0,<5 / notebook>=7.0,<8 / ipykernel / numpy / pandas / scikit-learn / scipy / matplotlib / Pillow / seaborn / pyarrow / pymysql / sqlalchemy / requests / pysnooper / jinja2 / pyyaml / hdfs / pika / kafka-python / redis / celery / thrift / pyhive |
| `cube_studio_dataset-2.0.0-py3-none-any.whl` | ✅ 已交付 | **核心交付物**,见下 |
| 风险包 wheel ×4(thrift-sasl / sasl / requests_kerberos / krbcontext) | ⚠️ 部分 | requests-kerberos 已从行内源装;**sasl / thrift-sasl 仍缺行外编译 wheel**(影响 pyhive SASL 场景,遗留风险);**krbcontext 未装**(当前 hdfs Kerberos 链路不需要,脚本若引用再补) |

**cube_studio_dataset-2.0.0 wheel 的结构与价值**:

- 形态:JL4 **预构建联邦扩展** wheel,内含 `remoteEntry.js`(module federation 入口),前端产物已内嵌,镜像内零 node 零 build;
- API:使用新式 `_jupyter_server_extension_points`(JL4),旧版 JL3 的 `_jupyter_server_extension_paths` 已废弃;旧版的 OutputTransform 注入 hack 已删除;
- 安装方式:`pip install --force-reinstall`(覆盖 JL3 旧版同名包);
- 价值:数据集面板在 JupyterLab 4 前端可正常渲染(v3 平台终验"数据集面板出数据"通过)。

---

## 三、组装流程完整命令序列(容器 + commit 法)

> 以下命令中 `<registry>`、容器名、tag 均为示例(本次实例:`10.240.125.39`、`nb-p312-01`),按实际环境替换。

### 3.1 起工作容器

```bash
docker run -d --name nb-p312-01 <registry>/kubeflow-dashboard:app-base-test-v1 bash -c "sleep 3600"
docker exec -it nb-p312-01 bash
# 容器内先留 rpm 基线(送评对照用):
rpm -qa | sort > /root/rpm_before_m3.txt
```

预期:容器 UP;`python3 --version` 为 3.12.x;`which python3` 指向基座 py3.12(勿用 python3.7)。

### 3.2 材料入容器

```bash
# 注意:docker cp 不支持多源!一次一个,逐个拷贝(踩坑见八.6)
docker cp jupyter/ nb-p312-01:/tmp/jy
docker cp jupyter-requirements.txt nb-p312-01:/tmp/jupyter-requirements.txt
docker cp cube_studio_dataset-2.0.0-py3-none-any.whl nb-p312-01:/tmp/
```

预期:容器内 `/tmp/jy/`、`/tmp/jupyter-requirements.txt`、`/tmp/cube_studio_dataset-2.0.0-py3-none-any.whl` 齐全(逐项 `ls` 确认)。

### 3.3 建 venv

```bash
python3.12 -m venv /opt/nbenv
```

预期:`/opt/nbenv/bin/pip` 存在。

### 3.4 装主清单(含 --no-binary docopt 例外与超时重试参数)

```bash
PIP_IDX="http://<user>:<pwd>@10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple"   # 凭证以行内实际为准

/opt/nbenv/bin/pip install \
  --only-binary=:all: \
  --no-binary docopt \
  --trusted-host 10.208.29.10 \
  --timeout 60 --retries 5 \
  --index-url "$PIP_IDX" \
  -r /tmp/jupyter-requirements.txt 2>&1 | tail -5
```

参数说明:

- `--only-binary=:all:`:纪律要求,全 wheel,防源码编译;
- **`--no-binary docopt` 唯一例外**:`hdfs` 依赖 `docopt`,PyPI 仅源码包,不加则 ResolutionImpossible;docopt 是纯 Python 包,源码构建 wheel 不需要 gcc,不改变版本选择——记录在案即可;
- `--timeout 60 --retries 5`:对抗 Nexus 回源抖动(见八.4);
- 预期输出:`Successfully installed ...` 一行,含 jupyterlab 4.6.3 / notebook 7.6.2 / ipykernel 7.3.0 / numpy / pandas / scikit-learn / matplotlib / seaborn / pyarrow / pyhive 等 110+ 包。

**Nexus 404 抖动应对**:大 wheel 首拉常见 404(numpy 2.5.3、scikit-learn 1.9.0 均遇过),策略 = **原样重跑同一命令直至通过**(容器内 pip 缓存会累积,越跑越快)。这是放弃 docker build 改容器+commit 的直接原因。

### 3.5 导入冒烟(装扩展前)

```bash
/opt/nbenv/bin/python -c "import jupyterlab, notebook, ipykernel, numpy, pandas, sklearn; print('imports OK')"
/opt/nbenv/bin/jupyter lab --version    # 预期 4.6.3
```

预期:输出 `imports OK`。注意此冒烟要**在配置/脚本注入之前跑**(若 sitecustomize 被误注入,见八.1 的因果链)。

### 3.6 配置/脚本注入

```bash
# 首次 cp 到 /etc/hadoop/conf 会因 /etc/hadoop 不存在而失败,必须先建目录:
mkdir -p /etc/hadoop
cp -a /tmp/jy/hadoop-conf /etc/hadoop/conf
cp /tmp/jy/init.sh /init.sh
cp /tmp/jy/init-spark.sh /init-spark.sh
cp /tmp/jy/dataset_init.sh /init-dataset.sh
chmod +x /init-dataset.sh /init.sh /init-spark.sh
cp /tmp/jy/dataset_helper.py /opt/dataset_helper.py

# /etc/krb5.conf 按纪律【不放占位】——部署阶段由行内 COPY 真实版(基座默认件不可用)
# sitecustomize.py【不注入】(py3.12 下毒害 isinstance,见八.1);留档即可:
mv /tmp/jy/sitecustomize.py /opt/sitecustomize.py.disabled
```

预期:`ls /etc/hadoop/conf/` 见 core/hdfs/yarn/ssl-client-site.xml + krb5.conf;`/init*.sh` 三件有 x 位;容器内**没有** `/etc/krb5.conf` 占位、site-packages **没有** sitecustomize.py。

### 3.7 数据集扩展安装(2.0.0 wheel)

```bash
# 安装(pip 校验 wheel 文件名,不能改名为 csd.whl 之类,见八.5):
/opt/nbenv/bin/pip install /tmp/cube_studio_dataset-2.0.0-py3-none-any.whl --no-deps --force-reinstall
/opt/nbenv/bin/python -c "import cube_studio_dataset; print('ext import OK')"
```

`--force-reinstall`:JL3 旧版占位包同名,直接覆盖。`--no-deps`:wheel 依赖闭由主清单+手动补齐控制。

### 3.8 server extension 启用与 config.d 手写 JSON

```bash
/opt/nbenv/bin/jupyter server extension enable --py cube_studio_dataset --sys-prefix
```

**注意**:该命令很可能报 `module could not be found` / 校验失败——根因是**扩展包缺 config.d 元数据**(jupyterlab/notebook 均随包自带此元数据,自研包常缺),不是模块真丢(解释器/路径均正常)。处理:手写标准 JSON:

```bash
mkdir -p /opt/nbenv/etc/jupyter/jupyter_server_config.d
cat > /opt/nbenv/etc/jupyter/jupyter_server_config.d/cube_studio_dataset.json <<'EOF'
{
  "ServerApp": {
    "jpserver_extensions": {
      "cube_studio_dataset": true
    }
  }
}
EOF

# 校验:
/opt/nbenv/bin/jupyter server extension list
```

预期:`cube_studio_dataset` 显示 `enabled ✓`,校验 OK。

### 3.9 启动冒烟(--allow-root)

```bash
/opt/nbenv/bin/jupyter lab --allow-root --port=18888 --ip=127.0.0.1 2>&1 | head -40
```

判据:

- 容器内 root 运行**必须带 `--allow-root`**,否则末尾被 "Running as root" 拦截退出(平台启动模板本就带,属预期);
- 成功标志:`Jupyter Server 2.21.0 is running at: http://127.0.0.1:18888/lab?token=...`,无 Traceback;
- 2.0.0 扩展应见 "v2.0.0 已加载(prebuilt)" 类日志;旧 JL3 版则会出现 `[Cube Studio] OutputTransform 注入失败: missing 'request'`(旧 tornado 签名不兼容,try/except 兜住不影响启动,属换 2.0.0 的信号)。

### 3.10 清缓存 + rpm 零变化验证

```bash
/opt/nbenv/bin/pip cache purge        # 或 rm -rf /root/.cache/pip
rpm -qa | sort > /root/rpm_after_m3.txt
# ⚠ 基座精简容器内没有 diff 命令(实测踩坑),用 python3 集合对比:
python3 -c 'a=set(open("/root/rpm_before_m3.txt").read().split()); b=set(open("/root/rpm_after_m3.txt").read().split()); print("新增:",sorted(b-a)); print("移除:",sorted(a-b))'
```

预期:**零差异**(或仅剩 M0 字体 7 包的既有差异——以 M0 最终基线为对照,新增恰为 fontconfig/wqy-microhei-fonts/libX11 系/freetype,移除 0)。送评口径:M3 系统层与 M0 完全一致,M0 结论直接覆盖。

### 3.11 commit(--change 注入 ENV)

```bash
exit   # 退出容器
# ⚠ ENV PATH 写完整字面值($PATH 不展开),本次实例完整值:
docker commit \
  --change 'ENV PATH=/opt/nbenv/bin:/opt/python3.12.10-x86_64-bin/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  --change 'ENV HADOOP_CONF_DIR=/etc/hadoop/conf' \
  nb-p312-01 <registry>/cube-studio/notebook:jupyter-p312-test-v1
```

要点:**一律用全新 tag,不覆盖任何原镜像**;ENV 用 `--change` 注入(不要指望 profile.d,K8s 非登录 shell 不生效)。

### 3.12 新镜像验证 + 导出

```bash
docker run --rm <registry>/cube-studio/notebook:jupyter-p312-test-v1 bash -c \
  'echo $PATH; echo $HADOOP_CONF_DIR; which python; /opt/nbenv/bin/python -c "import jupyterlab, cube_studio_dataset; print(\"OK\")"; ls /etc/hadoop/conf'
docker save -o /bdm/images-kylin/nb-p312-test-v1.tar <registry>/cube-studio/notebook:jupyter-p312-test-v1
docker rm nb-p312-01   # 确认 commit 无误后清理工作容器
```

预期:PATH 首段为 `/opt/nbenv/bin`;python 指向 nbenv;hadoop-conf 在位;tar 落盘(本次 v1 约 2G)。

---

## 四、v1 → v3 版本演进与整改

| 版本 | 内容 | 差异点 |
|---|---|---|
| **v1**(jupyter-p312-test-v1) | 初版组装 | 主清单装齐;cube_studio_dataset 装的是包内 **JL3 旧源**占位(服务端加载 OK,JL4 前端面板不生效,OutputTransform 注入失败日志);hdfs 装的还是 2.7.0;sitecustomize.py 已按交接文档注入 site-packages(隐患);风险包未装。tar 已导出送评 |
| **v2**(jupyter-p312-test-v2) | 扩展升级 2.0.0 | 平台测试 Pod 实锤 JL3 面板不出现(见五.1)后,迁移线交付 **cube_studio_dataset-2.0.0 wheel(JL4 预构建联邦扩展,remoteEntry.js,新 API `_jupyter_server_extension_points`,OutputTransform 已删)**;容器内 `--force-reinstall` 覆盖(注意 pip 校验 wheel 文件名,改名会报 invalid);冒烟确认 "v2.0.0 已加载(prebuilt)";commit v2 → push |
| **v3**(jupyter-p312-test-v3,**生产终版**) | 三项整改 | ① **sitecustomize.py 停用**:pyarrow import 报 `isinstance arg2 must be a type`,根因即 v1 注入的 sitecustomize(见八.1),`mv` 至 `/opt/sitecustomize.py.disabled` 留档;② **hdfs 2.7.0 → 2.7.3**:全量包排查 23/24 OK、唯一 FAIL 是 hdfs 2.7.0 顶层 `import imp`(py3.12 已移除),用行外重打的 2.7.3 wheel `--no-deps --force-reinstall`,24/24 OK;③ **Kerberos 依赖闭补齐**(见下)。commit 同款 ENV → push → **平台重建 notebook 终验通过**(数据集面板出数据、import pyarrow/hdfs 正常) |

**Kerberos 组补齐明细(v3)**:`hdfs.ext.kerberos` → `requests_kerberos` 缺(--no-deps 连锁,见八.3):

- `requests-kerberos 0.15.0` + `pyspnego 0.12.2`(行内源直装);
- `gssapi 1.9.0` + `decorator 5.3.1`(offline wheel);
- `cryptography 46.0.5`(pyspnego 依赖、清单缺口;版本与后端送评修正对齐;**不带 --no-deps**,让其依赖 cffi 正常解析,连带 cffi 升级)。

验证:`python -c "from hdfs.ext import kerberos; print('HDFS-Kerberos OK')"` + 全量 24 包 import 复验。

**给清单维护方的钉子更新建议(已反馈)**:jupyter-requirements 钉 `hdfs==2.7.3`、补 `cryptography==46.0.5`。

---

## 五、数据集扩展专题

### 5.1 JL3 旧版失效根因(两条渲染路径全断)

用包内 JL3 源占位时,平台测试 Pod(admin-9c60-test,实例值)证实数据集面板不出现,根因两条:

1. **服务端路径**:`[Cube Studio] OutputTransform 注入失败: missing 'request'` —— 旧源用 OutputTransform hack 注入,与新 tornado 签名不兼容(try/except 兜住,不影响启动但功能失效);
2. **前端路径**:旧 JS 等 `window.jupyterlab` 全局(JL3 时代约定),JL4 已改 module federation,前端资源根本不挂。

且旧源仅暴露 `_jupyter_server_extension_paths`(JL3 API)。结论:JL3 源只能作服务端占位,面板必须等 2.0.0 wheel。

### 5.2 2.0.0 wheel 安装注意

- **pip 校验 wheel 文件名**:文件名必须与包元数据一致(格式 `名称-版本-py3-none-any.whl`),改名为 `csd.whl` 之类会报 invalid,不要改名传递;
- 覆盖安装必须 `--force-reinstall`(同名包默认跳过);
- 安装后 config.d JSON 已就位则无需再动(M3-8 手写的 JSON 对 2.0.0 同样有效)。

### 5.3 平台启用(NOTEBOOK_IMAGES 注册)

- 镜像本身可用 ≠ 平台可用:Cube Studio 平台 notebook 镜像是**动态拉起**(jupyter 命名空间),注册点在 config.py 的 `NOTEBOOK_IMAGES`(实例参考:k8s-config/config.py 约第 748 行);
- **坑**:改 NOTEBOOK_IMAGES 不是改一行就完——它是 py312 ConfigMap 三件套(config.py/entrypoint.sh/project.py)的一部分,必须**三件套一起重建 ConfigMap + rollout restart dashboard**,漏一步不生效;
- 本次测试期已按此方式验证注册可行;正式注册由平台负责人执行。

---

## 六、Pod 测试方法

### 6.1 原则

- 用**独立测试 Pod**,不动任何用户 notebook;
- 先把镜像 push 到 Harbor(kubelet 只认 Harbor,不认构建机本机 docker);

```bash
docker push <registry>/cube-studio/notebook:jupyter-p312-test-v1   # 实例输出:digest sha256:... size: 2009
```

### 6.2 测试 Pod YAML(jupyter 命名空间)

```yaml
# /tmp/nb-imgtest.yaml(实例)
apiVersion: v1
kind: Pod
metadata:
  name: nb-imgtest-v1
  namespace: jupyter          # jupyter 命名空间(实例值)
spec:
  restartPolicy: Never        # 测试 Pod 用完即止,不自动重启
  containers:
  - name: nb
    image: 10.240.125.39/cube-studio/notebook:jupyter-p312-test-v1   # 按实际替换
    command: ["jupyter", "lab", "--allow-root", "--ip=0.0.0.0", "--port=8888"]
```

### 6.3 判据与执行

```bash
kubectl apply -f /tmp/nb-imgtest.yaml          # pod/nb-imgtest-v1 created
sleep 15
kubectl get pods -n jupyter nb-imgtest-v1      # 预期 1/1 Running,RESTARTS 0
# 日志判据①:server 起来
kubectl logs -n jupyter nb-imgtest-v1 | grep -E "is running|Traceback"
#   预期:[I ... ServerApp] Jupyter Server 2.21.0 is running at:
# 日志判据②(v2/v3 镜像):扩展 2.0.0 已加载(v2.0.0 loaded / prebuilt 字样)
# HTTP 判据:
kubectl exec -n jupyter nb-imgtest-v1 -- curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/lab
#   预期:302 —— 重定向到 token 登录页,属预期,不是故障
# 测完清理:
kubectl delete -f /tmp/nb-imgtest.yaml
```

**注意**:`curl /lab` 返回 302 是正常现象(未带 token 重定向到登录页);若 404/连接拒绝/重启计数增长才是故障。grep `Traceback` 必须为空。

---

## 七、命令速查表(按阶段)

| 阶段 | 命令 |
|---|---|
| 起容器 | `docker run -d --name nb-p312-01 <BASE> bash -c "sleep 3600"` |
| 入材料(逐个) | `docker cp jupyter/ nb-p312-01:/tmp/jy` 等,一文件一命令 |
| 建 venv | `python3.12 -m venv /opt/nbenv` |
| 装主清单 | `/opt/nbenv/bin/pip install --only-binary=:all: --no-binary docopt --trusted-host 10.208.29.10 --timeout 60 --retries 5 --index-url "$PIP_IDX" -r /tmp/jupyter-requirements.txt` |
| 导入冒烟 | `/opt/nbenv/bin/python -c "import jupyterlab, notebook, ipykernel; print('imports OK')"` |
| 配置注入 | `mkdir -p /etc/hadoop && cp -a /tmp/jy/hadoop-conf /etc/hadoop/conf && cp /tmp/jy/init.sh /init.sh && cp /tmp/jy/init-spark.sh /init-spark.sh && cp /tmp/jy/dataset_init.sh /init-dataset.sh && chmod +x /init*.sh && cp /tmp/jy/dataset_helper.py /opt/` |
| 装扩展 | `/opt/nbenv/bin/pip install /tmp/cube_studio_dataset-2.0.0-py3-none-any.whl --no-deps --force-reinstall` |
| 启用扩展 | 手写 `/opt/nbenv/etc/jupyter/jupyter_server_config.d/cube_studio_dataset.json` + `jupyter server extension list` 校验 |
| hdfs 修复 | `/opt/nbenv/bin/pip install <hdfs-2.7.3-wheel 路径> --no-deps --force-reinstall` |
| Kerberos 组 | `pip install requests-kerberos==0.15.0 pyspnego==0.12.2`(行内源);`pip install gssapi-1.9.0 decorator-5.3.1`(offline wheel);`pip install cryptography==46.0.5`(不带 --no-deps) |
| 启动冒烟 | `/opt/nbenv/bin/jupyter lab --allow-root --port=18888`(判据 `is running at`) |
| rpm 验证 | `rpm -qa \| sort > after.txt && diff before.txt after.txt`(预期零差异) |
| commit | `docker commit --change 'ENV PATH=/opt/nbenv/bin:/opt/python3.12.10-x86_64-bin/bin:/usr/local/sbin:...(完整字面值,$PATH 不展开)' --change 'ENV HADOOP_CONF_DIR=/etc/hadoop/conf' nb-p312-01 <registry>/cube-studio/notebook:<新tag>` |
| 导出/推送 | `docker save -o nb-p312-test-vX.tar ...` / `docker push ...` |
| Pod 测试 | `kubectl apply -f nb-imgtest.yaml` → `kubectl logs` grep `is running` → `curl /lab` 期望 302 → `kubectl delete -f` |

---

## 八、潜在问题与坑(全面清单)

### 8.1 sitecustomize.py 毒害 isinstance(最重要的坑)

完整因果链:

1. 交接组装文档要求把 `sitecustomize.py` 拷进 venv site-packages(旧链 py3.8 + Spark2.4 时代,cloudpickle 兼容补丁,会把 `types.CodeType` 替换成函数);
2. py3.12 下该替换本身能静默成功(sitecustomize 在解释器启动时自动 import);
3. 副作用:此后任何触发 C 扩展类型检查的 import 都可能炸,典型:`import pyarrow`(→numpy)报 **`isinstance() arg 2 must be a type`**(被替换的 CodeType 传入了 C 层的 isinstance);
4. 为什么初装冒烟没暴露:M3-5 的 imports 冒烟跑在**配置注入之前**,sitecustomize 尚未进 site-packages;
5. 佐证:旧链 Dockerfile.hdfs **没有** sitecustomize 这一步,说明它不是 notebook 运行必需,而是某历史后端场景补丁;
6. **处理:停用留档** —— `mv sitecustomize.py /opt/sitecustomize.py.disabled`(不删,保留追溯);py3.12 组装一律不注入;
7. 已反馈:组装交接文档 M3 的 sitecustomize cp 命令应删除。

### 8.2 hdfs 2.7.0 `import imp`

hdfs 2.7.0 顶层 `import imp`,而 `imp` 模块在 py3.12 已移除 → `import hdfs` 直接 ImportError。行内源若只回源 2.7.0,需用行外重打的 **hdfs 2.7.3** wheel(`--no-deps --force-reinstall`);清单应钉 `hdfs==2.7.3`。

### 8.3 --no-deps 的连锁依赖闭要手动补齐

扩展/hdfs 均用 `--no-deps` 装(避免拉起不受控依赖),后果是被跳过的依赖**全部要手动补**:本次链条为 `hdfs.ext.kerberos → requests-kerberos → pyspnego → cryptography(→cffi 升级)`,还叠 gssapi/decorator。装完务必做 `pip check` + `python -c "from hdfs.ext import kerberos"` 断言;清单缺口(cryptography)要反馈维护方。

### 8.4 Nexus 404 抖动

行内 Nexus(回源型)对大 wheel 首次拉取常见 404(numpy/scikit-learn/pyarrow/cryptography 均遇过),**重跑即过**。对策:命令带 `--timeout 60 --retries 5`;用容器+commit 流而非 docker build(build 失败整体重来、无 pip 缓存,放大该问题)。

### 8.5 pip 校验 wheel 文件名

`pip install xxx.whl` 会校验文件名与元数据一致性;传输时改名(如 `csd.whl`)会报 invalid。wheel 原名保管、原名安装。

### 8.6 docker cp 不支持多源

`docker cp a.txt b.txt c:/tmp/` 会报错,且在脚本里可能**连带跳过后续拷贝**而不显眼(M1 曾因此漏 keytab/krb5.conf)。纪律:一次一个文件 cp,拷完逐项 `ls` 对账。

### 8.7 扩展包缺 config.d 元数据,enable "误报"

`jupyter server extension enable --py cube_studio_dataset` 报 "module could not be found" **不是模块缺失**,是包缺 `config.d` 元数据(enable 的校验机制依赖它)。手写标准 JSON 到 `jupyter_server_config.d/` 即可,`extension list` 显示 enabled ✓ 为准。

### 8.8 JL3 旧源仅参考

包内 `labextension/` 与 `cube_studio_dataset/` 源均为 JL3 版(OutputTransform hack + `window.jupyterlab`),JL4 前端不生效;必须用迁移线 2.0.0 预构建 wheel。若装了旧版做占位,覆盖时记得 `--force-reinstall`。

### 8.9 /etc/krb5.conf 部署注入,组装不放占位

组装阶段不向 `/etc/krb5.conf` 放任何占位文件(基座默认件 ≠ 行内真实配置);部署时由行内 COPY/K8s 注入真实 krb5.conf + keytab。kinit 二进制与 kadm5srv 库已由 M0 基座提供。

### 8.10 风险包 sasl / thrift-sasl 仍缺行外 wheel

`jupyter-risico-requirements.txt` 中 thrift-sasl / sasl 无纯 Python wheel,需行外编译;**截至终态仍未交付**,影响 pyhive 的 SASL 认证场景(`hive.connection` 用 SASL 时不可用,纯 thrift 模式不受影响)。requests-kerberos 已由行内源解决;**krbcontext 未安装**(当前 hdfs Kerberos 链路不需要,若后续脚本引用再补装,行内源有)。

### 8.11 root 启动必须 --allow-root

容器内 root 跑 `jupyter lab` 会被 "Running as root is not allowed" 拦截;镜像层不需处理(平台启动模板自带 `--allow-root`),手动冒烟必须带。

### 8.12 kernel 闪退排查(参考行内实践 jupyternotebook环境自建_utf8.md)

行内已有实践的经验:kernel 闪退看 jupyter 报错,一般是 libffi / sqlite / openssl 等系统环境问题,对症补环境;用户侧装 gssapi 遇 C 编译规范问题时 `%env CFLAGS='-std=c99'` 后再装;`%pip` 与 `!pip` 不同(% 识别当前 kernel,! 走系统环境);装包用 `python3 -m pip` 指定解释器防串环境。这些属用户侧使用问题,不影响镜像组装,但答疑时可参考。

### 8.13 其他小项

- 提交一律**全新 tag**,不覆盖原镜像;`docker tag` 只建别名不改镜像;
- v1/v2 等中间 tag 验证闭环后可 `docker rmi` 清理(本次保留 v3 为终版);
- 平台注册 NOTEBOOK_IMAGES 时必须三件套一起重建(见 5.3);
- 冒烟时 `curl /lab` 302 属预期(见六)。

---

## 九、重建路径:Dockerfile.notebook-py312 固化版

### 9.1 定位

容器+commit 法适合首装试错(可重跑、可对账),但不可复现、不可审计。终态闭环后,应把 v3 的最终态固化为 **Dockerfile.notebook-py312**(工作区路径 `D:\BOSC\MLOps\9-7-前后端jupyter依赖任务\Dockerfile.notebook-py312`;**已按 v3 终态落地**,含扩展 2.0.0/Kerberos 组/hdfs 2.7.3/sitecustomize 警告注释,以文件为准,本章保留应固化内容的框架说明)。

### 9.2 固化版应包含的内容(与 v3 终态一一对应)

```dockerfile
FROM <registry>/kubeflow-dashboard:app-base-test-v1          # M0 基座
ENV HADOOP_CONF_DIR=/etc/hadoop/conf
ENV PATH=/opt/nbenv/bin:$PATH

# ① venv + 主清单(--no-binary docopt 例外固化进命令)
RUN python3.12 -m venv /opt/nbenv && \
    /opt/nbenv/bin/pip install --only-binary=:all: --no-binary docopt \
      --trusted-host <nexus-host> --timeout 60 --retries 5 \
      --index-url "<PIP_IDX>" -r /tmp/jupyter-requirements.txt
# ② hdfs 2.7.3 + Kerberos 组(requests-kerberos/pyspnego/gssapi/decorator/cryptography 46.0.5)
# ③ cube_studio_dataset-2.0.0 wheel(--no-deps)+ 手写 config.d JSON
# ④ hadoop-conf/、init*.sh、dataset_helper.py(sitecustomize.py 不出现;krb5.conf 不出现)
# ⑤ 构建末尾断言:全量 import + HDFS-Kerberos OK + jupyter lab --allow-root 冒烟
```

同时应固化清单文件:jupyter-requirements.txt(钉 hdfs==2.7.3、cryptography==46.0.5)。

### 9.3 适用场景与用法

| 场景 | 用法 |
|---|---|
| 环境**无** Nexus 404 抖动 / 源稳定 | 直接 `docker build` 一步到位,产物可审计可复现 |
| 环境**有**回源抖动 | docker build 每次失败整体重来;要么多跑几次,要么仍走容器+commit(本文第三章)作为兜底 |
| 换基座/换源/版本升级 | 先改 Dockerfile + 清单,在测试 tag 上构建验证,判据同第三章(imports OK / is running at / rpm 零变化),通过后再换正式 tag |

构建验证判据(与容器法一致):`PATH`/`HADOOP_CONF_DIR` 正确、全量 24 包 import OK、`Jupyter Server ... is running at`、`rpm -qa` 与 M0 基线零差异、Pod 测试(第六章)通过。

---

## 附:本次(2026-09)实例终态快照

- 生产镜像:`10.240.125.39/cube-studio/notebook:jupyter-p312-test-v3`(示例值)
- 内容:JL 4.6.3 / Notebook 7.6.2 / Jupyter Server 2.21.0 / 扩展 2.0.0(JL4 预构建)/ sitecustomize 停用 / hdfs 2.7.3 / Kerberos 组齐 / cryptography 46.0.5
- 验证:镜像级冒烟 ✅、独立 Pod 测试 ✅、平台重建终验 ✅(数据集面板出数据)
- 遗留:sasl/thrift-sasl 行外 wheel 未交付;NOTEBOOK_IMAGES 正式注册由平台侧执行;handover-docs 缺 3 份文档
