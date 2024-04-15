from importlib import import_module
from functools import cached_property
import inspect
import re
import typing as ty
from operator import attrgetter
from copy import copy
import logging
from collections import defaultdict
from types import ModuleType
from pathlib import Path
import black.parsing
import attrs
from nipype.interfaces.base import BaseInterface
from .. import task
from ..utils import (
    UsedSymbols,
    split_source_into_statements,
    extract_args,
    cleanup_function_body,
    ImportStatement,
    parse_imports,
    to_snake_case,
)
from .components import (
    NodeConverter,
    ConnectionConverter,
    NestedWorkflowConverter,
    ConfigParamsConverter,
    CommentConverter,
    DocStringConverter,
    ReturnConverter,
    IterableConverter,
    DynamicField,
    NodeAssignmentConverter,
)

logger = logging.getLogger(__name__)


@attrs.define
class PackageConverter:
    """
    workflows : dict[str, WorkflowConverter]
        The specs of potentially nested workflows functions that may be called within
        the workflow function
    import_translations : list[tuple[str, str]]
        packages that should be mapped to a new location (typically Nipype based deps
        such as niworkflows). Regular expressions are supported
    """

    name: str = attrs.field(
        metadata={
            "help": ("name of the package to generate, e.g. pydra.tasks.mriqc"),
        },
    )
    nipype_name: str = attrs.field(
        metadata={
            "help": ("name of the nipype package to generate from (e.g. mriqc)"),
        },
    )
    config_params: ty.Dict[str, ConfigParamsConverter] = attrs.field(
        converter=lambda dct: {
            n: (
                ConfigParamsConverter(**c)
                if not isinstance(c, ConfigParamsConverter)
                else c
            )
            for n, c in dct.items()
        },
        factory=dict,
        metadata={
            "help": (
                "The name of the global struct/dict that contains workflow inputs "
                "that are to be converted to inputs of the function along with the type "
                'of the struct, either "dict" or "class"'
            ),
        },
    )
    workflows: ty.Dict[str, "WorkflowConverter"] = attrs.field(
        factory=dict,
        metadata={
            "help": (
                "workflow specifications of other workflow functions in the package, which "
                "could be potentially nested within the workflow"
            ),
        },
    )
    interfaces: ty.Dict[str, task.base.BaseTaskConverter] = attrs.field(
        factory=dict,
        metadata={
            "help": (
                "interface specifications for the tasks defined within the workflow package"
            ),
        },
    )
    import_translations: ty.List[ty.Tuple[str, str]] = attrs.field(
        factory=list,
        metadata={
            "help": (
                "Mappings between nipype packages and their pydra equivalents. Regular "
                "expressions are supported"
            ),
        },
    )

    def write(self, package_root: Path, workflows: ty.List[str] = None):
        """Writes the package to the specified package root"""

        if not workflows:
            workflows = list(self.workflows)

        already_converted = set()
        intra_pkg_modules = defaultdict(set)
        for workflow_name in workflows:
            self.workflows[workflow_name].write(
                package_root,
                already_converted=already_converted,
                intra_pkg_modules=intra_pkg_modules,
            )

        # Write any additional functions in other modules in the package
        self._write_intra_pkg_modules(
            package_root, intra_pkg_modules, self.import_translations
        )

    def translate_submodule(self, nipype_module_name: str) -> str:
        """Translates a module name from the Nipype package to the Pydra package"""
        relpath = ImportStatement.get_relative_package(
            nipype_module_name, self.nipype_name
        )
        if relpath == self.nipype_name:
            raise ValueError(
                f"Module {nipype_module_name} is not in the nipype package {self.nipype_name}"
            )
        return ImportStatement.join_relative_package(self.name + ".__init__", relpath)

    def untranslate_submodule(self, pydra_module_name: str) -> str:
        """Translates a module name from the Nipype package to the Pydra package"""
        relpath = ImportStatement.get_relative_package(pydra_module_name, self.name)
        if relpath == self.nipype_name:
            raise ValueError(
                f"Module {pydra_module_name} is not in the nipype package {self.name}"
            )
        return ImportStatement.join_relative_package(
            self.nipype_name + ".__init__", relpath
        )

    def _write_intra_pkg_modules(
        self,
        package_root: Path,
        intra_pkg_modules: ty.Dict[str, ty.Set[str]],
        translations: ty.List[ty.Tuple[str, str]],
    ):
        """Writes the intra-package modules to the package root

        Parameters
        ----------
        package_root : Path
            the root directory of the package to write the module to
        intra_pkg_modules : dict[str, set[str]
            the intra-package modules to write
        """
        for mod_name, objs in intra_pkg_modules.items():
            mod_path = package_root.joinpath(*mod_name.split("."))
            mod_path.parent.mkdir(parents=True, exist_ok=True)
            mod = import_module(self.untranslate_submodule(mod_name))

            interfaces = [
                o for o in objs if inspect.isclass(o) and issubclass(o, BaseInterface)
            ]
            other_objs = [o for o in objs if o not in interfaces]

            if interfaces:
                mod_path.mkdir(parents=True, exist_ok=True)
                for interface in interfaces:
                    task_converter = self.interfaces[interface.__name__]
                    task_converter.write(package_root)
                with open(mod_path.joinpath("__init__.py"), "w") as f:
                    f.write(
                        "\n".join(
                            f"from .{o.__name__} import {o.__name__}"
                            for o in interfaces
                        )
                    )
                    if other_objs:
                        f.write(
                            "\nfrom .other import ("
                            + ", ".join(o.__name__ for o in other_objs + ")")
                        )

            if other_objs:
                used = UsedSymbols.find(
                    mod,
                    other_objs,
                    pull_out_inline_imports=False,
                    translations=translations,
                )
                code_str = (
                    "\n".join(str(i) for i in used.imports if not i.indent) + "\n\n"
                )
                code_str += (
                    "\n".join(f"{n} = {d}" for n, d in sorted(used.constants)) + "\n\n"
                )
                code_str += "\n\n".join(
                    sorted(cleanup_function_body(inspect.getsource(f)) for f in objs)
                )
                for klass in sorted(used.local_classes, key=attrgetter("__name__")):
                    if klass not in objs:
                        code_str += "\n\n" + cleanup_function_body(
                            inspect.getsource(klass)
                        )
                for func in sorted(used.local_functions, key=attrgetter("__name__")):
                    if func not in objs:
                        code_str += "\n\n" + cleanup_function_body(
                            inspect.getsource(func)
                        )
                try:
                    code_str = black.format_file_contents(
                        code_str, fast=False, mode=black.FileMode()
                    )
                except Exception as e:
                    with open("/Users/tclose/Desktop/gen-code.py", "w") as f:
                        f.write(code_str)
                    raise RuntimeError(
                        f"Black could not parse generated code: {e}\n\n{code_str}"
                    )
                if interfaces:
                    # Write into package with __init__.py
                    with open(mod_path.joinpath("other").with_suffix(".py"), "w") as f:
                        f.write(code_str)
                else:
                    # Write as a standalone module
                    with open(mod_path.with_suffix(".py"), "w") as f:
                        f.write(code_str)


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
    config_params: tuple[str, str], optional
        a globally accessible structure containing inputs to the workflow, e.g. config.workflow.*
        tuple consists of the name of the input and the type of the input
    input_nodes : ty.Dict[str], optional
        the name of the workflow's input node (to be mapped to lzin), by default 'inputnode'
    output_nodes :  ty.Dict[str], optional
        the name of the workflow's output node (to be mapped to lzout), by default 'outputnode'
    find_replace: dict[str, str]
        Generic regular expression substitutions to be run over the code before
        it is processed
    workflow_variable: str, optional
        the variable name that the workflow function returns, by default detected from the
        return statement. If multiple return statements are found, this must be specified
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
    input_nodes: ty.Dict[str, str] = attrs.field(
        converter=dict,
        metadata={
            "help": (
                "Name of the node that is to be considered the input of the workflow, "
                "i.e. its outputs will be the inputs of the workflow"
            ),
        },
    )
    output_nodes: ty.Dict[str, str] = attrs.field(
        converter=dict,
        metadata={
            "help": (
                "Name of the node that is to be considered the output of the workflow, "
                "i.e. its inputs will be the outputs of the workflow"
            ),
        },
    )
    find_replace: ty.List[ty.Tuple[str, str]] = attrs.field(
        factory=list,
        metadata={
            "help": (
                "Generic regular expression substitutions to be run over the code before "
                "it is processed"
            ),
        },
    )
    workflow_variable: str = attrs.field(
        metadata={
            "help": ("name of the workflow variable that is returned"),
        },
    )
    package: PackageConverter = attrs.field(
        default=None,
        metadata={
            "help": ("the package converter that the workflow is associated with"),
        },
    )
    external_nested_workflows: ty.List[str] = attrs.field(
        metadata={
            "help": (
                "the names of the nested workflows that are defined in other modules "
                "and need to be imported"
            ),
        },
        factory=list,
    )

    nodes: ty.Dict[str, ty.List[NodeConverter]] = attrs.field(factory=dict)

    @nipype_module.validator
    def _nipype_module_validator(self, _, value):
        if not self.nipype_module_name.startswith(self.package.nipype_name + "."):
            raise ValueError(
                f"Workflow {self.name} is not in the nipype package {self.package.nipype_name}"
            )

    @property
    def output_module(self):
        return self.package.translate_submodule(self.nipype_module_name)

    def get_output_module_path(self, package_root: Path):
        output_module_path = package_root.joinpath(
            *self.output_module.split(".")
        ).with_suffix(".py")
        output_module_path.parent.mkdir(parents=True, exist_ok=True)
        return output_module_path

    @workflow_variable.default
    def workflow_variable_default(self):
        returns = set(
            re.findall(r"^    return (\w+)", self.func_body, flags=re.MULTILINE)
        )
        if not returns:
            return None
        if len(returns) > 1:
            raise RuntimeError(
                f"Ambiguous return statements {returns}, please specify explicitly"
            )
        return list(returns)[0]

    @cached_property
    def nipype_function(self) -> ty.Callable:
        func = getattr(self.nipype_module, self.nipype_name)
        if not inspect.isfunction(func):
            raise ValueError(
                f"Could not find function {self.nipype_name} in module {self.nipype_module}, found "
                f"{self.nipype_name}=={func} instead"
            )
        return func

    @property
    def nipype_module_name(self):
        return self.nipype_module.__name__

    @property
    def full_name(self):
        return f"{self.nipype_module_name}.{self.nipype_name}"

    @cached_property
    def used_symbols(self) -> UsedSymbols:
        return UsedSymbols.find(
            self.nipype_module,
            [self.func_body],
            collapse_intra_pkg=False,
            translations=self.package.import_translations,
        )

    @cached_property
    def config_defaults(self) -> ty.Dict[str, ty.Dict[str, str]]:
        defaults = {}
        for name, config_params in self.package.config_params.items():
            params = config_params.module
            defaults[name] = {}
            for part in config_params.varname.split("."):
                params = getattr(params, part)
            if config_params.type == "struct":
                defaults[name] = {
                    a: getattr(params, a)
                    for a in dir(params)
                    if not inspect.isfunction(getattr(params, a))
                    and not a.startswith("_")
                }
            elif config_params.type == "dict":
                defaults[name] = copy(params)
            else:
                assert False, f"Unrecognised config_params type {config_params.type}"
        return defaults

    @cached_property
    def used_configs(self) -> ty.List[str]:
        return self._converted_code[1]

    @cached_property
    def converted_code(self) -> ty.List[str]:
        return self._converted_code[0]

    @cached_property
    def inline_imports(self) -> ty.List[str]:
        return [s for s in self.converted_code if isinstance(s, ImportStatement)]

    @cached_property
    def func_src(self):
        return inspect.getsource(self.nipype_function)

    @cached_property
    def func_body(self):
        preamble, args, post = extract_args(self.func_src)
        return post.split(":", 1)[1]

    @cached_property
    def nested_workflows(self):
        potential_funcs = [f[0] for f in self.used_symbols.intra_pkg_funcs] + [
            f.__name__ for f in self.used_symbols.local_functions
        ]
        return {
            name: workflow
            for name, workflow in self.package.workflows.items()
            if name in potential_funcs
        }

    def write(
        self,
        package_root: Path,
        already_converted: ty.Set[str] = None,
        additional_funcs: ty.List[str] = None,
        intra_pkg_modules: ty.Dict[str, ty.Set[str]] = None,
        nested: bool = False,
    ):
        """Generates and writes the converted package to the specified package root

        Parameters
        ----------
        package_root: str
            the root directory of the package to write the module to
        already_converted : set[str], optional
            names of the workflows that have already converted workflows
        additional_funcs : list[str], optional
            additional functions to write to the module required as dependencies of
            workflows in other modules
        """

        if already_converted is None:
            already_converted = set()
        if intra_pkg_modules is None:
            intra_pkg_modules = defaultdict(set)
        already_converted.add(self.full_name)

        if additional_funcs is None:
            additional_funcs = []

        used = UsedSymbols(
            imports=copy(self.used_symbols.imports),
            intra_pkg_classes=copy(self.used_symbols.intra_pkg_classes),
            intra_pkg_funcs=copy(self.used_symbols.intra_pkg_funcs),
            local_functions=copy(self.used_symbols.local_functions),
            local_classes=copy(self.used_symbols.local_classes),
            constants=copy(self.used_symbols.constants),
        )

        # Start writing output module with used imports and converted function body of
        # main workflow
        code_str = (
            "\n".join(str(i) for i in used.imports if not i.indent)
            + "\nimport pydra.task\n"
            + "from pydra.engine import Workflow\n\n"
        )
        code_str += self.converted_code

        # Get any intra-package classes and functions that need to be written

        for _, intra_pkg_obj in used.intra_pkg_classes + list(used.intra_pkg_funcs):
            intra_pkg_modules[self.to_output_module_path(intra_pkg_obj.__module__)].add(
                intra_pkg_obj
            )
        local_func_names = {f.__name__ for f in used.local_functions}

        # Convert any nested workflows
        for name, conv in self.nested_workflows.items():
            if conv.full_name in already_converted:
                continue
            already_converted.add(conv.full_name)
            if name in local_func_names:
                code_str += "\n\n\n" + conv.converted_code
                used.update(conv.used_symbols)
            else:
                conv.write(
                    package_root,
                    already_converted=already_converted,
                    additional_funcs=intra_pkg_modules[conv.output_module],
                )

        # Add any local functions, constants and classes
        for func in sorted(used.local_functions, key=attrgetter("__name__")):
            if func.__module__ + "." + func.__name__ not in already_converted:
                code_str += "\n\n" + cleanup_function_body(inspect.getsource(func))

        code_str += "\n".join(f"{n} = {d}" for n, d in used.constants)
        for klass in sorted(used.local_classes, key=attrgetter("__name__")):
            code_str += "\n\n" + cleanup_function_body(inspect.getsource(klass))

        # Format the generated code with black
        try:
            code_str = black.format_file_contents(
                code_str, fast=False, mode=black.FileMode()
            )
        except Exception as e:
            with open("/Users/tclose/Desktop/gen-code.py", "w") as f:
                f.write(code_str)
            raise RuntimeError(
                f"Black could not parse generated code: {e}\n\n{code_str}"
            )

        with open(self.get_output_module_path(package_root), "w") as f:
            f.write(code_str)

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

        preamble, func_args, post = extract_args(self.func_src)
        return_types = post[1:].split(":", 1)[0]  # Get the return type

        # Parse the statements in the function body into converter objects and strings
        parsed_statements, workflow_name = self._parse_statements(self.func_body)

        # Mark the nodes and connections that are to be included in the workflow, starting
        # from the designated input node (doesn't have to be the first node in the function body,
        # i.e. the input node can be after the data grabbing steps)
        missing = []
        input_spec = set()
        input_nodes = []
        for prefix, input_node_name in self.input_nodes.items():
            try:
                sibling_input_nodes = self.nodes[input_node_name]
            except KeyError:
                missing.append(input_node_name)
            else:
                for input_node in sibling_input_nodes:
                    for conn in input_node.out_conns:
                        conn.wf_in_out = "in"
                        src_out = (
                            conn.source_out
                            if not isinstance(conn.source_out, DynamicField)
                            else conn.source_out.varname
                        )
                        input_spec.add(src_out)
                    input_nodes.append(input_node)
        if missing:
            raise ValueError(
                f"Unrecognised input nodes {missing}, not in {list(self.nodes)} "
                f"for {self.full_name}"
            )

        # Walk through the DAG and include all nodes and connections that are connected to
        # the input nodes and their connections up until the output nodes
        included = []
        node_stack = copy(input_nodes)
        while node_stack:
            node = node_stack.pop()
            for conn in node.out_conns:
                conn.include = True
                if conn.target_name not in (
                    included
                    + list(self.input_nodes.values())
                    + list(self.output_nodes.values())
                ):
                    included.append(conn.target_name)
                    for tgt in conn.targets:
                        tgt.include = True
                        node_stack.append(tgt)

        missing = []
        for prefix, output_node_name in self.output_nodes.items():
            try:
                sibling_output_nodes = self.nodes[output_node_name]
            except KeyError:
                missing.append(output_node_name)
            else:
                for output_node in sibling_output_nodes:
                    for conn in output_node.in_conns:
                        conn.wf_in_out = "out"
        if missing:
            raise ValueError(
                f"Unrecognised output node {missing}, not in "
                f"{list(self.nodes)} for {self.full_name}"
            )

        code_str = ""
        # Write out the preamble (e.g. docstring, comments, etc..)
        while parsed_statements and isinstance(
            parsed_statements[0],
            (DocStringConverter, CommentConverter, ImportStatement),
        ):
            code_str += str(parsed_statements.pop(0)) + "\n"

        # Initialise the workflow object
        code_str += (
            f"    {self.workflow_variable} = Workflow("
            f'name={workflow_name}, input_spec=["'
            + '", "'.join(sorted(input_spec))
            + '"])\n\n'
        )

        # Write out the statements to the code string
        for statement in parsed_statements:
            code_str += str(statement) + "\n"

        used_configs = set()
        for config_name, config_param in self.package.config_params.items():
            if config_param.type == "dict":
                config_regex = re.compile(
                    r"\b" + config_name + r"\[(?:'|\")([^\]]+)(?:'|\")\]\b"
                )
            else:
                config_regex = re.compile(r"\b" + config_param.varname + r"\.(\w+)\b")
            used_configs.update(
                (config_name, m) for m in config_regex.findall(code_str)
            )
            code_str = config_regex.sub(config_name + r"_\1", code_str)

        for nested_workflow in self.nested_workflows.values():
            used_configs.update(nested_workflow.used_configs)

        config_sig = [
            f"{n}_{c}={self.config_defaults[n][c]!r}" for n, c in used_configs
        ]

        # construct code string with modified signature
        signature = preamble + ", ".join(sorted(func_args + config_sig)) + ")"
        if return_types:
            signature += f" -> {return_types}"
        code_str = signature + ":\n\n" + code_str

        if not isinstance(parsed_statements[-1], ReturnConverter):
            code_str += f"\n    return {self.workflow_variable}"

        return code_str, used_configs

    def _parse_statements(self, func_body: str) -> ty.Tuple[
        ty.List[
            ty.Union[str, NodeConverter, ConnectionConverter, NestedWorkflowConverter]
        ],
        str,
    ]:
        """Parses the statements in the function body into converter objects and strings
        also populates the `self.nodes` attribute

        Parameters
        ----------
        func_body : str
            the function body to parse

        Returns
        -------
        parsed : list[Union[str, NodeConverter, ConnectionConverter, NestedWorkflowConverter]]
            the parsed statements
        workflow_name : str
            the name of the workflow
        """

        statements = split_source_into_statements(func_body)

        parsed = []
        workflow_name = None
        for statement in statements:
            if not statement.strip():
                continue
            if match := re.match(r"^(\s*)#\s*(.*)", statement):  # comments
                parsed.append(
                    CommentConverter(comment=match.group(2), indent=match.group(1))
                )
            elif match := re.match(
                r"^(\s*)(?='|\")(.*)", statement, flags=re.MULTILINE | re.DOTALL
            ):  # docstrings
                parsed.append(
                    DocStringConverter(docstring=match.group(2), indent=match.group(1))
                )
            elif ImportStatement.matches(statement):
                parsed.extend(parse_imports(statement))
            elif match := re.match(
                r"\s+(?:"
                + self.workflow_variable
                + r")\s*=.*\bWorkflow\(.*name\s*=\s*([^,=\)]+)",
                statement,
                flags=re.MULTILINE,
            ):
                workflow_name = match.group(1)
            elif match := re.match(  # Nodes
                r"(\s+)(\w+)\s*=.*\b(Map)?Node\(", statement, flags=re.MULTILINE
            ):
                indent = match.group(1)
                varname = match.group(2)
                args = extract_args(statement)[1]
                node_kwargs = match_kwargs(args, NodeConverter.SIGNATURE)
                intf_name, intf_args, intf_post = extract_args(node_kwargs["interface"])
                if "iterables" in node_kwargs:
                    iterables = [
                        IterableConverter(*extract_args(a)[1])
                        for a in extract_args(node_kwargs["iterables"])[1]
                    ]
                else:
                    iterables = []

                splits = node_kwargs["iterfield"] if match.group(3) else None
                if intf_name.endswith("("):  # strip trailing parenthesis
                    intf_name = intf_name[:-1]
                node_converter = NodeConverter(
                    name=varname,
                    interface=intf_name,
                    args=intf_args,
                    iterables=iterables,
                    itersource=node_kwargs.get("itersource"),
                    splits=splits,
                    workflow_converter=self,
                    indent=indent,
                )
                if varname in self.nodes:
                    self.nodes[varname].append(node_converter)
                else:
                    self.nodes[varname] = [node_converter]
                parsed.append(node_converter)
            elif match := re.match(  #
                r"(\s+)(\w+) = ("
                + "|".join(list(self.nested_workflows) + self.external_nested_workflows)
                + r")\(",
                statement,
                flags=re.MULTILINE,
            ):
                indent, varname, wf_name = match.groups()
                nested_workflow_converter = NestedWorkflowConverter(
                    varname=varname,
                    workflow_name=wf_name,
                    nested_spec=self.nested_workflows.get(wf_name),
                    args=extract_args(statement)[1],
                    indent=indent,
                    workflow_converter=self,
                )
                if varname in self.nodes:
                    self.nodes[varname].append(nested_workflow_converter)
                else:
                    self.nodes[varname] = [nested_workflow_converter]
                parsed.append(nested_workflow_converter)

            elif match := re.match(
                r"(\s*)" + self.workflow_variable + r"\.connect\(",
                statement,
                flags=re.MULTILINE | re.DOTALL,
            ):
                indent = match.group(1)
                args = extract_args(statement)[1]
                if len(args) == 1:
                    conns = extract_args(args[0])[1]
                else:
                    conns = [args]
                for conn in conns:
                    src, tgt, field_conns_str = extract_args(conn)[1]
                    if (
                        field_conns_str.startswith("(")
                        and len(extract_args(field_conns_str)[1]) == 1
                    ):
                        field_conns_str = extract_args(field_conns_str)[1][0]
                    field_conns = extract_args(field_conns_str)[1]
                    for field_conn in field_conns:
                        out, in_ = extract_args(field_conn)[1]
                        pre, args, post = extract_args(out)
                        if args is not None:
                            out = DynamicField(*args)
                        conn_converter = ConnectionConverter(
                            source_name=src,
                            target_name=tgt,
                            source_out=out,
                            target_in=in_,
                            indent=indent,
                            workflow_converter=self,
                        )
                        try:
                            conn_converter.lzouttable
                        except AttributeError:
                            conn_converter.lzouttable
                        if not conn_converter.lzouttable:
                            parsed.append(conn_converter)
                        for src_node in self.nodes[src]:
                            src_node.out_conns.append(conn_converter)
                        for tgt_node in self.nodes[tgt]:
                            tgt_node.in_conns.append(conn_converter)
            elif match := re.match(r"(\s*)return (.*)", statement):
                parsed.append(
                    ReturnConverter(vars=match.group(2), indent=match.group(1))
                )
            else:
                # Match assignments to node attributes
                match = re.match(
                    r"(\s*)(" + "|".join(self.nodes) + r")\b([\w\.]+)\s*=\s*(.*)",
                    statement,
                    flags=re.MULTILINE | re.DOTALL,
                )
                if self.nodes and match:
                    parsed.append(
                        NodeAssignmentConverter(
                            nodes=self.nodes[match.group(2)],
                            attribute=match.group(3),
                            value=match.group(4),
                            indent=match.group(1),
                        )
                    )
                else:
                    parsed.append(statement)

        if workflow_name is None:
            raise ValueError(
                "Did not detect worklow name in statements:\n\n" + "\n".join(statements)
            )

        return parsed, workflow_name

    def to_output_module_path(self, nipype_module_path: str) -> str:
        """Converts an original Nipype module path to a Pydra module path

        Parameters
        ----------
        nipype_module_path : str
            the original Nipype module path

        Returns
        -------
        str
            the Pydra module path
        """
        return ImportStatement.join_relative_package(
            self.output_module,
            ImportStatement.get_relative_package(
                nipype_module_path, self.nipype_module
            ),
        )

    def from_output_module_path(self, pydra_module_path: str) -> str:
        """Converts an original Nipype module path to a Pydra module path

        Parameters
        ----------
        pydra_module_path : str
            the original Pydra module path
        """
        return ImportStatement.join_relative_package(
            self.nipype_module.__name__,
            ImportStatement.get_relative_package(pydra_module_path, self.output_module),
        )


def match_kwargs(args: ty.List[str], sig: ty.List[str]) -> ty.Dict[str, str]:
    """Matches up the args with given signature"""
    kwargs = {}
    found_kw = False
    for i, arg in enumerate(args):
        match = re.match(r"\s*(\w+)\s*=\s*(.*)", arg)
        if match:
            key, val = match.groups()
            found_kw = True
            kwargs[key] = val
        else:
            if found_kw:
                raise ValueError(
                    f"Non-keyword arg '{arg}' found after keyword arg in {args}"
                )
            kwargs[sig[i]] = arg

    return kwargs
