from .function import FunctionTaskConverter
from .shell_command import ShellCommandTaskConverter
from importlib import import_module
from .base import (
    InputsConverter,
    OutputsConverter,
    TestGenerator,
    DocTestGenerator,
)


def get_converter(nipype_module: str, nipype_name: str, **kwargs):
    """Loads the appropriate converter for the given nipype interface."""
    nipype_interface = getattr(import_module(nipype_module), nipype_name)

    if hasattr(nipype_interface, "_cmd"):
        from .shell_command import ShellCommandTaskConverter as Converter
    else:
        from .function import FunctionTaskConverter as Converter

    return Converter(nipype_module=nipype_module, nipype_name=nipype_name, **kwargs)


__all__ = [
    "FunctionTaskConverter",
    "ShellCommandTaskConverter",
    "InputsConverter",
    "OutputsConverter",
    "TestGenerator",
    "DocTestGenerator",
    "get_converter",
]
