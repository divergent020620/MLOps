# -*- coding: utf-8 -*-
# py3.12 SyntaxWarning: 正则字符串字面量加 r 前缀(无效转义 \d \. \- 等)
# 安全规则:
#   - 只处理 re.compile/re.match/re.search/re.sub/re.findall/Regexp( 后第一个普通字符串
#   - 含字面 \\ 或正则语义敏感有效转义 \b 的串跳过并列出(人工复核)
# 用法: python fix_regex_escape.py /repo
import ast
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
INVALID = re.compile(r"\\[dDwWsSbS.\-+\-+()\[\]{}$|*?/^]")  # 无效/警告转义全集
SENSITIVE = re.compile(r"\\(b|a|v)")  # 正则语义敏感, 跳过
MEHTODS = ("re.compile", "re.match", "re.search", "re.sub", "re.findall", "Regexp")

changed = []
skipped = []
for f in (root / "myapp").rglob("*.py"):
    src = f.read_text(encoding="utf-8")
    lines = src.split("\n")
    out = []
    mod = False
    for ln in lines:
        for meth in MEHTODS:
            idx = ln.find(meth + "(")
            if idx == -1:
                continue
            rest = ln[idx + len(meth) + 1 :]
            m = re.match(r"\s*([rbfuRBFU]*)(['\"])", rest)
            if not m:
                continue
            prefix, quote = m.group(1), m.group(2)
            if "r" in prefix or "b" in prefix:
                continue
            # 取到匹配的字符串字面量(简化: 只匹配单行简单串)
            s = None
            for mm in re.finditer(r"([rbfuRBFU]*)(['\"])(.*?)\2", rest):
                if mm.start() == m.start():
                    s = mm.group(3)
                    break
            if s is None:
                continue
            if INVALID.search(s):
                if SENSITIVE.search(s):
                    skipped.append("%s:%s" % (f.relative_to(root), ln[:80]))
                else:
                    # 普通字符串 -> r 前缀; 若字符串含双引号内单引号等已含, 只加前缀
                    newln = ln[: idx + len(meth) + 1] + "r" + rest
                    ln = newln
                    mod = True
            break
        out.append(ln)
    if mod:
        f.write_text("\n".join(out), encoding="utf-8")
        changed.append(str(f.relative_to(root)))
print("MODIFIED files:", len(changed))
for c in sorted(changed):
    print("  ", c)
print("SKIPPED (需要人工, 含 \\b 等语义敏感):", len(skipped))
for s in skipped:
    print("  ", s)
