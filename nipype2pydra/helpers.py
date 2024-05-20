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
    full_address,
    multiline_comment,
    split_source_into_statements,
    replace_undefined,
)
from .statements import (
    ImportStatement,
    CommentStatement,
    DocStringStatement,
    parse_imports,
    ReturnStatement,
    ExplicitImport,
    from_list_to_imports,
)
import nipype2pydra.package
import nipype2pydra.interface
from typing_extensions import Self

logger = logging.getLogger(__name__)

if ty.TYPE_CHECKING:
    from nipype2pydra.package import PackageConverter


@attrs.define(slots=False)
class BaseHelperConverter:
    """Specifies how the semi-automatic conversion from Nipype to Pydra should
    be performed for generic functions that may be part of function interfaces or
    build and return Nipype nodes

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
    imports: ty.List[ExplicitImport] = attrs.field(
        factory=list,
        converter=from_list_to_imports,
        metadata={
            "help": """list import statements required by the test, with each list item
                consisting of 'module', 'name', and optionally 'alias' keys"""
        },
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

    @cached_property
    def src(self):
        return inspect.getsource(self.nipype_object)

    @property
    def full_name(self):
        return f"{self.nipype_module_name}.{self.nipype_name}"

    @cached_property
    def nipype_object(self):
        return getattr(self.nipype_module, self.nipype_name)

    @cached_property
    def used_symbols(self) -> UsedSymbols:
        used = UsedSymbols.find(
            self.nipype_module,
            [self.src],
            collapse_intra_pkg=False,
            omit_classes=self.package.omit_classes,
            omit_modules=self.package.omit_modules,
            omit_functions=self.package.omit_functions,
            omit_constants=self.package.omit_constants,
            always_include=self.package.all_explicit,
            translations=self.package.all_import_translations,
        )
        used.imports.update(i.to_statement() for i in self.imports)
        return used

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

    @classmethod
    def default_spec(
        cls, name: str, nipype_module: str, defaults: ty.Dict[str, ty.Any]
    ) -> str:
        """Generates a spec for the workflow converter from the given function"""
        conv = cls(
            name=name,
            nipype_name=name,
            nipype_module=nipype_module,
            **{n: eval(v) for n, v in defaults},
        )
        dct = attrs.asdict(conv)
        dct["nipype_module"] = dct["nipype_module"].__name__
        del dct["package"]
        for k in dct:
            if not dct[k]:
                dct[k] = None
        yaml_str = yaml.dump(dct, sort_keys=False)
        for k in dct:
            fld = getattr(attrs.fields(cls), k)
            hlp = fld.metadata.get("help")
            if hlp:
                yaml_str = re.sub(
                    r"^(" + k + r"):",
                    multiline_comment(hlp) + r"\1:",
                    yaml_str,
                    flags=re.MULTILINE,
                )
        return yaml_str

    @classmethod
    def from_object(cls, func_or_class, package_converter: "PackageConverter") -> Self:
        return cls(
            name=func_or_class.__name__,
            nipype_name=func_or_class.__name__,
            nipype_module=func_or_class.__module__,
            package=package_converter,
        )

    def _parse_statements(self, func_body: str) -> ty.List[
        ty.Union[
            str,
            ImportStatement,
            DocStringStatement,
            CommentStatement,
        ]
    ]:
        """Parses the statements in the function body into converter objects and strings
        also populates the `self.nodes` attribute

        Parameters
        ----------
        func_body : str
            the function body to parse

        Returns
        -------
        parsed : list[str | NodeConverter | ImportStatement | AddNodeStatement | ConnectionStatement | AddNestedWorkflowStatement | NodeAssignmentStatement | WorkflowInitStatement | DocStringStatement | CommentStatement | ReturnStatement]
            the parsed statements
        workflow_init : WorkflowInitStatement
            the workflow init statement
        """

        statements = split_source_into_statements(func_body)

        parsed = []
        for i, statement in enumerate(statements):
            if not statement.strip():
                continue
            if CommentStatement.matches(statement):  # comments
                parsed.append(CommentStatement.parse(statement))
            elif DocStringStatement.matches(statement):  # docstrings
                parsed.append(DocStringStatement.parse(statement))
            elif ImportStatement.matches(statement):
                parsed.extend(
                    parse_imports(
                        statement,
                        relative_to=self.nipype_module.__name__,
                        translations=self.package.all_import_translations,
                    )
                )
            elif ReturnStatement.matches(statement):
                parsed.append(ReturnStatement.parse(statement))
            else:  # A statement we don't need to parse in a special way so leave as string
                parsed.append(statement)

        return parsed

    def _convert_function(self, func_src: str) -> ty.Tuple[str, ty.List[str]]:
        """
        Convert the function source code to a Pydra function

        Parameters
        ----------
        func_src : str
            the source code of the function to convert

        Returns
        -------
        str
            the converted function code
        used_configs : list[str]
            the names of the used configs
        """

        func_src = replace_undefined(func_src)
        declaration, func_args, post = extract_args(func_src)
        return_types, func_body = post[1:].split(
            ":", 1
        )  # Get the return type and function body

        # Parse the statements in the function body into converter objects and strings
        parsed_statements = self._parse_statements(func_body)

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
        signature = declaration + ", ".join(func_args + config_sig) + ")"
        if return_types:
            signature += f"{return_types}"
        code_str = signature + ":\n\n" + preamble + code_str

        return code_str, used_configs


@attrs.define(slots=False)
class FunctionConverter(BaseHelperConverter):
    """Specifies how the semi-automatic conversion from Nipype to Pydra should
    be performed for generic functions that may be part of function interfaces or
    build and return Nipype nodes

    Parameters
    ----------
    name: str
        name of the workflow to generate
    nipype_name: str, optional
        the name of the task in the nipype module, defaults to the output task_name
    """

    @cached_property
    def func_body(self):
        preamble, args, post = extract_args(self.src)
        return post.split(":", 1)[1]

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
        code_str, used_configs = self._convert_function(self.src)

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


@attrs.define(slots=False)
class ClassConverter(BaseHelperConverter):
    """Specifies how the semi-automatic conversion from Nipype to Pydra should
    be performed for generic functions that may be part of function interfaces or
    build and return Nipype nodes

    Parameters
    ----------
    name: str
        name of the workflow to generate
    nipype_name: str, optional
        the name of the task in the nipype module, defaults to the output task_name
    """

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

        used_configs = set()
        parts = re.split(
            r"\n    (?!\s|\))", replace_undefined(self.src), flags=re.MULTILINE
        )
        converted_parts = []
        for part in parts:
            if part.startswith("def"):
                converted_func, func_used_configs = self._convert_function(part)
                converted_parts.append(converted_func)
                used_configs.update(func_used_configs)
            else:
                converted_parts.append(part)
        code_str = "\n    ".join(converted_parts)
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
