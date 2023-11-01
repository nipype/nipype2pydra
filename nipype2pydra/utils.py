import traceback
import typing as ty
from types import ModuleType
import sys
import os
import inspect
from contextlib import contextmanager
from pathlib import Path
from fileformats.core import FileSet

try:
    from typing import GenericAlias
except ImportError:
    from typing import _GenericAlias as GenericAlias

from importlib import import_module


def load_class_or_func(location_str):
    module_str, name = location_str.split(':')
    module = import_module(module_str)
    return getattr(module, name)


def show_cli_trace(result):
    return "".join(traceback.format_exception(*result.exc_info))


def import_module_from_path(module_path: ty.Union[ModuleType, Path, str]) -> ModuleType:
    if isinstance(module_path, ModuleType) or module_path is None:
        return module_path
    module_path = Path(module_path).resolve()
    sys.path.insert(0, str(module_path.parent))
    try:
        return import_module(module_path.stem)
    finally:
        sys.path.pop(0)


@contextmanager
def set_cwd(path):
    """Sets the current working directory to `path` and back to original
    working directory on exit

    Parameters
    ----------
    path : str
        The file system path to set as the current working directory
    """
    pwd = os.getcwd()
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(pwd)


@contextmanager
def add_to_sys_path(path: Path):
    """Adds the given `path` to the Python system path and then reverts it back to the
    original value on exit

    Parameters
    ----------
    path : str
        The file system path to add to the system path
    """
    sys.path.insert(0, str(path))
    try:
        yield sys.path
    finally:
        sys.path.pop(0)


def is_fileset(tp: type):
    return (
        inspect.isclass(tp)
        and type(tp) is not GenericAlias
        and issubclass(tp, FileSet)
    )


def to_snake_case(name: str) -> str:
    """
    Converts a PascalCase string to a snake_case one
    """
    snake_str = ""

    # Loop through each character in the input string
    for i, char in enumerate(name):
        # If the current character is uppercase and it's not the first character or
        # followed by another uppercase character, add an underscore before it and
        # convert it to lowercase
        if (
            i > 0
            and (char.isupper() or char.isdigit())
            and (
                not (name[i - 1].isupper() or name[i - 1].isdigit())
                or ((i + 1) < len(name) and (name[i + 1].islower() or name[i + 1].islower()))
            )
        ):
            snake_str += "_"
            snake_str += char.lower()
        else:
            # Otherwise, just add the character as it is
            snake_str += char.lower()

    return snake_str
