import traceback
from importlib import import_module


def load_class_or_func(location_str):
    module_str, name = location_str.split(':')
    module = import_module(module_str)
    return getattr(module, name)


def show_cli_trace(result):
    return "".join(traceback.format_exception(*result.exc_info))
