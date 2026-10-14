"""
Compatibility alias for the package's former name.

Everything lives in ``pylibselenium``; this module imports it, re-exports its public names and
registers every ``pylibselenium.*`` module under ``pylibseleniummanagement.*`` in ``sys.modules``
so that ``from pylibseleniummanagement.driver.types import DROPDOWNTYPE`` and
``import pylibseleniummanagement.profile`` keep working. The module objects are shared, not copied.
"""
import importlib as _importlib
import sys as _sys

_REAL = "pylibselenium"
_SUBPACKAGES = ("driver", "dom", "performance", "profile", "logger")

_real = _importlib.import_module(_REAL)
for _sub in _SUBPACKAGES:
    _importlib.import_module(f"{_REAL}.{_sub}")
for _name, _module in list(_sys.modules.items()):
    if _name.startswith(_REAL + "."):
        _sys.modules[__name__ + _name[len(_REAL):]] = _module
for _sub in _SUBPACKAGES:
    globals()[_sub] = getattr(_real, _sub)

from pylibselenium import *  # noqa: E402,F401,F403
from pylibselenium import Logger  # noqa: E402,F401

__version__ = getattr(_real, "__version__", None)
