# -*- coding: utf-8 -*-
"""discover 入口垫片（2026-11-06 实测）。

实测结论：`python -m unittest discover -s 工具 -p "test_*.py"` 在本机
Python 3.14.4 下**不会**递归进 工具/measure_sun_2026_11_06/——
用限定模式 `discover -s 工具 -p "test_sun_position.py"` 实测读数
`Ran 0 tests in 0.000s / NO TESTS RAN`（子目录无 __init__.py、非包，
3.14 的 unittest discovery 不再把非包目录加入检索）。
因此按任务预案增设本入口：把子目录里的实现与测试用文件路径方式
（importlib.util.spec_from_file_location）加载进来，并把 TestCase 类
绑定到本模块命名空间，使既有全量门禁命令原样收集到这 9 例。
判据本体全部在 工具/measure_sun_2026_11_06/ 下，本文件零逻辑。
"""
import importlib.util
import sys
from pathlib import Path

_SUB = Path(__file__).resolve().parent / "measure_sun_2026_11_06"


def _load(mod_name, filename):
    spec = importlib.util.spec_from_file_location(mod_name, _SUB / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module

# 先加载实现本体（与直接跑子目录测试时同一入口）
sun_position = _load("sun_position", "sun_position.py")
_tests = _load("sun_position_tests", "test_sun_position.py")

# 把子目录测试模块的 TestCase 类绑定进本命名空间，供 unittest 收集
for _name in dir(_tests):
    _obj = getattr(_tests, _name)
    if isinstance(_obj, type) and issubclass(_obj, __import__("unittest").TestCase):
        globals()[_name] = _obj
del _name, _obj
