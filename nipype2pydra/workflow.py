from importlib import import_module
from functools import cached_property
import inspect
import re
import typing as ty
from types import ModuleType
from pathlib import Path
import attrs
from .utils import UsedSymbols, split_source_into_statements, extract_args


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
    input_struct: tuple[str, str], optional
        a globally accessible structure containing inputs to the workflow, e.g. config.workflow.*
        tuple consists of the name of the input and the type of the input
    inputnode : str, optional
        the name of the workflow's input node (to be mapped to lzin), by default 'inputnode'
    outputnode : str, optional
        the name of the workflow's output node (to be mapped to lzout), by default 'outputnode'
    potential_nested_workflows : list[str]
        The specs of potentially nested workflows functions that may be called within
        the workflow function
    omit_interfaces : list[str]
        the list of interfaces to be omitted from the workflow (e.g. DataGrabber)
    package_mappings : dict[str, str]
        packages that should be mapped to a new location (typically Nipype based deps
        such as niworkflows)
    other_mappings: dict[str, str]
        other name mappings between
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
    potential_nested_workflows: dict[str, dict] = attrs.field(factory=dict)
    omit_interfaces: list[str] = attrs.field(factory=list)
    package_mappings: dict[str, str] = attrs.field(factory=dict)
    other_mappings: dict[str, str] = attrs.field(factory=dict)
    workflow_variable: str = None

    @output_module.default
    def _output_module_default(self):
        return f"pydra.tasks.{self.nipype_module.__name__}"

    @input_struct.validator
    def input_struct_validator(self, _, value):
        permitted = ("dict", "class")
        if value[1] not in permitted:
            raise ValueError(
                "the second item in the input_struct arg names the type of structu and "
                f"must be one of {permitted}"
            )

    @cached_property
    def nipype_function(self):
        return getattr(self.nipype_module, self.nipype_name)

    @cached_property
    def generate(self, package_root: Path) -> ty.List[str]:
        """Generate the Pydra task module

        Parameters
        ----------
        package_root: str
            the root directory of the package to write the module to

        Returns
        -------
        UsedSymbols
            symbols that are defined within the same package as the workflow function
            that need to be converted too
        """

        output_module = package_root.joinpath(
            self.output_module.split(".")
        ).with_suffix(".py")
        output_module.parent.mkdir(parents=True, exist_ok=True)

        func_src = inspect.getsource(self.nipype_function)

        used = UsedSymbols.find(
            self.nipype_module, [func_src], collapse_intra_pkg=False
        )

        for orig, new in self.other_mappings.items():
            func_src = re.sub(r"\b" + orig + r"\b", new, func_src)

        # Determine the name of the workflow variable if not provided
        if self.workflow_variable is None:
            returns = set(re.findall(r"^\s+return (\w+)", func_src, flags=re.MULTILINE))
            if len(returns) > 1:
                raise RuntimeError(f"Ambiguous return statements {returns}")
            workflow_var = list(returns)[0]
        else:
            workflow_var = self.workflow_variable

        preamble, args, post = extract_args(func_src)

        postamble, body = func_src.split(post, 1)

        if self.input_struct:
            if self.input_struct[1] == "class":
                input_struct_re = re.compile(r"\b" + self.input_struct + r"\.(\w+)\b")
            elif self.input_struct[1] == "dict":
                input_struct_re = re.compile(
                    r"\b" + self.input_struct + r"\[(?:'|\")([^\]]+)(?:'|\")]"
                )
            else:
                assert False
            # Find all the inputs that have been used in the function
            used_inputs = sorted(set(input_struct_re.findall(func_src)))
            # Substitute the input struct with a variable of that name
            func_src = input_struct_re.sub("\1", func_src)
            # Insert the inputs that are used in the function body into the signature
        else:
            used_inputs = []

        args += used_inputs

        signature = preamble + ", ".join(args) + postamble
        statements = split_source_into_statements(body)

        code_str = ""

        with open(output_module, "w") as f:
            f.write(code_str)

        return used
