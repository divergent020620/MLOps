# JupyterLab 4 数据集面板 —— 技术详解

> 把这次从「面板不显示」到「wheel 装完即生效」中间所有技术细节讲清楚。
> 配套代码：`fix/jupyter-jl4/`，交付包：`fix/jupyter-jl4-pack.tgz`

---

## 第一部分 · 为什么这件事突然变麻烦了

### 1.1 旧版是「Python 里塞 JS」，JL3 允许这么干

`fix/交接/jupyter/cube_studio_dataset/__init__.py` 干的事很朴素：

```python
def _load_jupyter_server_extension(lab_app):
    extra_js = PANEL_JS                     # ← 一大段 <script>...</script> 字符串
    class _InjectPanelJS(OutputTransform):
        def transform_first_chunk(self, status_code, headers, chunk, finishing):
            if b'</body>' in chunk:
                chunk = chunk.replace(b'</body>', js_bytes + b'\n</body>')
            return status_code, headers, chunk
    lab_app.web_app.add_transform(_InjectPanelJS())      # ← 往页面里插
```

思路：**用 Tornado 的 `OutputTransform` 在响应 HTML 的 `</body>` 前塞一段 `<script>`**，
这段 JS 再靠 `window.jupyterlab` 拿到 JupyterLab 的应用对象，往侧边栏挂 widget。

**在 JL3 上这确实能跑**，所以 `domestic-jupyter` 当年是好的。

### 1.2 JL4 把这条路堵死了两处

| 断点 | 具体 | 为什么 |
|---|---|---|
| **注入失败** | `add_transform` 在 jupyter_server 2.x 上抛异常 | JL4 配套的 jupyter_server 2.x 换了页面服务实现 |
| **拿不到 app** | `window.jupyterlab` 在 JL4 **不存在** | JL4 重构了前端，不再往 window 暴露全局 |

第二点是决定性的：**即使 JS 成功注入，它也没有任何办法拿到 JupyterLab 的 shell**，
所以 `shell.add(panel, 'left')` 这行永远执行不了。

### 1.3 JL4 的答案：扩展必须预编译

JL3 时代有两种扩展：
- **source extension**：源码放在 `share/jupyter/labextensions/<name>/`，启动时由 JL 统一 webpack 打包
- **prebuilt extension**：已编译好的包

JL4 **取消了 source 这条路**（也取消了 `jupyter lab build`）。
现在唯一形态是 **prebuilt / federated extension** —— 一个独立编译好的 webpack 产物。

```
JL3:  源码 → (容器内 npm + jupyter lab build) → 打进 JL 主 bundle
JL4:  源码 → (发布前 tsc + webpack) → 独立的 remoteEntry.js → 运行时按需加载
```

**这就是为什么必须行外编译**：编译从「运行时/构建时」挪到了「发布前」，
而 JL4 的规定就是发布者自己负责把编译做掉。

---

## 第二部分 · Module Federation 到底怎么回事

这是理解「为什么 bundle 只有 6.9KB」的关键。

### 2.1 每个扩展是一个 webpack "remote"

预构建扩展被编译成一个 **Module Federation remote**：

```
static/remoteEntry.9ed04956ef4517a6ee99.js   ← remote 入口，暴露一个 container
static/968.4ccf7ba23c581292fb72.js           ← 代码分块
static/509.9758412eb8a54dcbdfec.js           ← 代码分块（我写的面板逻辑在这）
```

JupyterLab 主应用是 **host**，运行时通过 `_build.load` 指向的 remoteEntry 去**动态加载**这个扩展。

### 2.2 `sharedPackages` + `singleton` —— 关键设计

我的 `package.json` 里有：

```json
"jupyterlab": {
  "sharedPackages": {
    "@lumino/widgets": { "bundled": false, "singleton": true }
  }
}
```

含义：

| 字段 | 意思 | 不这么写会怎样 |
|---|---|---|
| `bundled: false` | **不要把 lumino/widgets 的代码打进我的 bundle**，运行时用宿主的 | 打进去会多 ~200KB，且和宿主两份 `Widget` 类 |
| `singleton: true` | 宿主和扩展必须**共用同一个实例** | 如果各有一份，`widgetA instanceof Widget` 会 false，挂载到 DOM 会炸 |

编译日志印证了这一点：

```
consume shared module (default) @jupyterlab/apputils@^4.7.3 (singleton) 42 bytes
consume shared module (default) @lumino/widgets@^2.3.1-alpha.1 (singleton) 42 bytes
```

