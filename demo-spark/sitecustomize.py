# sitecustomize.py — 在 Python 启动时自动执行，早于任何 pyspark 导入
# 修复 Python 3.8 + Spark 2.4 cloudpickle 不兼容问题
import types as _types

_orig_CodeType = _types.CodeType


def _patched_CodeType(*args, **kwargs):
    # Python 3.8 新增 posonlyargcount（第2个参数），3.7 的 cloudpickle 没传
    # 旧调用 15 个参数 → 在位置1插入 posonlyargcount=0
    if len(args) == 15:
        args = list(args)
        args.insert(1, 0)
    return _orig_CodeType(*args, **kwargs)


_types.CodeType = _patched_CodeType
