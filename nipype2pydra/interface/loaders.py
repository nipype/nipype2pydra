from importlib import import_module


def get_converter(nipype_module: str, nipype_name: str, **kwargs):
    """Loads the appropriate converter for the given nipype interface."""
    nipype_interface = getattr(import_module(nipype_module), nipype_name)

    if hasattr(nipype_interface, "_cmd"):
        from .shell_command import ShellCommandInterfaceConverter as Converter
    else:
        from .function import FunctionInterfaceConverter as Converter

    return Converter(nipype_module=nipype_module, nipype_name=nipype_name, **kwargs)
