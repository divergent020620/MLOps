# M3 jupyter 镜像 —— JupyterLab 4 数据集面板（适配版交付）

> 目的：补上《组装交接文档》M3 节里列为「等交接人交付」的三份材料。
> 结论一句话：**面板是前端扩展，行内不装 node 所以编不出来；本目录把 node 构建前置到行外，
> 产出一个「pip 装进去就生效」的 wheel —— 行内零编译。**

---

## 一、解决什么问题

`fix/交接/jupyter/` 里的旧源自述「兼容 JupyterLab 3.x」，在 JL4 上有三处断点：

| # | 旧版断点（JL3 时代写法） | 本版修法 |
|---|---|---|
| **A** | 内联 JS 等 `window.jupyterlab` 全局 —— JL4 已不暴露该对象，`waitForJupyterLab` 永远轮询不到 | 面板改为**真正的 labextension**，用 `JupyterFrontEndPlugin.activate(app)` 拿 shell，完全不碰 window 全局 |
| **B** | `_jupyter_server_extension_paths()` + Tornado `OutputTransform` 注入页面 —— 旧入口名，`add_transform` 在 JL4 上抛异常（源码 `:231` 那句 `OutputTransform 注入失败` 就是它） | 改用 `_jupyter_server_extension_points()`；**彻底删除 OutputTransform 注入**，服务端这层只打日志 |
| **C** | labextension 依赖 `@jupyterlab/* ^3.4.0` + `@lumino/widgets ^1.31.0`，且**没有 `lib/` 预构建产物**（`main` 指向不存在的 `lib/index.js`） | 依赖升到 `@jupyterlab/* ^4` + `@lumino/widgets ^2`；**预构建产物随 wheel 分发** |

> **面板与数据集功能是两件事。**
> 数据能力全在 Cube Studio 后端（`myapp/views/view_dataset.py:683` 的 `/jupyter_list`）
> 和纯 Python 的 `dataset_helper.py` 里 —— 那部分跟 JupyterLab 版本无关，一直是好的。
> 本目录修的只是**侧边栏 UI**。

---

## 二、目录结构

```
fix/jupyter-jl4/
├── labextension/                  ← 前端扩展 TS 源码（不进 wheel）
│   ├── package.json               依赖 @jupyterlab/* ^4、@lumino/widgets ^2
│   ├── tsconfig.json
│   ├── src/index.ts               ★ JL4 版插件实现
│   ├── style/base.css             跟随 JL 亮/暗主题（用 --jp-* 变量）
│   └── schema/plugin.json         设置项：apiBase / autoOpen
├── cube_studio_dataset/           ← Python 包
│   ├── __init__.py                ★ JL4 版入口
│   └── labextension/              ← 构建产物落点（脚本生成）
│       ├── package.json
│       ├── install.json
│       ├── static/remoteEntry.<hash>.js   ★ JL4 实际加载的文件
│       └── schemas/…
├── setup.py  MANIFEST.in  pyproject.toml
├── build_jupyter_ext.sh           ★ 行外一键构建
├── fix_build_paths.py             ★ Windows 反斜杠路径规范化（必须）
├── jupyter-requirements.txt       M3 材料 1
└── out/                           构建产物汇总（脚本生成）
```

---

## 三、行外：构建（本机需 node ≥ 18 + npm，不需要 docker）

```bash
cd <repo root>
bash fix/jupyter-jl4/build_jupyter_ext.sh
```

脚本做七步：

1. 建 venv 并装 `jupyterlab>=4.2,<5`（只有它提供 `jupyter-builder` CLI）
2. `cd labextension && npm install`
3. `npx tsc` —— 先类型检查，早失败
4. `jupyter-builder build . --core-path <jupyterlab>/staging` —— 打 webpack 预构建产物
5. **`fix_build_paths.py` 规范化路径**（见第五节，不做这步麒麟上会白屏）
6. `python -m build --wheel`，并**核验 wheel 里两处都带了 `remoteEntry*.js`**
7. 汇总到 `out/` 并打包成 `fix/jupyter-jl4-pack.tgz`

首次约 3-5 分钟（主要耗在 `npm install`）。

### 产物

