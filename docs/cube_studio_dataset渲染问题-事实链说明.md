# cube_studio_dataset 数据集面板不渲染 —— 事实链说明

> 面向：交接人 / 装配同事
> 目的：把「扩展没丢」和「面板不出」这两件事分开，并说明**因果不在组装环节**
> 标注约定：**【已核实】**= 可在仓库/交付包中按 `文件:行号` 复核；**【待补证】**= 出自流程记录或运行态观察，尚未落盘为文件

---

## 一、结论先行

```
错误归因：组装把功能弄丢了 / 交付物里有就能用
正确归因：JupyterLab 4 适配版这个交付物尚未产出；
         现场装的是包内旧源（JL3 版）作占位 —— 服务端能起、不炸，
         但渲染层在等适配版。这不是组装问题，是交付物缺位。
```

一句话：**不是"被去除了"，是"被装上了一个注定渲染不出来的旧版"。**

---

## 二、事实链

### 事实 1 · 扩展确实装了，服务端一直在跑，没被删

**【待补证】** 来自运行态（需附证据）：

| 观察点 | 记录值 |
|---|---|
| pip 安装 | `cube_studio_dataset` 已安装 |
| config.d JSON | 已启用 |
| Pod 日志 | `cube_studio_dataset \| extension was successfully linked` |
| 代码改动 | 服务端一行未删 |

**要说明的点**：`extension was successfully linked` 只证明 **server extension 加载成功**，
它证明不了**前端渲染**。这两件事在 JupyterLab 里是两条独立链路：

```
server extension（Python）  → extension was successfully linked   ← 这里成功了
labextension（前端 JS/TS）  → 侧边栏出现面板                        ← 这里没成功
```

**所以"日志里有 successfully linked"不能推出"应该能看到面板"。**

### 事实 2 · 它渲染不了 —— 源码级三处断点【已核实】

被装进去的那份源码，自己就在文件头声明了它的适配目标：

```python
# fix/交接/jupyter/cube_studio_dataset/__init__.py:L1-9
"""
Cube Studio Dataset — Jupyter Server Extension

在 JupyterLab 侧边栏添加 "数据集" 面板。
纯 Python 实现，无需 TypeScript 编译，兼容 JupyterLab 3.x。     ← ★ L5 自述
                                                                   
用法:
    pip install cube_studio_dataset/
    jupyter serverextension enable --py cube_studio_dataset --sys-prefix   ← ★ L9 旧命令
"""
```

> **L5 原文就是「兼容 JupyterLab 3.x」。**
> **L9 用的还是 `jupyter serverextension enable`** —— jupyter_server 1.x 的旧命令；
> JL4 配套的 jupyter_server 2.x 是 `jupyter server extension enable`（有空格）。
> 这份文档连自己的安装说明都还是 JL3 写法。

三处断点逐条对应：

| # | 断点 | 证据 | 为什么在 JL4 上必定失败 |
|---|---|---|---|
| **A** | 前端 JS 等 `window.jupyterlab` 全局变量 | `__init__.py:26`<br>`if (window.jupyterlab && window.jupyterlab.shell) {`<br>`__init__.py:36`<br>`var lab = window.jupyterlab;` | **JL4 不再向 `window` 暴露 `jupyterlab` 这个全局对象。** 这段 `waitForJupyterLab` 轮询会**永远等不到**，面板永不挂载 |
| **B** | server extension 用 JL3 旧入口 + Tornado `outputTransform` 注入 | `__init__.py:195`<br>`def _jupyter_server_extension_paths():`<br>`__init__.py:207`<br>`def _load_jupyter_server_extension(lab_app):`<br>`__init__.py:221`<br>`def transform_first_chunk(self, status_code, headers, chunk, finishing):`<br>`__init__.py:228`<br>`lab_app.web_app.add_transform(_InjectPanelJS())` | `_jupyter_server_extension_paths()` 是 jupyter_server 1.x 的旧入口名（2.x 起用 `_jupyter_server_extension_points()`）。<br>`add_transform` 这条注入路径在 JL4 环境下**实际失败** —— 冒烟当天已记录 `OutputTransform 注入失败`（M3-9，**【待补证】**）。<br>**源码自己就写了这个失败分支**，见下 |
| **C** | labextension 依赖整套 `@jupyterlab/* ^3.4.0` | `labextension/package.json:25-27`<br>`"@jupyterlab/application": "^3.4.0"`<br>`"@jupyterlab/apputils": "^3.4.0"`<br>`"@lumino/widgets": "^1.31.0"` | JL4 对应的是 `@jupyterlab/* ^4.x` + `@lumino/widgets ^2.x`。**大版本 API 完全不同**，不能直接跑在 JL4 上 |