**42 bytes** 就是那句"我要用你的那份"的声明 —— 一行引用代码，不是实现。
所以整个 bundle 才 6.9KB。

> 顺带：这也意味着**扩展和 JupyterLab 主版本的 API 必须兼容**。
> 我用 `@jupyterlab/* ^4.2` 编译，跑在 JL 4.6.3 上 —— 4.x 内小版本兼容。

---

## 第三部分 · ★ JL4 到底怎么"发现"一个扩展（决定 wheel 怎么打）

**这是这次最容易做错、且做错后毫无报错的一步。**

### 3.1 我第一版 wheel 就是错的

直觉上会这么想：

```python
# cube_studio_dataset/__init__.py
def _jupyter_labextension_paths():
    return [{"src": "labextension", "dest": "cube_studio_dataset"}]
```

看起来这是"告诉 Jupyter 我的扩展在哪"。**但 JL4 运行时根本不读这个函数。**

我在整个 site-packages 里搜过：

```
有多少地方引用 _jupyter_labextension_paths：
  jupyterlab/tests/...          ← 测试
  jupyter_builder/...           ← 构建工具（develop 模式用）
  jupyterlab_pygments/...       ← 另一个扩展自己声明
```

**jupyterlab 本体、jupyter_server 本体 —— 零引用。**

### 3.2 真正的发现机制

`jupyterlab_server/config.py:40`：

```python
def get_federated_extensions(labextensions_path: list[str]) -> dict[str, Any]:
    federated_extensions = {}
    for ext_dir in labextensions_path:
        # extensions are either top-level directories, or two-deep in @org directories
        for ext_path in chain(
            iglob(pjoin(ext_dir, "[!@]*", "package.json")),
            iglob(pjoin(ext_dir, "@*", "*", "package.json")),
        ):
            with open(ext_path, encoding="utf-8") as fid:
                pkgdata = json.load(fid)
            ...
```

**它就是扫目录**。而 `labextensions_path` 的实际取值：

```
C:\...\.venv\share\jupyter\labextensions           ← <sys.prefix>/share/jupyter/labextensions
C:\Users\...\AppData\Roaming\jupyter\labextensions ← 用户目录
```

（Linux 上就是 `/opt/nbenv/share/jupyter/labextensions`）

### 3.3 所以 wheel 必须这么打

`setup.py` 里必须用 **`data_files`**（不是 `package_data`）：

```python
LABEXT_DEST = os.path.join("share", "jupyter", "labextensions", EXT_NAME)

def _labextension_data_files():
    out = []
    for path in sorted(LABEXT_BUILT.rglob("*")):
        if not path.is_file():
            continue
        rel_parent = path.relative_to(LABEXT_BUILT).parent
        target = LABEXT_DEST if str(rel_parent) == "." else os.path.join(LABEXT_DEST, str(rel_parent))
        out.append((target, [str(path)]))
    return out

setup(
    ...
    package_data={...},                 # ← 这一份是备用的（自检 + JL3 兼容）
    data_files=_labextension_data_files(),   # ← ★ 这一份才是 JL4 认的
)
```

打出来的 wheel 里会多出一层 `.data/data/`：

```
cube_studio_dataset-2.0.0.data/data/share/jupyter/labextensions/cube-studio-dataset/
    ├── package.json
    ├── install.json
    ├── static/remoteEntry.9ed04956ef4517a6ee99.js
    └── schemas/...
cube_studio_dataset/                      ← 包里那份（备用）
    ├── __init__.py
    └── labextension/...
```

pip 会把 `.data/data/` 的内容铺到 `<venv>/share/jupyter/labextensions/` —— 正好是 3.2 扫的目录。

### 3.4 怎么验证（这条命令是判据）

```python
from jupyter_core.paths import jupyter_path
from jupyterlab_server.config import get_federated_extensions

exts = get_federated_extensions(jupyter_path('labextensions'))
print(list(exts.keys()))
# ['cube-studio-dataset', 'jupyterlab_pygments']   ← 内置 pygments 是已知正确的对照组
```

**这是唯一可靠的验收方式** —— 它调用的就是 JupyterLab 启动时用的那个函数。

---

## 第四部分 · 完整构建链（每一步在干什么）

