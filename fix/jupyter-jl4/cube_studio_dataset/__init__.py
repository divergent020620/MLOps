"""
Cube Studio Dataset — JupyterLab 4.x 适配版

在 JupyterLab 侧边栏添加「数据集」面板，列出 Cube Studio 中已下载的 HDFS 数据集，
支持查看 schema 与一键复制加载代码。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
与 JL3 旧版的差异（这是本包存在的全部理由，逐条对应旧版的三处断点）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

旧版（fix/交接/jupyter/cube_studio_dataset）声明「兼容 JupyterLab 3.x」，
在 JL4 上有三处断点：

  断点 A  内联 JS 等 `window.jupyterlab` 全局 —— JL4 已不暴露该对象
  断点 B  `_jupyter_server_extension_paths()` + Tornado OutputTransform 注入
          —— 旧入口名，且 add_transform 在 JL4 上抛异常
  断点 C  前端 labextension 依赖 @jupyterlab/* ^3.4.0，且没有 lib/ 预构建产物

本版对应修法：

  A → 面板改为 labextension（前端扩展），由 JupyterFrontEndPlugin 的
      activate(app) 拿到 shell，完全不碰 window 全局
  B → 用 `_jupyter_server_extension_points()`（jupyter_server 2.x 新入口）；
      **彻底移除 OutputTransform 注入**
  C → 依赖升到 @jupyterlab/* ^4、@lumino/widgets ^2；
      前端预构建产物随本包一起分发（labextension/static/），装包即用，行内无需 node

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本模块自身不提供任何数据集 API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
数据全部来自 Cube Studio 后端：
    GET /dataset_modelview/api/jupyter_list
    （myapp/views/view_dataset.py:683 Dataset_ModelView_base.jupyter_list）

服务端这一层只做两件事：声明 labextension 路径 + 打一行日志。
"""

import json
import logging

__version__ = "2.0.0"

logger = logging.getLogger(__name__)

# ─── 前端扩展（本项目的主体） ──────────────────────────────────
#
# 返回的 dest 必须与 package.json 里 "jupyterlab.outputDir" 的落点、
# 以及构建产物 static/ 内的 remoteEntry 名称保持自洽。
# JupyterLab 会把它挂到 /lab/extensions/<dest>/ 下。

_HERE = __import__("pathlib").Path(__file__).parent
_LABEXT_DEST = "cube_studio_dataset"


def _jupyter_labextension_paths():
    """把随包分发的预构建前端扩展注册给 JupyterLab。"""
    return [{"src": "labextension", "dest": _LABEXT_DEST}]


# ─── 服务端扩展（仅日志，不做注入） ────────────────────────────


def _jupyter_server_extension_points():
    """
    jupyter_server 2.x（JupyterLab 4 配套）的新入口点。

    旧版用的是 `_jupyter_server_extension_paths()`，那是 jupyter_server 1.x 的名字，
    2.x 起已废弃。
    """
    return [{"module": "cube_studio_dataset"}]


def _jupyter_server_extension_paths():
    """
    jupyter_server 1.x 旧入口，保留以兼容尚未升级的环境。

    新环境走 `_jupyter_server_extension_points()`；两者同时存在不冲突。
    """
    return [{"module": "cube_studio_dataset"}]


def load_jupyter_server_extension(server_app):
    """
    jupyter_server 2.x 的加载函数名。

    刻意什么都不做（除日志）：面板的挂载完全由前端 labextension 负责。
    旧版在这里用 Tornado OutputTransform 往页面里塞 <script>，
    那正是 JL4 上 `OutputTransform 注入失败` 的来源，本版已移除。
    """
    _log_ready(server_app)


def _load_jupyter_server_extension(server_app):
    """jupyter_server 1.x 的加载函数名，转发到新版实现。"""
    load_jupyter_server_extension(server_app)


def _log_ready(server_app):
    log = getattr(server_app, "log", None) or logger
    try:
        labext_dir = _HERE / "labextension"
        static_dir = labext_dir / "static"
        remote_entries = (
            sorted(p.name for p in static_dir.glob("remoteEntry*.js"))
            if static_dir.is_dir()
            else []
        )
        if not remote_entries:
            log.warning(
                "[Cube Studio] 数据集扩展已加载，但未找到前端预构建产物 "
                "(%s/static/remoteEntry*.js)。面板不会出现 —— "
                "请确认安装的是带 labextension/static/ 的 wheel。",
                labext_dir,
            )
        else:
            log.info(
                "[Cube Studio] 数据集面板扩展 v%s 已加载（prebuilt: %s）",
                __version__,
                ", ".join(remote_entries),
            )
    except Exception as e:  # 日志失败绝不能影响 Jupyter 启动
        log.warning("[Cube Studio] 扩展自检异常: %s", e)


# ─── 便利函数：设置真值（供调试 / 自动化检查用） ────────────────


def status():
    """返回本扩展的安装自检结果字典，便于运维一行命令判断是否装好。"""
    static_dir = _HERE / "labextension" / "static"
    remote = (
        sorted(p.name for p in static_dir.glob("remoteEntry*.js"))
        if static_dir.is_dir()
        else []
    )
    pkg_json = _HERE / "labextension" / "package.json"
    meta = {}
    if pkg_json.is_file():
        try:
            meta = json.loads(pkg_json.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return {
        "version": __version__,
        "package": str(_HERE),
        "labextension_dir": str(_HERE / "labextension"),
        "prebuilt": bool(remote),
        "remote_entry": remote[0] if remote else None,
        "extension_name": meta.get("name"),
        "extension_version": meta.get("version"),
        "api_endpoint": "/dataset_modelview/api/jupyter_list",
    }


if __name__ == "__main__":
    print(json.dumps(status(), indent=2, ensure_ascii=False))
