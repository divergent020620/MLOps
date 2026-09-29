# -*- coding: utf-8 -*-
# Flask 3.x 批量迁移: from flask import Markup/escape -> from markupsafe import Markup/escape
# 用法: 在容器内 python /repo/py312/fix_flask_markup.py /repo
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
moved_names = ("Markup", "escape")
changed = []

files = list((root / "myapp").rglob("*.py"))
for extra in ("proxy.py", "app.py"):
    p = root / extra
    if p.exists():
        files.append(p)

for f in files:
    s = f.read_text(encoding="utf-8")
    lines = s.split("\n")
    out = []
    modified = False
    for ln in lines:
        m = re.match(r"^from flask import (.+)$", ln)
        if m:
            names = [n.strip() for n in m.group(1).split(",") if n.strip()]
            moved = [n for n in names if n in moved_names]
            if moved:
                rest = [n for n in names if n not in moved]
                if rest:
                    out.append("from flask import " + ", ".join(rest))
                out.append("from markupsafe import " + ", ".join(moved))
                modified = True
                continue
        out.append(ln)
    if modified:
        f.write_text("\n".join(out), encoding="utf-8")
        changed.append(str(f.relative_to(root)))

for c in sorted(changed):
    print("MODIFIED", c)
print("total:", len(changed))