| 文件 | 对应 M3 材料 | 说明 |
|---|---|---|
| `out/cube_studio_dataset-2.0.0-py3-none-any.whl` | 材料 2 | JL4 适配版，**自带前端预构建产物** |
| `out/labextension-dist/` | 材料 3 | JL4 预构建前端包（备选装配方式用） |
| `out/jupyter-requirements.txt` | 材料 1 | Python 依赖清单（**范围约束，装完请冻结**） |
| `out/dataset_helper.py`<br>`out/dataset_init.sh`<br>`out/sitecustomize.py` | — | 纯 Python 数据集落地件，与 JL 版本无关 |

---

## 四、行内：装配

### 4.1 装 Python 依赖

```bash
python3.12 -m venv /opt/nbenv
PIP_IDX="http://<user>:<pass>@10.208.29.10:8087/repository/BDAS.BDM-PY-PUBLIC/simple"
/opt/nbenv/bin/pip install --only-binary=:all: \
  --trusted-host 10.208.29.10 --index-url "$PIP_IDX" \
  -r /tmp/jupyter-requirements.txt
```

> `--only-binary=:all:` 是有意的：它保证**不会去现场编译**。
> 任何要 gcc 的包会直接报错停下，而不是偷偷装一半。

### 4.2 ★ 装数据集扩展（关键一步）

```bash
/opt/nbenv/bin/pip install /tmp/cube_studio_dataset-2.0.0-py3-none-any.whl --no-deps
```

**就这一条。没有 `jupyter labextension install`，没有 node，没有 npm。**

装完立刻验证（这条命令是判据，不是参考）：

```bash
/opt/nbenv/bin/python - <<'PYEOF'
from jupyter_core.paths import jupyter_path
from jupyterlab_server.config import get_federated_extensions

BS = chr(92)  # 反斜杠。用 chr() 写，避免 shell/here-doc/Python 三层转义互相打架
exts = get_federated_extensions(jupyter_path('labextensions'))
print('发现的扩展:', list(exts.keys()))
assert 'cube-studio-dataset' in exts, 'FAIL: JupyterLab 看不到扩展，面板不会出现'

e = exts['cube-studio-dataset']
load = e['jupyterlab']['_build']['load']
print('  version :', e['version'])
print('  load    :', load)
assert BS not in load, 'FAIL: 路径含反斜杠，麒麟上会 404'
print('OK: 扩展已被 JupyterLab 4 识别')
PYEOF
```

> 预期输出里 `load` 应是 `static/remoteEntry.<hash>.js`（**正斜杠**）。

### 4.3 数据集落地件（纯 Python，与 JL 无关）

```bash
cp /tmp/dataset_helper.py /opt/dataset_helper.py
cp /tmp/dataset_init.sh   /init-dataset.sh && chmod +x /init-dataset.sh
# sitecustomize.py 若行内已有，不要覆盖，先 diff
cp /tmp/sitecustomize.py  /opt/nbenv/lib/python3.12/site-packages/sitecustomize.py
```

> ⚠️ `dataset_init.sh` 里硬编码了 `/mnt/${USERNAME}` 这个**旧版 notebook 的目录约定**。
> 换 JL4 时这个路径要跟实际部署对齐，否则 `dataset_helper.py` 会被复制到错误位置。

### 4.4 备选装配方式（不走 pip）

若行内策略不允许 pip 装本地 wheel，可以用 `extra_labextensions_path` 直接挂目录：

```bash
install -d /opt/jupyter-labextensions/cube-studio-dataset
cp -r /tmp/labextension-dist/. /opt/jupyter-labextensions/cube-studio-dataset/
# 启动参数追加：
#   --LabApp.extra_labextensions_path=/opt/jupyter-labextensions
```

两条路等价，**推荐 4.2 的 pip 方式**（升级/卸载干净，`pip uninstall` 即可回退）。

---

## 五、★ 一个只在 Windows 行外构建时才会遇到的坑

`jupyter-builder` 用 `os.path.join` 生成 `jupyterlab._build.load`，在 Windows 上得到：

```json
"load": "static\\remoteEntry.9ed04956ef4517a6ee99.js"     ← 反斜杠！
```