**断点 B 的关键细节 —— 失败是源码预期内的，它自己打了 warning：**

```python
# __init__.py:L214-231
    # 方式1: Tornado OutputTransform (兼容 Jupyter Server 1.x / 2.x)   ← 注释声称兼容 2.x
    if hasattr(lab_app, 'web_app'):
        from tornado.web import OutputTransform
        ...
        try:
            lab_app.web_app.add_transform(_InjectPanelJS())
            lab_app.log.info('[Cube Studio] 数据集面板扩展已加载 (OutputTransform)')
        except Exception as e:
            lab_app.log.warning(f'[Cube Studio] OutputTransform 注入失败: {e}')   ← ★ L231
```

> **`OutputTransform 注入失败` 这句 warning 就在源码 L231 —— 作者自己预留的失败分支。**
> 连接收失败的兜底都写好了，说明这个注入路径本身就不稳。
> 这与流程记录里「组装当天冒烟就报了 outputTransform 注入失败（M3-9）」**完全对应**。
> **【待补证】**：M3-9 那条冒烟记录的具体编号与截图，需从流程记录调出。

**断点 C 还有一个硬伤：这份 labextension 根本没有可用的预构建产物。**

```json
// labextension/package.json:L8, L11, L32
"main": "lib/index.js",          ← 指向 lib/，但包内没有 lib/
"build": "tsc",                  ← 需要 TypeScript 编译（而 JL4 线明确不装 node/编译链）
"typescript": "~4.1.6",
```

实测 `labextension/` 目录内容：

```
fix/交接/jupyter/labextension/
├── package.json
├── schema/plugin.json
├── src/index.ts        ← 只有 TS 源
├── style/base.css
└── tsconfig.json
```

**没有 `lib/`。** 而 `main` 指向 `lib/index.js`。
→ 即使忽略 API 版本差异，它也**必须先在行外 `tsc` 编译**才能用；
而 M3 的环境约束是「不装 node / gcc / 编译链」。

**【已核实】** 附带一提：迁移评估报告早在评估阶段就把这块列为风险区 ——
`py312/Python312迁移评估报告.md:254`：「`tornado 6.1→6.3.3+`、
`jupyterlab 3.6.3/jupyter_server 1.23.6(3.12 下需实测或升 4.x/2.x)`」。

### 事实 3 · 交接文档自己就把这块列为「待交付材料」【已核实】

这不是事后解释，是**文档当时的原文定义**。

#### 3.1 `fix/交接/文档/组装交接文档.md` M3 节（`:130` 起）

> ### M3 jupyter 镜像(原生 py3.12 版,约 1 天)
>
> **材料(等交接人交付)**:
> 1. `jupyter-requirements.txt` —— jupyterlab 4.x + notebook 7.x + ipykernel + numpy/pandas/... 等(py3.12 兼容清单)
> 2. **`cube_studio_dataset-*.whl` —— 包内源行外构建(JupyterLab4 API 适配版)**
> 3. **`labextension-dist` —— JupyterLab 4 版预构建前端包(包内源为旧版参考)**
>
> ---
> **边界:jupyterlab 4 版本组合若安装/启动异常 → 完整报错交回(版本选择由交接人定);
> labextension 旧源只作参考,必须用迁移线交付的 4 版**

注意第 2、3 条：**`cube_studio_dataset-*.whl` 的定义就是「JupyterLab4 API 适配版」**，
**`labextension-dist` 的定义就是「JupyterLab 4 版预构建前端包」，且明写「包内源为旧版参考」。**

