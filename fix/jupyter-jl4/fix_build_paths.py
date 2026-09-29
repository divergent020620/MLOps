#!/usr/bin/env python3
"""
把 jupyter-builder 在 Windows 上生成的 package.json 里的反斜杠路径规范成正斜杠。

★ 为什么必须做这一步（这是行外 Windows 构建专属的坑）：

  jupyter-builder 用 os.path.join 拼 `jupyterlab._build.load`，在 Windows 上得到
      "static\\remoteEntry.<hash>.js"
  而 JupyterLab 会把它拼成前端要 fetch 的 URL：
      /lab/extensions/<name>/static\\remoteEntry.<hash>.js

  Windows 上浏览器会把反斜杠当分隔符容忍掉，所以**行外怎么测都是好的**；
  部署到麒麟（Linux）后，反斜杠是合法 URL 字符而不是分隔符 →
  **404，面板白屏，而且前端控制台不一定报错**。

  对照：内置的 jupyterlab_pygments 是 "static/remoteEntry.<hash>.js"（正斜杠）。

用法（由 build_jupyter_ext.sh 自动调用）：
    python fix_build_paths.py <extension-dir>
    # 例：python fix_build_paths.py cube_studio_dataset/labextension

退出码：
    0  已规范 / 本来就正常
    1  找不到 package.json 或结构不对
"""

import json
import sys
from pathlib import Path

# 需要规范成正斜杠的键（点路径）
PATH_KEYS = [
    ("jupyterlab", "_build", "load"),
]


def _norm(value):
    """把 Windows 反斜杠路径转成正斜杠，并去掉可能的前导 ./"""
    if not isinstance(value, str):
        return value, False
    fixed = value.replace("\\", "/")
    if fixed.startswith("./"):
        fixed = fixed[2:]
    return fixed, fixed != value


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1

    ext_dir = Path(argv[1])
    pkg_json = ext_dir / "package.json"
    if not pkg_json.is_file():
        print(f"!! 找不到 {pkg_json}")
        return 1

    data = json.loads(pkg_json.read_text(encoding="utf-8"))
    changed = []

    for key_path in PATH_KEYS:
        node = data
        for k in key_path[:-1]:
            if not isinstance(node, dict) or k not in node:
                node = None
                break
            node = node[k]
        if not isinstance(node, dict):
            continue

        last = key_path[-1]
        if last not in node:
            continue

        old = node[last]
        new, did = _norm(old)
        if did:
            node[last] = new
            changed.append((".".join(key_path), old, new))

    if not changed:
        print(f"[fix_build_paths] {pkg_json.name}: 路径已规范，无需修改")
        return 0

    pkg_json.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[fix_build_paths] 已修正 {len(changed)} 处 Windows 反斜杠路径：")
    for name, old, new in changed:
        print(f"    {name}")
        print(f"      - {old}")
        print(f"      + {new}")
    print("[fix_build_paths] 提示：不改这一步，麒麟上扩展会 404 白屏")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
