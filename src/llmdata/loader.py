"""Load an object from a dotted path such as 'pkg.mod:name'."""

from __future__ import annotations

import importlib
from typing import Any


def load_object(path: str) -> Any:
    module_name, _, attr = path.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "run")
