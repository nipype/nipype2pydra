import traceback
from types import ModuleType
import sys
from pathlib import Path
from importlib import import_module


def load_class_or_func(location_str):
    module_str, name = location_str.split(':')
    module = import_module(module_str)
    return getattr(module, name)


def show_cli_trace(result):
    return "".join(traceback.format_exception(*result.exc_info))


def import_module_from_path(module_path: Path) -> ModuleType:
    if isinstance(module_path, ModuleType) or module_path is None:
        return module_path
    module_path = Path(module_path).resolve()
    sys.path.insert(0, str(module_path.parent))
    try:
        return import_module(module_path.stem)
    finally:
        sys.path.pop(0)
