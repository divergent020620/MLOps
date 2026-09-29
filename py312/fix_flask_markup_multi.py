# -*- coding: utf-8 -*-
# 多行 from flask import (... Markup ...) -> 移出 Markup/escape, 新增 from markupsafe import
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = list((root / "myapp").rglob("*.py"))
changed = []
for f in files:
    lines = f.read_text(encoding="utf-8").split("\n")
    out = []
    i = 0
    modified = False
    while i < len(lines):
        if re.match(r"^from flask import \($", lines[i]):
            j = i + 1
            while j < len(lines) and lines[j].strip() != ")":
                j += 1
            chunk = lines[i + 1 : j]
            moved = [l for l in chunk if l.strip().rstrip(",") in ("Markup", "escape")]
            if moved:
                newchunk = [l for l in chunk if l not in moved]
                if newchunk:
                    out.append(lines[i])
                    out.extend(newchunk)
                out.append(lines[j])
                # 在闭括号后补 markupsafe import
                out.append("")
                out.append(
                    "from markupsafe import " + ", ".join(l.strip().rstrip(",") for l in moved)
                )
                modified = True
                i = j + 1
                continue
        out.append(lines[i])
        i += 1
    if modified:
        f.write_text("\n".join(out), encoding="utf-8")
        changed.append(str(f.relative_to(root)))
for c in sorted(changed):
    print("MODIFIED", c)
print("total:", len(changed))