JupyterLab 会把它拼成前端 fetch 的 URL：

```
/lab/extensions/cube-studio-dataset/static\remoteEntry.….js
```

- **Windows 上浏览器容忍反斜杠，怎么测都是好的**
- **麒麟（Linux）上反斜杠是合法 URL 字符、不是分隔符 → 404，面板白屏，控制台不一定报错**

对照内置的 `jupyterlab_pygments`，它是 `"static/remoteEntry.….js"`（正斜杠）。

所以 `build_jupyter_ext.sh` 的第 5 步强制跑 `fix_build_paths.py` 规范化，
并在之后 `grep -q '\\\\'` 复验 —— **这一步不能省**。第 4.2 节的验证命令里也带了这个断言。

---

## 六、为什么行内不需要 node（本方案的核心）

```
官方模板（hatch-jupyter-builder）：
    pip install .  →  构建时跑 npm  →  ★ 行内没 node，走不通

本方案：
    行外：npm install + tsc + jupyter-builder build  →  static/remoteEntry.js
                                                          ↓ 随 wheel 分发
    行内：pip install xxx.whl  →  纯拷贝文件  →  JupyterLab 直接加载
                                  ★ 零编译、零 node
```

---

## 七、验收清单

装完容器里逐条过：

- [ ] 4.2 节的验证脚本通过（`cube-studio-dataset` 出现在扩展列表里）
- [ ] `_build.load` 里**没有反斜杠**
- [ ] 启动 JupyterLab，**左侧边栏出现「数据集」Tab**
- [ ] 面板能列出数据集（若为空 → 见下方排查）
- [ ] 点「加载」按钮能复制出 `pd.read_parquet(...)` 代码
- [ ] notebook 里 `from dataset_helper import list_datasets; list_datasets()` 有输出

## 八、排查

| 现象 | 原因 / 处置 |
|---|---|
| 侧边栏**没有**「数据集」Tab | 跑 4.2 的验证脚本。列表里没有 = wheel 没装对；有但没 Tab = 浏览器强刷（Ctrl+Shift+R），JL 有前端缓存 |
| Tab 在，但显示「无法连接 Cube Studio API」 | 面板与 Cube Studio **不同源**。默认走相对路径 `/dataset_modelview/api`；若不同源，用设置项或页面上注入 `window._cube_studio_api` 覆盖 |
| 显示「未登录或登录已过期（401/403）」 | JupyterLab 与 Cube Studio 的登录态不共享，重新登录 Cube Studio |
| 显示「暂无可用数据集」 | 数据集还没下载。先在 Cube Studio「数仓浏览(HDFS)」里下载，或检查 `/mnt/<user>/datasets/` 挂载 |
| `pd.read_parquet` 报缺引擎 | `pyarrow` 没装（`jupyter-requirements.txt` 里有，确认装上了） |
| 装 wheel 报缺 `remoteEntry` | wheel 是坏包。本仓库 `setup.py` 里自带这个断言，正常不会发出这种包 |

---

## 九、和 `fix/交接/jupyter/` 的关系

| | `fix/交接/jupyter/`（旧） | 本目录（新） |
|---|---|---|
| 定位 | **JL3 旧版参考源** | **JL4 适配版（正式交付物）** |
| 声明 | 自述「兼容 JupyterLab 3.x」 | 依赖 `@jupyterlab/* ^4` |
| 面板机制 | Tornado OutputTransform 注入 + `window.jupyterlab` | 真正的 labextension 插件 |
| 预构建产物 | ❌ 无（`main` 指向不存在的 `lib/`） | ✅ 随 wheel 分发 |
| 行内可用 | ❌ `pip install` 后服务端能起、**面板不出现** | ✅ 装完即生效 |
| `dataset_helper.py` 等纯 Python 件 | ✅ 可继续用 | ✅ 原样沿用（本方案一并打包） |

旧目录**不要删** —— 它仍是 `dataset_init.sh` / `hadoop-conf/` / `Dockerfile.hdfs` 等件的事实来源，
本目录只替换掉「面板」这一块。等本方案行内验证通过后，再在交接文档里把旧目录标注为「已废弃」。
