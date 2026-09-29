# jupyter 材料说明(原生 py3.12 版)

> 定位(2026-09-07 定):jupyter 镜像基于 **原生 py3.12.10 + JupyterLab 4.x**(不做 conda/py3.7 移植,不装 node/gcc),但**数据集定制应用层全部保留**(配置/脚本/扩展源均在此目录)。

## 本目录内容与用途

| 项 | 用途 | M3 中怎么用 |
|---|---|---|
| `hadoop-conf/`(core/hdfs/ssl/yarn-site.xml + krb5.conf) | HDFS 数据集配置 | 复制到 `/etc/hadoop/conf/` |
| `krb5.conf` | Kerberos 认证(行内真实版替换) | 复制到 `/etc/krb5.conf`(+ keytab 由部署注入) |
| `init.sh` / `init-spark.sh` / `dataset_init.sh` | 启动/数据集初始化脚本 | COPY 并保留执行位(启动方式按行内约定) |
| `dataset_helper.py` | 数据集辅助 | COPY 到 `/opt/` |
| `sitecustomize.py` | 站点定制(导入路径等) | COPY 到 v env 的 site-packages |
| `cube_studio_dataset/` | 数据集定制扩展(Python 包源) | **迁移线构建 wheel**(JupyterLab4 适配后)后交付 |
| `labextension/` | 数据集前端扩展(JupyterLab 3 api 旧版源) | **迁移线按 JupyterLab 4 API 重建**后交付;本源仅参考 |
| `Dockerfile.hdfs` / `Dockerfile.spark` | 旧版构建参考(conda/3.4.8) | 仅供参考(技术栈差异在文档 M3 小节) |
| `ip-binary` | 旧链遗留二进制(打包时见过)| 核对用途,若不需要直接丢 |

## 迁移线交付物(同事等这些才能合流 M3)

1. `jupyter-requirements.txt` —— jupyterlab 4.x + notebook 7.x + ipykernel + numpy/pandas/... 等(py3.12 兼容,行内 pypi 直装)
2. `cube_studio_dataset-*.whl` —— 本目录 setup.py 行外构建(JupyterLab4 API 适配版)
3. `labextension-dist` —— JupyterLab 4 版预构建前端包
4. (HDFS) —— krb5.conf 用行内真实版;keytab 部署注入

## 其他

- 无 node / 无 gcc / 无任何额外 rpm:labextension 构建与数据集扩展构建全部行外完成
- 参考行内已有 jupyter 实践(`fix/交接/文档/jupyternotebook环境自建_utf8.md`):kernel 闪退查 libffi/sqlite/openssl;用户侧 gssapi 装包需 `%env CFLAGS='-std=c99'`
