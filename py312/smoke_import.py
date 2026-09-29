# -*- coding: utf-8 -*-
# py3.12 全量 import 冒烟: 逐个 import myapp.* 模块, 收集失败清单
# 用法(容器内): PYTHONPATH=/home/myapp /home/myapp/py312/bin/python /repo/py312/smoke_import.py
import importlib
import pkgutil
import traceback
import sys

import myapp

fails = []
count = 0
for info in pkgutil.walk_packages(myapp.__path__, "myapp."):
    name = info.name
    if name.startswith("myapp.bin") or name.startswith("myapp.translations"):
        continue
    count += 1
    try:
        importlib.import_module(name)
    except BaseException as e:
        fails.append((name, e))
        print("FAIL: %s: %r" % (name, e))
        # traceback.print_exc()

print("=== modules tried: %d, failed: %d ===" % (count, len(fails)))
if len(fails) > 6:
    print("仅显示前6条, 其余同上模式")
sys.exit(1 if fails else 0)