```
labextension/src/index.ts          TypeScript 源码（我写的面板逻辑）
        │
        │ ① npm install             拉 @jupyterlab/* ^4、@lumino/widgets ^2
        ↓
   node_modules/
        │
        │ ② npx tsc                  类型检查 + 编译到 lib/
        ↓
   labextension/lib/index.js
        │
        │ ③ jupyter-builder build    用 webpack Module Federation 打包
        │                            （读 package.json 的 jupyterlab.outputDir 决定产物落点）
        ↓
   cube_studio_dataset/labextension/
   ├── package.json                  ← builder 重写过，加了 jupyterlab._build
   ├── static/remoteEntry.<hash>.js  ← ★ 核心产物
   └── schemas/
        │
        │ ④ fix_build_paths.py       把 Windows 反斜杠路径规范成正斜杠
        ↓
        │ ⑤ python -m build --wheel  用 setup.py 的 data_files 铺进 wheel
        ↓
   cube_studio_dataset-2.0.0-py3-none-any.whl
        │
        │ ⑥ 行内：pip install         ← 只有这一步在行内，且不需要 node
        ↓
   /opt/nbenv/share/jupyter/labextensions/cube-studio-dataset/
        │
        │ ⑦ JupyterLab 启动时 get_federated_extensions() 扫到它
        ↓
   侧边栏出现「数据集」
```

### 4.1 为什么 ② 和 ③ 是两步而不是一步

- `tsc` 负责 **TS → JS**（类型检查在这一步，语法/类型错误早暴露）
- `jupyter-builder build` 负责 **webpack 打包**（Module Federation 的 container 包装）

`package.json` 里 `"main": "lib/index.js"` 指向 ② 的产物，③ 再从这里打包。
所以两步顺序不能颠倒。

### 4.2 builder 重写 package.json 做了什么

对比我写的源文件和产物：

```jsonc
// 我写的（源）
"jupyterlab": {
  "extension": true,
  "outputDir": "../cube_studio_dataset/labextension",
  "sharedPackages": { "@lumino/widgets": { "bundled": false, "singleton": true } }
}

// builder 产出的（多了 _build）
"jupyterlab": {
  "extension": true,
  "outputDir": "...",
  "sharedPackages": {...},
  "_build": {
    "load": "static/remoteEntry.9ed04956ef4517a6ee99.js",   // ← 主应用去哪加载
    "extension": "./extension",                              // ← 暴露的模块名
    "style": "./style"                                       // ← 样式入口
  }
}
```

`_build.load` 就是**运行时那条下载路径** —— 也正是它被 Windows 写成反斜杠会致命。

---

## 第五部分 · 六个坑（这一节是精华）

### 坑 1 · `jupyter labextension build` 在 JL4.6 已经废弃且会崩

```bash
$ jupyter labextension build .
(Deprecated) 'jupyter labextension build' is deprecated, use 'jupyter-builder build' instead.
Traceback (most recent call last):
  ...
  File "jupyterlab/labextensions.py", line 467, in start
    sys.exit(subprocess.call(["jupyter-builder", "build"] + self._builder_args))
```

**对策**：直接用 `jupyter-builder build . --core-path <jupyterlab>/staging`。

> 这也是为什么文档里说"版本决定一切" —— JL 4.6 和 4.2 的行为就可能不同。

### 坑 2 · Windows 中文 locale 把 builder 读崩

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x94 in position 103
  File "jupyter_builder/federated_extensions.py", line 444
    ext_data = json.load(fid)