#### 3.2 `fix/交接/jupyter/README.md`（材料目录自己的说明）

> | 项 | 用途 | M3 中怎么用 |
> |---|---|---|
> | `cube_studio_dataset/` | 数据集定制扩展(Python 包源) | **迁移线构建 wheel**(JupyterLab4 适配后)后交付 |
> | `labextension/` | 数据集前端扩展(**JupyterLab 3 api 旧版源**) | **迁移线按 JupyterLab 4 API 重建**后交付;**本源仅参考** |
>
> ## 迁移线交付物(同事等这些才能合流 M3)
> 1. `jupyter-requirements.txt`
> 2. `cube_studio_dataset-*.whl` —— 本目录 setup.py 行外构建(JupyterLab4 API 适配版)
> 3. `labextension-dist` —— JupyterLab 4 版预构建前端包

**目录自己的 README 白纸黑字写着 `labextension/` 是「JupyterLab 3 api 旧版源」、「本源仅参考」。**

#### 3.3 `总交接文档-行内上线流程.md:52`

```
│       └── jupyter/                     ← M3(jupyter 镜像)材料, 本次不用
```

同文件紧接一句：

> **本次只动 6 个 ⭐ 标注的路径, 其余为背景材料。**

**即：交付包在自己的目录说明里，就把 `jupyter/` 标成了「本次不用 / 背景材料」。**

### 事实 4 · 交付包里确实没有那三样【已核实】

对 `C:\Users\27404\Desktop\BOS\cubeStudio\cube312-prod-pack` 逐项查证：

| 材料 | 应有 | 实况 |
|---|---|---|
| `cube_studio_dataset-*.whl` | M3 材料 2 | ❌ 全包无此文件 |
| `labextension-dist` | M3 材料 3 | ❌ 全包无此文件 |
| `jupyter-requirements.txt` | M3 材料 1 | ❌ 全包无此文件 |
| `handover-docs/` | 交接文档目录 | ⚠️ **空目录**（0 个文件） |
| `myapp/static/jupyterlab-extension/` | 前端扩展位 | ⚠️ **只有一个空的 `src/` 子目录** |

包内 `offline-wheels/` 的完整清单（**只有 6 个，与 jupyter 无关**）：

```
decorator-5.3.1-py3-none-any.whl
docopt-0.6.2-py2.py3-none-any.whl
gssapi-1.9.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
hdfs-2.7.3-py3-none-any.whl
jieba-0.42.1-py3-none-any.whl
wtforms_json-0.3.5-py3-none-any.whl
```

`build/` 只有后端三件（`Dockerfile.backend-py312`、`requirements-final.txt`、`requirements-kerberos.txt`），
**没有任何 jupyter 镜像构建件**。

> 顺便把来源也钉一下：旧源确实随 `py312迁移交付包.zip` 发过去了 ——
> `fix/交接/jupyter/cube_studio_dataset/{__init__.py, setup.py}` 在该 zip 内（已核实）。
> **但同一个包的总交接文档，把 `jupyter/` 标为「本次不用」。**
> 所以现场装到旧源，来源可查；而**适配版从来没被做出来**，来源不可查 —— 因为不存在。

---

## 三、因果定位

把四段拼起来：

```
① 交付来源：包内只有 JL3 旧源（且文档标注「本次不用 / 旧版参考」）
        ↓
② 现场装配：装了旧源占位 —— pip 安装 + enable 成功
        ↓
③ 服务端：extension was successfully linked  ← 这层本来就该成功
        ↓
④ 渲染层：三处断点全部命中（window.jupyterlab 不存在 / outputTransform 注入失败 / @jupyterlab ^3.4.0）
        → 面板不出现
        ↓
⑤ 适配版（cube_studio_dataset-*.whl + labextension-dist）从未产出
```

**所以：**
- 「组件被去除了」——不成立。**它在镜像里，服务端还在跑。**
- 「交付物里有就能用」——不成立。**交付物里那两份，按文档定义就是"旧版参考源"，不是"适配版"。**
  真正能在 JL4 上跑的两份（whl + labextension-dist），**至今未交付**。

