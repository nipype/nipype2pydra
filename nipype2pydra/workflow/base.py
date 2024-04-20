from importlib import import_module
from functools import cached_property
import inspect
import re
import typing as ty
from copy import copy
import logging
from collections import defaultdict
from types import ModuleType
from pathlib import Path
import attrs
import yaml
from ..utils import (
    UsedSymbols,
    split_source_into_statements,
    extract_args,
    write_to_module,
    full_address,
    ImportStatement,
    parse_imports,
)
from .components import (
    NodeConverter,
    ConnectionConverter,
    NestedWorkflowConverter,
    CommentConverter,
    DocStringConverter,
    ReturnConverter,
    IterableConverter,
    DynamicField,
    NodeAssignmentConverter,
)
import nipype2pydra.package

logger = logging.getLogger(__name__)


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
        converter=lambda lst: [tuple(i) for i in lst] if lst else [],
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
    package: "nipype2pydra.package.PackageConverter" = attrs.field(
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
        converter=attrs.converters.default_if_none(factory=list),
        factory=list,
    )

    nodes: ty.Dict[str, ty.List[NodeConverter]] = attrs.field(factory=dict)

    def __attrs_post_init__(self):
        if self.workflow_variable is None:
            self.workflow_variable = self.workflow_variable_default()

    @nipype_module.validator
    def _nipype_module_validator(self, _, value):
        if self.package:
            if not self.nipype_module_name.startswith(self.package.nipype_name + "."):
                raise ValueError(
                    f"Workflow {self.name} is not in the nipype package {self.package.nipype_name}"
                )

    @property
    def output_module(self):
        return self.package.translate_submodule(self.nipype_module_name)

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
            translations=self.package.all_import_translations,
        )

    @cached_property
    def config_defaults(self) -> ty.Dict[str, ty.Dict[str, str]]:
        all_defaults = {}
        for name, config_params in self.package.config_params.items():
            params = config_params.module
            all_defaults[name] = {}
            for part in config_params.varname.split("."):
                params = getattr(params, part)
            if config_params.type == "struct":
                defaults = {
                    a: getattr(params, a)
                    for a in dir(params)
                    if not inspect.isfunction(getattr(params, a))
                    and not a.startswith("_")
                }
            elif config_params.type == "dict":
                defaults = copy(params)
            else:
                assert False, f"Unrecognised config_params type {config_params.type}"
            defaults.update(config_params.defaults)
            all_defaults[name] = defaults
        return all_defaults

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
        potential_funcs = {
            full_address(f[1]): f[0] for f in self.used_symbols.intra_pkg_funcs
        }
        potential_funcs.update(
            (full_address(f), f.__name__) for f in self.used_symbols.local_functions
        )
        return {
            potential_funcs[address]: workflow
            for address, workflow in self.package.workflows.items()
            if address in potential_funcs
        }

    @cached_property
    def nested_workflow_symbols(self) -> ty.List[str]:
        """Returns the symbols that are used in the body of the workflow that are also
        workflows"""
        return list(self.nested_workflows) + self.external_nested_workflows

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

        used = self.used_symbols.copy()

        # Start writing output module with used imports and converted function body of
        # main workflow
        code_str = self.converted_code

        # Get any intra-package classes and functions that need to be written

        for _, intra_pkg_obj in used.intra_pkg_classes + list(used.intra_pkg_funcs):
            if full_address(intra_pkg_obj) not in list(self.package.workflows):
                # + list(
                #     self.package.interfaces
                # ):
                intra_pkg_modules[
                    self.to_output_module_path(intra_pkg_obj.__module__)
                ].add(intra_pkg_obj)

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

        write_to_module(
            package_root,
            module_name=self.output_module,
            converted_code=code_str,
            used=used,
            find_replace=self.package.find_replace,
        )

        # Write test code
        write_to_module(
            package_root,
            module_name=ImportStatement.join_relative_package(
                self.output_module, ".tests.test_" + self.name
            ),
            converted_code=self.test_code,
            used=self.test_used,
        )

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

        # Initialise the workflow object
        code_str = (
            f"    {self.workflow_variable} = Workflow("
            f'name={workflow_name}, input_spec=["'
            + '", "'.join(sorted(input_spec))
            + '"])\n\n'
        )

        preamble = ""
        # Write out the preamble (e.g. docstring, comments, etc..)
        while parsed_statements and isinstance(
            parsed_statements[0],
            (DocStringConverter, CommentConverter, ImportStatement),
        ):
            preamble += str(parsed_statements.pop(0)) + "\n"

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

        config_sig = []
        param_init = ""
        for scope_prefix, config_name in used_configs:
            param_name = f"{scope_prefix}_{config_name}"
            param_default = self.config_defaults[scope_prefix][config_name]
            if isinstance(param_default, str) and "(" in param_default:
                # delay init of default value to function body
                param_init += (
                    f"    if {param_name} is None:\n"
                    f"        {param_name} = {param_default}\n\n"
                )
                param_default = None
            config_sig.append(f"{param_name}={param_default!r}")

        # construct code string with modified signature
        signature = declaration + ", ".join(sorted(func_args + config_sig)) + ")"
        if return_types:
            signature += f" -> {return_types}"
        code_str = signature + ":\n\n" + preamble + param_init + code_str

        if not isinstance(parsed_statements[-1], ReturnConverter):
            code_str += f"\n    return {self.workflow_variable}"

        for find, replace in self.find_replace:
            code_str = re.sub(find, replace, code_str, flags=re.MULTILINE | re.DOTALL)

        return code_str, used_configs

    @property
    def test_code(self):
        return f"""

def test_{self.name}():
    workflow = {self.name}()
    assert isinstance(workflow, Workflow)
"""

    @property
    def test_used(self):
        return UsedSymbols(
            imports=parse_imports(
                [
                    f"from {self.output_module} import {self.name}",
                    "from pydra.engine import Workflow",
                ]
            )
        )

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
                parsed.extend(
                    parse_imports(
                        statement,
                        relative_to=self.nipype_module.__name__,
                        translations=self.package.all_import_translations,
                    )
                )
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
                r"(\s+)(\w+) = (" + "|".join(self.nested_workflow_symbols) + r")\(",
                statement,
                flags=re.MULTILINE,
            ):
                indent, varname, wf_name = match.groups()
                nested_workflow_converter = NestedWorkflowConverter(
                    name=varname,
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

    @classmethod
    def default_spec(
        cls, name: str, nipype_module: str, defaults: ty.Dict[str, ty.Any]
    ) -> str:
        """Generates a spec for the workflow converter from the given function"""
        conv = WorkflowConverter(
            name=name,
            nipype_name=name,
            nipype_module=nipype_module,
            input_nodes={"": "inputnode"},
            output_nodes={"": "outputnode"},
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
            fld = getattr(attrs.fields(WorkflowConverter), k)
            hlp = fld.metadata.get("help")
            if hlp:
                yaml_str = re.sub(
                    r"^(" + k + r"):",
                    "# " + hlp + r"\n\1:",
                    yaml_str,
                    flags=re.MULTILINE,
                )
        return yaml_str


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