```

Python 在中文 Windows 上默认用 GBK 打开文件。我的 `package.json` 里有个 `—`（U+2014，UTF-8 是 `E2 80 94`），
`0x94` 就是它。

**对策**：① 全程 `PYTHONUTF8=1`；② `package.json` 的 description 改成纯 ASCII。

> `schema/plugin.json` 里的中文**不用改** —— 那是运行时由 JupyterLab 以 UTF-8 读的，不经过 Python 的 `json.load`。

### 坑 3 · ★ Windows 反斜杠 → 麒麟上 404 白屏

builder 用 `os.path.join` 生成路径，Windows 上得到：

```json
"load": "static\\remoteEntry.9ed04956ef4517a6ee99.js"     ← 反斜杠
```

对照内置的正确样例：

```json
// jupyterlab_pygments
"load": "static/remoteEntry.5cbb9d2323598fbda535.js"      ← 正斜杠
```

这个值被拼成前端 fetch 的 URL。**Windows 浏览器容忍反斜杠，所以行外怎么测都是好的；
麒麟（Linux）上反斜杠是合法 URL 字符、不是分隔符 → 404。**

而且失败方式很隐蔽：JS 加载失败，控制台**不一定**报错，表现得就是"面板不出现"。

**对策**：`fix_build_paths.py` 规范化 + 构建脚本里 `grep` 复验 + Dockerfile 断言里再查一次。三处兜底。

### 坑 4 · `_jupyter_labextension_paths()` 不是发现机制

已在第三部分详述。**做错的后果是：装得上、无报错、就是没面板。**
最难查的一类 bug，因为你所有的"日志"都是正常的。

**对策**：用 `get_federated_extensions()` 做验收，而不是看"pip install 成功"。

### 坑 5 · ★ 后端给的是 String，我按 number 写的

前端第一版：

```typescript
const rows = ds.entries_num ? ds.entries_num.toLocaleString() : '-';
```

但后端：

```python
# myapp/models/model_dataset.py:48
entries_num = Column(String(200), nullable=True, default='', comment='记录数目')
# myapp/tasks/hdfs_tasks.py:357
dataset.entries_num = str(total_rows) if total_rows else ''
```

**是字符串。** `"1000".toLocaleString` 是 `undefined` →
`TypeError: ds.entries_num.toLocaleString is not a function` →
整个 `_renderDatasets()` 抛出 → **面板白屏**。

**对策**：

```typescript
function formatCount(v: unknown): string {
  if (v === null || v === undefined || v === '') return '-';
  const n = Number(String(v).replace(/,/g, '').trim());
  return Number.isFinite(n) ? n.toLocaleString() : String(v);
}
```

> **教训**：前端对接后端时，**去读列定义**，别信接口文档或示例 JSON。
> 这种 bug 在"有数据"时才出现，空列表时测不出来。

### 坑 6 · `dataset_init.sh` 是个孤儿脚本

对照两个版本：

```dockerfile
# 参照版 install/docker/notebook-hdfs-build/Dockerfile:81
COPY dataset_init.sh /init.sh          ← dataset_init.sh 就是 /init.sh  ✅

# domestic-jupyter/Dockerfile.hdfs:68,80
COPY dataset_init.sh /init-dataset.sh   ← 放成了别的名字  ❌
COPY init.sh         /init.sh           ← /init.sh 是 SSH 那个
```

而平台只执行 `/init.sh`：

```python
# myapp/views/view_notebook.py:499
pre_command = '(nohup sh /init.sh > /notebook_init.log 2>&1 &) ; (nohup sh /mnt/%s/init.sh > /init.log 2>&1 &) ; '
```

**所以 `/init-dataset.sh` 从来没有被调用过** →
`/opt/dataset_helper.py` 从没被复制到 `/mnt/<user>/` →
notebook 里 `from dataset_helper import ...` **必然 ImportError**。

**对策**：把两个脚本合并成一个 `/init.sh`（SSH + 数据集目录 + helper 落地）。

---

## 第六部分 · 分层调试方法论

每一层一个**独立判据**。出问题时，从上往下逐层排除，不要跳。

| # | 层 | 判据 | 命令 |
|---|---|---|---|
| 1 | TS 编译 | 无类型错误 | `npx tsc --noEmit` |
| 2 | webpack | 消费的是 **JL4** 的共享模块 | 看 builder 日志里 `@jupyterlab/apputils@^4.x` |
| 3 | wheel 落位 | 有 `share/jupyter/labextensions/...` | `unzip -l xxx.whl \| grep labextensions` |
| 4 | **JL 发现** | ★ 名字出现在扩展列表 | `get_federated_extensions(jupyter_path('labextensions'))` |
| 5 | 加载路径 | `_build.load` **无反斜杠** | 见坑 3 |
| 6 | 数据接口 | 后端返回 `status: 0` | `curl -b <cookie> http://host/dataset_modelview/api/jupyter_list` |
| 7 | 渲染 | 浏览器里看到 Tab | 人眼 + Ctrl+Shift+R |

**第 4 层是最有价值的一层。** 它把"面板能不能显示"这个模糊问题，
变成了一个二值断言 —— 而且它用的就是 JupyterLab 自己的代码。

这也是为什么 Dockerfile 里那 6 条断言值得写：
**把运行时才发现的失败，提前到构建时。**

---

## 第七部分 · 文件职责清单

### 7.1 前端（`fix/jupyter-jl4/labextension/`）

