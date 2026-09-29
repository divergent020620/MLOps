"""
cube_studio_dataset — JupyterLab 4 数据集面板（打包脚本）

★ 关键设计：**本包不含任何构建步骤。**

前端 labextension 的 webpack 预构建产物（cube_studio_dataset/labextension/static/
remoteEntry*.js）在**行外**由 build_jupyter_ext.sh 生成，就躺在包目录里；
本 setup.py 只负责把它原样打进 wheel。效果：

  - 行内 pip install 时 **不需要 node / npm / gcc / 编译链**
  - 不需要 hatch-jupyter-builder 之类的构建后端
  - 装完即被 JupyterLab 4 识别，**不需要** `jupyter labextension install`

★★ 为什么必须写 data_files（这是最容易做错的一步）★★
  JupyterLab 4 **运行时并不读** `_jupyter_labextension_paths()`。
  它扫的是 jupyter_path('labextensions') 下的目录：
      <sys.prefix>/share/jupyter/labextensions/<dir>/package.json
  实现见 jupyterlab_server/config.py:40-48 get_federated_extensions()：
      iglob(pjoin(ext_dir, "[!@]*", "package.json"))
  所以 wheel **必须**把构建产物装到 share/jupyter/labextensions/<name>/，
  否则装完面板不会出现 —— 这正是本次要根除的失败模式。

布局：
    fix/jupyter-jl4/                 ← 本文件所在（构建根）
    ├── setup.py  MANIFEST.in  pyproject.toml
    ├── cube_studio_dataset/         ← Python 包
    │   ├── __init__.py
    │   └── labextension/            ← 构建产物落点（package.json + static/ + schemas/）
    └── labextension/                ← TS 源码（**不进 wheel**）

构建（行外）：
    bash fix/jupyter-jl4/build_jupyter_ext.sh
"""

import json
import os
from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).parent
PKG = HERE / "cube_studio_dataset"
LABEXT_BUILT = PKG / "labextension"          # 构建产物（jupyter-builder 的 outputDir）

# ── 版本 / 扩展名：从构建产物读，保证与前端一致 ────────────────────────────
MANIFEST_JSON = LABEXT_BUILT / "package.json"
if not MANIFEST_JSON.is_file():
    raise SystemExit(
        "!! 找不到构建产物：\n"
        f"   {MANIFEST_JSON}\n"
        "   请先在行外执行：bash fix/jupyter-jl4/build_jupyter_ext.sh"
    )

_meta = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
EXT_NAME = _meta["name"]            # 例：cube-studio-dataset
VERSION = _meta["version"]

VERSION_PY = "2.0.0"
for line in (PKG / "__init__.py").read_text(encoding="utf-8").splitlines():
    if line.startswith("__version__"):
        VERSION_PY = line.split("=", 1)[1].strip().strip("\"'")
        break
if VERSION_PY != VERSION:
    raise SystemExit(
        f"!! 版本不一致：__init__.py={VERSION_PY}  package.json={VERSION}\n"
        "   两处必须相同，否则 JupyterLab 缓存会出现幽灵扩展"
    )

# ── 自检：没有 remoteEntry 就别出包 ────────────────────────────────────────
_remote = sorted((LABEXT_BUILT / "static").glob("remoteEntry*.js")) if (LABEXT_BUILT / "static").is_dir() else []
if not _remote:
    raise SystemExit(
        "!! 缺少前端预构建产物：\n"
        f"   {LABEXT_BUILT}/static/remoteEntry*.js\n"
        "   请先在行外执行：bash fix/jupyter-jl4/build_jupyter_ext.sh"
    )

# ── data_files：把构建产物铺到 <prefix>/share/jupyter/labextensions/<name>/ ──
# JupyterLab 4 就是在这儿找扩展的（见文件头说明）。
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


# install.json：JupyterLab 用它显示扩展来源（可选，但列目录时好看）
_INSTALL_JSON = LABEXT_BUILT / "install.json"


def _write_install_json():
    if _INSTALL_JSON.is_file():
        return
    _INSTALL_JSON.write_text(
        json.dumps(
            {
                "packageManager": "python",
                "packageName": "cube_studio_dataset",
                "uninstallInstructions": (
                    "pip uninstall cube_studio_dataset，然后重启 JupyterLab"
                ),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


_write_install_json()

README = (HERE / "README.md").read_text(encoding="utf-8") if (HERE / "README.md").is_file() else ""

setup(
    name="cube_studio_dataset",
    version=VERSION,
    description=(
        "Cube Studio Dataset Panel for JupyterLab 4 - "
        "browse and load HDFS datasets in the sidebar"
    ),
    long_description=README,
    long_description_content_type="text/markdown",
    license="Apache-2.0",
    python_requires=">=3.8",
    packages=find_packages(include=["cube_studio_dataset", "cube_studio_dataset.*"]),
    # ① 包里也存一份：供 __init__.status() 自检 + JL3 时代 _jupyter_labextension_paths 兼容
    package_data={
        "cube_studio_dataset": [
            "labextension/package.json",
            "labextension/install.json",
            "labextension/static/*",
            "labextension/schemas/*/*",
        ]
    },
    include_package_data=False,
    zip_safe=False,
    # ② ★ 真正让 JupyterLab 4 认到的那一份
    data_files=_labextension_data_files(),
    # 刻意留空：纯前端 + 一个服务端空壳，不强制拉起 jupyterlab 版本，
    # 由 jupyter-requirements.txt 统一钉
    install_requires=[],
    classifiers=[
        "Framework :: Jupyter",
        "Framework :: Jupyter :: JupyterLab",
        "Framework :: Jupyter :: JupyterLab :: 4",
        "Framework :: Jupyter :: JupyterLab :: Extensions",
        "Framework :: Jupyter :: JupyterLab :: Extensions :: Prebuilt",
        "Programming Language :: Python :: 3",
    ],
)
