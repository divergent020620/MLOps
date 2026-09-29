# 给装配同事 —— M3 Jupyter Notebook 镜像（py3.12 + JupyterLab 4 + 数据集面板）

> 这份是操作说明，**照着敲就行**。
> 背景/原理/排查见同目录 `README.md`。

---

## 0. 一句话

之前 M3 缺的那几样（JL4 适配版 wheel、预构建前端包、依赖清单）**已经做好了**。
你只需要 build 镜像 —— **不需要 node、不需要 npm、不需要编译**。

---

## 1. 这个包里有什么

| 路径 | 是什么 |
|---|---|
| `out/jupyter-p312-build/` | **★ 现成的 build context，进去直接 docker build** |
| `out/cube_studio_dataset-2.0.0-py3-none-any.whl` | 数据集面板扩展（JL4 适配版，自带前端产物） |
| `out/labextension-dist/` | 同一份前端包（备选装配方式用，一般不用） |
| `out/jupyter-requirements.txt` | Python 依赖清单（JupyterLab 4 线） |
| `out/jupyter-p312-build/init.sh` | 容器启动初始化（SSH + 数据集目录 + helper 落地） |
| `README.md` | 完整技术说明 + 排查表 |

---

## 2. 前提（先确认，缺了会白忙）

```bash
# ① M0 基座镜像必须在
docker images | grep app-base-test-v1

# ② 能连到行内 pip 源
curl -sI http://10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple | head -1
```

如果 ① 没有 —— 先回去做 M0，本包依赖它（它提供 py3.12 + kinit + fontconfig）。

---

## 3. 构建（两条命令）

```bash
# 解包
tar xzf jupyter-jl4-pack.tgz
cd out/jupyter-p312-build

# 构建
docker build \
  -t 10.240.125.39/cube-studio/cube-studio-notebook:jupyter-p312-v1 \
  -f Dockerfile.notebook-p312 .
```

> **`--network=host` 不需要**（pip 源是 IP 直连）。
> 口令轮换了就加一句：`--build-arg PIP_INDEX="http://<user>:<pwd>@10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple"`

**构建会自己把关。** Dockerfile 里有 6 条断言，任何一条不过就直接构建失败，不会产出一个"装得上但面板不显示"的坏镜像。看到下面这段就是过了：

```
════ [5/6] ★ JupyterLab 自己能发现这个扩展吗（最关键的一条）════
发现的扩展: ['cube-studio-dataset', ...]
  version: 2.0.0
  load   : static/remoteEntry.xxxxxxxx.js
  OK: 扩展可被 JL4 加载
════ [6/6] 确认未引入编译链与 node（M3 约束）════
OK: 无 node / 无 gcc
```

---

## 4. 推镜像

```bash
docker tag 10.240.125.39/cube-studio/cube-studio-notebook:jupyter-p312-v1 \
           10.240.125.39/cube-studio/cube-studio-notebook:jupyter-p312-v1
docker push 10.240.125.39/cube-studio/cube-studio-notebook:jupyter-p312-v1

# 留一份离线 tar（行内习惯）
docker save -o nb-p312-v1.tar \
  10.240.125.39/cube-studio/cube-studio-notebook:jupyter-p312-v1
```

---

## 5. 验收（起来之后点一眼）

### 5.1 容器内验（不依赖浏览器）

```bash
docker run --rm -it 10.240.125.39/cube-studio/cube-studio-notebook:jupyter-p312-v1 bash

# 容器里跑：
python -m cube_studio_dataset          # 打印自检 JSON，看 prebuilt 是不是 true
jupyter lab --version                  # 应该是 4.x
ls /opt/nbenv/share/jupyter/labextensions/cube-studio-dataset/static/
```

### 5.2 ★ 浏览器验（这一步必须做）

在 Cube Studio 里起一个 notebook，看：

- [ ] **左侧边栏有「数据集」Tab**
- [ ] 点开能看到数据集列表（有内容，不是"暂无可用数据集"）
- [ ] 点「加载」能复制出 `pd.read_parquet(...)` 代码
- [ ] 贴进 notebook 能跑出 DataFrame

**没看到 Tab 的话，先 Ctrl+Shift+R 强刷**（JupyterLab 有前端缓存），还不行再看 `README.md` 第八节排查表。

---

## 6. 你现在不用改后端

面板调的是 `/dataset_modelview/api/jupyter_list`，**这个接口后端已经有了**
（`myapp/views/view_dataset.py:683`，注册在 `:805`）。

