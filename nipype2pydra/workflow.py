from importlib import import_module
from functools import cached_property
import inspect
from types import ModuleType
from pathlib import Path
import attrs


@attrs.define
class WorkflowConverter:
    """Specifies how the semi-automatic conversion from Nipype to Pydra should
    be performed

    Parameters
    ----------
    name: str
        name of the workflow to generate
    nipype_name: str, optional
        the name of the task in the nipype module, defaults to the output task_name
    nipype_module: str or ModuleType
        the nipype module or module path containing the Nipype interface
    output_module: str
        the output module to store the converted task into relative to the `pydra.tasks` package
    input_struct: tuple[str, type]
        a globally accessible structure containing inputs to the workflow, e.g. config.workflow.*
        tuple consists of the name of the input and the type of the input
    """

    name: str
    nipype_name: str
    nipype_module: ModuleType = attrs.field(
        converter=lambda m: import_module(m) if not isinstance(m, ModuleType) else m
    )
    output_module: str = attrs.field()
    input_struct: str = None
    inputnode: str = "inputnode"
    outputnode: str = "outputnode"
    nested_workflow_funcs: list[str] = None
    omit_nodes: list[str] = None

    @output_module.default
    def _output_module_default(self):
        return f"pydra.tasks.{self.nipype_module.__name__}"

    @cached_property
    def nipype_function(self):
        return getattr(self.nipype_module, self.nipype_name)

    @cached_property
    def generate(self, package_root: Path):
        """Generate the Pydra task module

        Parameters
        ----------
        package_root: str
            the root directory of the package to write the module to
        """

        output_module = package_root.joinpath(
            self.output_module.split(".")
        ).with_suffix(".py")
        output_module.parent.mkdir(parents=True, exist_ok=True)

        src = inspect.getsource(self.nipype_function)

        code_str = ""

        with open(output_module, "w") as f:
            f.write(code_str)
