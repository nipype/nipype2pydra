import logging
from functools import cached_property
import typing as ty
import re
import attrs
import inspect
from pathlib import Path
from importlib import import_module
from types import ModuleType
import black.report
import yaml
from .utils import (
    UsedSymbols,
    extract_args,
    ImportStatement,
    full_address,
    multiline_comment,
)
from .statements import (
    CommentStatement,
    DocStringStatement,
)
import nipype2pydra.package
import nipype2pydra.interface

logger = logging.getLogger(__name__)


@attrs.define
class NodeFactoryConverter:
    """Specifies how the semi-automatic conversion from Nipype to Pydra should
    be performed for functions that build and return Nipype nodes

    Parameters
    ----------
    name: str
        name of the workflow to generate
    nipype_name: str, optional
        the name of the task in the nipype module, defaults to the output task_name
    """

    name: str = attrs.field(
        metadata={
            "help": ("name of the converted workflow constructor function"),
        },
    )
    nipype_name: str = attrs.field(
        metadata={
            "help": ("name of the nipype workflow constructor"),
        },
    )
    nipype_module: ModuleType = attrs.field(
        converter=lambda m: import_module(m) if not isinstance(m, ModuleType) else m,
        metadata={
            "help": (
                "name of the nipype module the function is found within, "
                "e.g. mriqc.workflows.anatomical.base"
            ),
        },
    )
    interfaces: ty.Dict[str, nipype2pydra.interface.base.BaseInterfaceConverter] = (
        attrs.field(
            factory=dict,
            metadata={
                "help": (
                    "interface specifications for the tasks defined within the workflow package"
                ),
            },
        )
    )
    external_nested_interfaces: ty.List[str] = attrs.field(
        metadata={
            "help": (
                "the names of the nested interfaces that are defined in other modules "
                "and need to be imported"
            ),
        },
        converter=attrs.converters.default_if_none(factory=list),
        factory=list,
    )
    find_replace: ty.List[ty.Tuple[str, str]] = attrs.field(
        metadata={
            "help": (
                "a list of tuples where the first element is a regular expression to find "
                "in the code and the second element is the replacement string"
            ),
        },
        converter=attrs.converters.default_if_none(factory=list),
        factory=list,
    )
    package: "nipype2pydra.package.PackageConverter" = attrs.field(
        default=None,
        metadata={
            "help": ("the package converter that the workflow is associated with"),
        },
    )

    @property
    def nipype_module_name(self):
        return self.nipype_module.__name__

    @property
    def full_name(self):
        return f"{self.nipype_module_name}.{self.nipype_name}"

    @cached_property
    def func_src(self):
        return inspect.getsource(self.nipype_function)

    @cached_property
    def func_body(self):
        preamble, args, post = extract_args(self.func_src)
        return post.split(":", 1)[1]

    @cached_property
    def used_symbols(self) -> UsedSymbols:
        return UsedSymbols.find(
            self.nipype_module,
            [self.func_body],
            collapse_intra_pkg=False,
            omit_classes=self.package.omit_classes,
            omit_modules=self.package.omit_modules,
            omit_functions=self.package.omit_functions,
            omit_constants=self.package.omit_constants,
            translations=self.package.all_import_translations,
        )

    @cached_property
    def used_configs(self) -> ty.List[str]:
        return self._converted_code[1]

    @cached_property
    def converted_code(self) -> ty.List[str]:
        return self._converted_code[0]

    @cached_property
    def nested_interfaces(self):
        potential_classes = {
            full_address(c[1]): c[0]
            for c in self.used_symbols.intra_pkg_classes
            if c[0]
        }
        potential_classes.update(
            (full_address(c), c.__name__) for c in self.used_symbols.local_classes
        )
        return {
            potential_classes[address]: workflow
            for address, workflow in self.package.workflows.items()
            if address in potential_classes
        }

    @cached_property
    def nested_interface_symbols(self) -> ty.List[str]:
        """Returns the symbols that are used in the body of the workflow that are also
        workflows"""
        return list(self.nested_interfaces) + self.external_nested_interfaces

    @cached_property
    def _converted_code(self) -> ty.Tuple[str, ty.List[str]]:
        """Convert the Nipype workflow function to a Pydra workflow function and determine
        the configuration parameters that are used

        Returns
        -------
        function_code : str
            the converted function code
        used_configs : list[str]
            the names of the used configs
        """

        declaration, func_args, post = extract_args(self.func_src)
        return_types = post[1:].split(":", 1)[0]  # Get the return type

        # Parse the statements in the function body into converter objects and strings
        parsed_statements, workflow_name = self._parse_statements(self.func_body)

        preamble = ""
        # Write out the preamble (e.g. docstring, comments, etc..)
        while parsed_statements and isinstance(
            parsed_statements[0],
            (DocStringStatement, CommentStatement, ImportStatement),
        ):
            preamble += str(parsed_statements.pop(0)) + "\n"

        # Write out the statements to the code string
        code_str = ""
        for statement in parsed_statements:
            code_str += str(statement) + "\n"

        code_str, config_sig, used_configs = (
            self.package.find_and_replace_config_params(code_str)
        )

        # construct code string with modified signature
        signature = declaration + ", ".join(sorted(func_args + config_sig)) + ")"
        if return_types:
            signature += f" -> {return_types}"
        code_str = signature + ":\n\n" + preamble + code_str

        # Format the the code before the find and replace so it is more predictable
        try:
            code_str = black.format_file_contents(
                code_str, fast=False, mode=black.FileMode()
            )
        except black.report.NothingChanged:
            pass
        except Exception as e:
            # Write to file for debugging
            debug_file = "~/unparsable-nipype2pydra-output.py"
            with open(Path(debug_file).expanduser(), "w") as f:
                f.write(code_str)
            raise RuntimeError(
                f"Black could not parse generated code (written to {debug_file}): "
                f"{e}\n\n{code_str}"
            )

        for find, replace in self.find_replace:
            code_str = re.sub(find, replace, code_str, flags=re.MULTILINE | re.DOTALL)

        return code_str, used_configs

    @classmethod
    def default_spec(
        cls, name: str, nipype_module: str, defaults: ty.Dict[str, ty.Any]
    ) -> str:
        """Generates a spec for the workflow converter from the given function"""
        conv = NodeFactoryConverter(
            name=name,
            nipype_name=name,
            nipype_module=nipype_module,
            input_nodes={"inputnode": ""},
            output_nodes={"outputnode": ""},
            **{n: eval(v) for n, v in defaults},
        )
        dct = attrs.asdict(conv)
        dct["nipype_module"] = dct["nipype_module"].__name__
        del dct["package"]
        del dct["nodes"]
        for k in dct:
            if not dct[k]:
                dct[k] = None
        yaml_str = yaml.dump(dct, sort_keys=False)
        for k in dct:
            fld = getattr(attrs.fields(NodeFactoryConverter), k)
            hlp = fld.metadata.get("help")
            if hlp:
                yaml_str = re.sub(
                    r"^(" + k + r"):",
                    multiline_comment(hlp) + r"\1:",
                    yaml_str,
                    flags=re.MULTILINE,
                )
        return yaml_str