**前提是后端已经换成 py312 版**（M1 做过就行）。后端不用为这个面板改任何代码。

---

## 7. 两件你需要知道的事

### 7.1 「面板」和「数据集功能」是两回事

- **面板** = 侧边栏那块 UI。这次修的就是它。
- **数据集功能** = 能列出、能读。**它一直不依赖面板**，靠 `dataset_helper.py` + 后端接口。

所以就算面板暂时没出来，也可以先让用户这么用（这才是数据能力的兜底）：

```python
from dataset_helper import list_datasets, load_dataset
list_datasets()              # 列出可用数据集
df = load_dataset('数据集名')  # 直接加载成 DataFrame
```

`init.sh` 会把 `/opt/dataset_helper.py` 复制到 `/mnt/<用户名>/`，所以上面这行在用户工作目录里就能 import。

> 顺带说一句：**老版本那套镜像里这一步是坏的** —— `dataset_init.sh` 被拷成了 `/init-dataset.sh`，
> 而平台只执行 `/init.sh`，所以 helper 从没被复制到用户目录。
> 本包的 `init.sh` 已经合并修好了。

### 7.2 这个镜像**不含 HDFS 客户端**

按你说的"纯读数据集不需要 HDFS"，我去掉了：

- 系统包：`krb5-devel` `cyrus-sasl-devel` `gcc` `gcc-c++`
- Python 包：`hdfs` `requests_kerberos` `krbcontext`
- 配置：`hadoop-conf/`、`krb5.conf`

**理由是这条链根本用不到 HDFS**：

```
侧边栏列表   → HTTP 调 Cube Studio 后端 /jupyter_list        （不是 HDFS）
读数据      → pd.read_parquet('/mnt/<user>/datasets/**/data.parquet')   （本地挂载卷）
HDFS 下载   → 发生在后端 celery worker（myapp/tasks/hdfs_tasks.py），不在 notebook 里
```

**但这会影响一件事**：如果有用户**在 notebook 里直接读 HDFS**（`from hdfs import ...`），那会坏。
→ 如果确实有这种用法，`Dockerfile.notebook-p312` 文末有「如何把 HDFS 加回来」的完整步骤。
**上线前跟业务方确认一下这点。**

---

## 8. 出问题找谁

| 现象 | 先做这个 |
|---|---|
| 构建就失败了 | 看断言输出 —— Dockerfile 会明确告诉你哪一条不过、为什么 |
| 镜像起来了但没 Tab | `README.md` 第八节排查表 |
| 有 Tab 但显示"无法连接" | 面板和 Cube Studio 不同源，或登录态过期 |
| 有 Tab 但"暂无可用数据集" | 数据集还没在 Cube Studio 里下载，或 `/mnt/<user>/datasets/` 挂载没生效 |
| 构建报某个包装不上 | **不要自己换版本**，把完整报错发回（M3 边界条款） |
| pip 报 OpenSSL / cryptography 相关错 | 见下面第 9 节 |

---

## 9. 两条行内特有的坑（来自《jupyternotebook环境自建》实践）

### 9.1 pip 报 OpenSSL / cryptography 错

行内的老环境（尤其 OpenSSL 1.0.2 的）装包时会遇到 cryptography 相关报错，
行内通行做法是前置一个开关：

```bash
CRYPTOGRAPHY_ALLOW_OPENSSL_102=1 <pip 命令>
```

**本 Dockerfile 的基座是 py3.12 + 较新 OpenSSL，正常不会遇到。**
如果构建时 pip 真的报了这个错，在 `Dockerfile.notebook-p312` 的 pip 那两行前面加上
`CRYPTOGRAPHY_ALLOW_OPENSSL_102=1` 即可（改 2 处）。

### 9.2 想临时手动装个包试试

行内习惯的写法（和本镜像的源口径一致）：

```bash
/opt/nbenv/bin/python -m pip install <包名> \
    --trusted-host 10.208.29.10 --only-binary=:all:
```

> ⚠️ **装进 `/opt/nbenv` 只在当前容器有效，重启就没了。**
> 要永久生效得改 `jupyter-requirements.txt` 再重建镜像。
>
> 另外注意行内文档里那条：**「如果找不到合适的包，可能是他没有 whl 格式的安装包」** ——
> 去掉 `--only-binary=:all:` 就能源码编译，但**本镜像没有 gcc**，所以这条路走不通，
> 只能换有 wheel 的包或换版本。这正是 §9.1 那个 gssapi 的情况。