---

## 四、需要谁做什么

| 项 | 责任方 | 说明 |
|---|---|---|
| 产出 `cube_studio_dataset-*.whl` | 交接人（迁移线） | 按 JL4 API 适配后，行外构建（`fix/交接/jupyter/README.md` 「迁移线交付物」第 2 条） |
| 产出 `labextension-dist` | 交接人（迁移线） | 按 JL4 API 重建 + 行外预构建（同 README 第 3 条）；**必须带预构建产物，因为 M3 不装 node** |
| 产出 `jupyter-requirements.txt` | 交接人（迁移线） | 同 README 第 1 条 |
| 现场占位状态维持 | 装配同事 | 旧源装了不炸、服务端可用；渲染层等适配版 |

**当前状态一句话：M3 的三份材料（清单 + 适配版 wheel + 预构建前端包）是 M3 的硬前置，
它们在 `组装交接文档.md` M3 节和 `fix/交接/jupyter/README.md` 里都被列为「等交接人交付」，
至今未到 —— 这正是流程记录里反复反映的事项（见附录 B）。**

---

## 附录 A · 证据索引（可逐条复核）

| # | 论断 | 位置 |
|---|---|---|
| 1 | 源码自述「兼容 JupyterLab 3.x」 | `fix/交接/jupyter/cube_studio_dataset/__init__.py:5` |
| 2 | 源码仍用 JL3 的 `jupyter serverextension enable` 命令 | 同上 `:9` |
| 3 | 前端 JS 等 `window.jupyterlab` 全局 | 同上 `:26`、`:36` |
| 4 | server extension 用旧入口 `_jupyter_server_extension_paths` | 同上 `:195` |
| 5 | 加载函数签名 `_load_jupyter_server_extension(lab_app)` | 同上 `:207` |
| 6 | Tornado `outputTransform` 注入 + 自带的失败 warning | 同上 `:215`、`:221`、`:228`、**`:231`** |
| 7 | labextension 依赖 JL3 版 API | `fix/交接/jupyter/labextension/package.json:25`、`:26`、`:27` |
| 8 | labextension `main` 指向不存在的 `lib/`，且需 `tsc` | 同上 `:8`、`:11`、`:32`；目录实测无 `lib/` |
| 9 | M3 三份材料「等交接人交付」 | `fix/交接/文档/组装交接文档.md:130` 起（`fix/组装交接文档.md:148` 同文） |
| 10 | 边界「labextension 旧源只作参考，必须用迁移线交付的 4 版」 | 同上 M3 节末 |
| 11 | 材料目录自述「JupyterLab 3 api 旧版源 / 本源仅参考」 | `fix/交接/jupyter/README.md` 表格行 2 |
| 12 | 「迁移线交付物（同事等这些才能合流 M3）」三条 | 同上 |
| 13 | 交付包把 `jupyter/` 标为「本次不用」 | `cube312-prod-pack/总交接文档-行内上线流程.md:52` |
| 14 | tornado/jupyterlab 版本风险早在评估期标注 | `py312/Python312迁移评估报告.md:254` |
| 15 | 交付包内无三份材料 / `handover-docs` 空 | `cube312-prod-pack/` 实测（见事实 4 表） |

## 附录 B · 待补证的记录（需从流程记录调出）

以下两条出自流程记录与运行态，**本文件未能在仓库中定位，需你补齐后此材料即完整**：

1. **M3-9** —— 组装当天冒烟测试记录里「`outputTransform` 注入失败」的那条，及其编号/截图。
   （源码 `__init__.py:231` 的 warning 字符串与之对应，可互为印证）
2. **反馈清单第 7、8 条** —— 自 2026-09-08 起反复记录的反馈条目，含编号与提交时间，
   用于证明「这不是新问题，是持续未销项」。

> 补齐位置建议：紧接本文件，作为「附录 B-1 / B-2」正文引用即可，
> 转载给同事时无需改动前文任何论断。