| 文件 | 职责 | 关键点 |
|---|---|---|
| `package.json` | 依赖 + 打包配置 | `@jupyterlab/* ^4`、`@lumino/widgets ^2`；`outputDir` 决定产物落点；`sharedPackages.singleton` |
| `tsconfig.json` | TS 配置 | `target: ES2018`（JL4 浏览器基线） |
| `src/index.ts` | **面板实现** | `JupyterFrontEndPlugin` + `activate(app)`；**不碰 `window` 全局** |
| `style/base.css` | 样式 | 全用 `--jp-*` 变量 → 自动跟随亮/暗主题 |
| `schema/plugin.json` | 设置项 | `apiBase`（API 前缀）、`autoOpen`（是否自动开） |

### 7.2 Python 包（`fix/jupyter-jl4/cube_studio_dataset/`）

| 文件 | 职责 |
|---|---|
| `__init__.py` | `_jupyter_server_extension_points()`（JL4 新入口）+ `_jupyter_labextension_paths()`（兼容/develop 用）+ **已删除 OutputTransform**；`status()` 自检函数 |
| `labextension/` | 构建产物落点（脚本生成，不进 git） |

### 7.3 打包（`fix/jupyter-jl4/`）

| 文件 | 职责 |
|---|---|
| `setup.py` | ★ **`data_files` 铺到 `share/jupyter/labextensions/`** —— JL4 认的就是这份 |
| `pyproject.toml` | 只声明 `build-system`，**不写 `[project]`**（避免和 setup.py 元数据打架） |
| `MANIFEST.in` | sdist 内容 |
| `build_jupyter_ext.sh` | 七步一键构建 |
| `fix_build_paths.py` | 反斜杠规范化（坑 3） |
| `Dockerfile.notebook-p312` | 行内镜像 |
| `init.sh` | 容器启动初始化（合并版，修了坑 6） |

---

## 第八部分 · 如果你想改，改哪里会怎样

| 想做的事 | 改哪 | 注意 |
|---|---|---|
| 改面板外观 | `style/base.css` | 用 `--jp-*` 变量才能跟主题 |
| 改列表字段/交互 | `src/index.ts` 的 `_renderDatasets()` | **改前先去 `model_dataset.py` 确认字段类型**（坑 5） |
| 加一个功能按钮 | `src/index.ts` 的 `activate()` 里 `commands.addCommand` | 加完记得 `palette.addItem` 才能进命令面板 |
| 换 API 地址 | `schema/plugin.json` 的 `apiBase`，或运行时设 `window._cube_studio_api` | 默认同源相对路径 `/dataset_modelview/api` |
| 升级 JupyterLab | `package.json` 的 `@jupyterlab/*` + `jupyter-requirements.txt` | 两处**必须同步**，否则 Module Federation 版本不匹配 |
| 改面板版本号 | `labextension/package.json` 的 `version` **和** `cube_studio_dataset/__init__.py` 的 `__version__` | setup.py 有断言，不一致会**直接报错**（防止出现"幽灵扩展"） |

### 一条重要纪律

**改完必须重跑 `build_jupyter_ext.sh`。** 直接改 `cube_studio_dataset/labextension/` 里的产物是没用的 ——
那是脚本生成的，下次构建会被覆盖；而且 `data_files` 是从它复制的，改了也进不了 wheel。

---

## 附录 · 关键代码位置速查

| 内容 | 位置 |
|---|---|
| JL4 扩展发现逻辑 | `jupyterlab_server/config.py:40` `get_federated_extensions()` |
| `labextensions_path` 默认值 | `jupyter_core/paths.py` `jupyter_path('labextensions')` |
| `OutputTransform` 旧实现（已废） | `fix/交接/jupyter/cube_studio_dataset/__init__.py:215-231` |
| 数据集列表接口 | `myapp/views/view_dataset.py:683` `jupyter_list()` |
| 接口注册路径 | `myapp/views/view_dataset.py:805` `route_base = '/dataset_modelview/api'` |
| Dataset 字段类型 | `myapp/models/model_dataset.py:47-48`（`storage_size`/`entries_num` 都是 String） |
| 平台拉起 `/init.sh` | `myapp/views/view_notebook.py:499` 和 `:628` 的 `pre_command` |
| notebook 内读数据集 | `dataset_helper.py` → `pd.read_parquet('/mnt/<user>/datasets/<name>_<ver>/data.parquet')` |
| HDFS 下载（在**后端**） | `myapp/tasks/hdfs_tasks.py:28` `download_hdfs_dataset` |
