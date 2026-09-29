#!/bin/bash
# Wrapper: monkey-patch Python 3.8 types.CodeType for Spark 2.4 cloudpickle compatibility
exec python3.8 -c "
import types as _types
_orig = _types.CodeType
def _patched(*a, **kw):
    # Old cloudpickle calls with 15 args (3.7 style), new needs 16 (3.8+)
    if len(a) == 15:
        a = list(a); a.insert(1, 0)
    return _orig(*a, **kw)
_types.CodeType = _patched
import sys, runpy
sys.argv = sys.argv[1:] if len(sys.argv) > 1 else ['']
runpy.run_path(sys.argv[0], run_name='__main__')
" -- "$@"