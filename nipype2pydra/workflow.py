from importlib import import_module
from functools import cached_property
import inspect
import re
import typing as ty
from operator import attrgetter
from copy import copy
from types import ModuleType
from pathlib import Path
import black.parsing
import attrs
from .utils import (
    UsedSymbols,
    split_source_into_statements,
    extract_args,
    cleanup_function_body,
)


class VarField(str):
    pass


@attrs.define
class DelayedVarField:

    varname: str = attrs.field(
        converter=lambda s: s[1:-1] if s.startswith("'") or s.startswith('"') else s
    )
    callable: ty.Callable = attrs.field()


def field_converter(field: str) -> ty.Union[str, VarField]:
    if isinstance(field, DelayedVarField):
        return field
    match = re.match(r"('|\")?(\w+)('|\")?", field)
    if len(match.groups()) == 3:
        return VarField(match.group(2))
    elif len(match.groups()) == 1:
        field = match.group(1)
        if field.startswith("inputnode."):
            field = field[: len("inputnode.")]
            return field
    else:
        raise ValueError(f"Could not parse field {field}, unmatched quotes")


@attrs.define
class ConnectionConverter:

    source_name: str
    target_name: str
    source_out: ty.Union[str, VarField] = attrs.field(converter=field_converter)
    target_in: ty.Union[str, VarField] = attrs.field(converter=field_converter)
    indent: str = attrs.field()
    workflow_converter: "WorkflowConverter" = attrs.field()
    include: bool = attrs.field(default=False)
    lzin: bool = attrs.field(default=False)

    @cached_property
    def source(self):
        return self.workflow_converter.nodes[self.source_name]

    @cached_property
    def target(self):
        return self.workflow_converter.nodes[self.target_name]

    @cached_property
    def conditional(self):
        return len(self.indent) != 4

    @cached_property
    def lzouttable(self) -> bool:
        return not (
            self.conditional or self.source.conditional or self.target.conditional
        ) and (isinstance(self.source_out, str) and isinstance(self.target_in, str))

    @cached_property
    def workflow_variable(self):
        return self.workflow_converter.workflow_variable

    def __str__(self):
        if not self.include:
            return ""
        code_str = ""
        if isinstance(self.source_out, VarField):
            src = f"getattr({self.workflow_variable}.outputs.{self.source_name}, {self.source_out})"
        elif isinstance(self.source_out, DelayedVarField):
            task_name = f"{self.source_name}_{self.source_out.varname}"
            intf_name = f"{task_name}_callable"
            code_str += (
                f"\n{self.indent}@pydra.task.mark\n"
                f"{self.indent}def {intf_name}(in_: str):\n"
                f"{self.indent}    return {self.source_out.callable}(in_)\n\n"
                f"{self.indent}{self.workflow_variable}.add("
                f'{intf_name}(in_={self.workflow_variable}.{self.source_name}.lzout.{self.source_out.varname}, name="{task_name}"))\n\n'
            )
            src = f"{self.workflow_variable}.{task_name}.lzout.out"
        else:
            src = f"{self.workflow_variable}.{self.source_name}.lzout.{self.source_out}"
        if isinstance(self.target_in, VarField):
            code_str += f"{self.indent}setattr({self.workflow_variable}.inputs.{self.target_name}, {src})"
        else:
            code_str += (
                f"{self.indent}{self.target_name}.inputs.{self.target_in} = {src}"
            )
        return code_str


@attrs.define
class IterableConverter:

    fieldname: str = attrs.field(converter=field_converter)
    variable: str = attrs.field()


@attrs.define
class NodeConverter:

    name: str
    interface: str
    args: ty.List[str]
    iterables: ty.List[IterableConverter]
    itersource: ty.Optional[str]
    indent: str
    workflow_converter: "WorkflowConverter"
    splits: ty.List[str] = attrs.field(
        converter=attrs.converters.default_if_none(factory=list), factory=list
    )
    in_conns: ty.List[ConnectionConverter] = attrs.field(factory=list)
    out_conns: ty.List[ConnectionConverter] = attrs.field(factory=list)
    include: bool = attrs.field(default=False)

    @property
    def inputs(self):
        return [c.target_in for c in self.in_conns]

    def __str__(self):
        if not self.include:
            return ""
        code_str = f"{self.indent}{self.workflow_variable}.add("
        split_args = None
        if self.args is not None:
            split_args = [a for a in self.args if a.split("=", 1)[0] in self.splits]
            nonsplit_args = [
                a for a in self.args if a.split("=", 1)[0] not in self.splits
            ]
            code_str += f"{self.interface}(" + ", ".join(
                nonsplit_args
                + [
                    (
                        f"{conn.target_in}="
                        f"{self.workflow_variable}.{conn.source_name}.lzout.{conn.source_out}"
                    )
                    for conn in self.in_conns
                    if conn.lzouttable
                ]
            )
            if self.args:
                code_str += ", "
            code_str += f'name="{self.name}")'
        code_str += ")"
        if split_args:
            code_str += (
                f"{self.indent}{self.workflow_variable}.{self.name}.split("
                + ", ".join(split_args)
                + ")"
            )
        if self.iterables:
            raise NotImplementedError(
                f"iterables not yet implemented (see {self.name} node) in "
                f"{self.workflow_converter.name} workflow"
            )
        if self.itersource:
            raise NotImplementedError(
                f"itersource not yet implemented (see {self.name} node) in "
                f"{self.workflow_converter.name} workflow"
            )
        return code_str

    @cached_property
    def conditional(self):
        return self.indent != 4

    @cached_property
    def workflow_variable(self):
        return self.workflow_converter.workflow_variable

    SIGNATURE = [
        "interface",
        "name",
        "iterables",
        "itersource",
        "iterfield",
        "synchronize",
        "overwrite",
        "needed_outputs",
        "run_without_submitting",
        "n_procs",
        "mem_gb",
    ]


@attrs.define
class NestedWorkflowConverter:

    varname: str
    workflow_name: str
    nested_spec: "WorkflowConverter"
    indent: str
    args: ty.List[str]
    include: bool = attrs.field(default=False)
    in_conns: ty.List[ConnectionConverter] = attrs.field(factory=list)
    out_conns: ty.List[ConnectionConverter] = attrs.field(factory=list)

    def __str__(self):
        if not self.include:
            return ""
        return (
            f"{self.indent}{self.varname} = {self.workflow_name}("
            + ", ".join(self.args + self.nested_spec.used_configs)
            + ")"
        )

    @cached_property
    def conditional(self):
        return self.indent != 4


@attrs.define
class ConfigParamsConverter:

    varname: str = attrs.field(
        metadata={
            "help": (
                "name dict/struct that contains the workflow inputs, e.g. config.workflow.*"
            ),
        }
    )
    type: str = attrs.field(
        metadata={
            "help": (
                "name of the nipype module the function is found within, "
                "e.g. mriqc.workflows.anatomical.base"
            ),
        },
        validator=attrs.validators.in_(["dict", "struct"]),
    )

    module: str = attrs.field(
        converter=lambda m: import_module(m) if not isinstance(m, ModuleType) else m,
        metadata={
            "help": (
                "name of the nipype module the function is found within, "
                "e.g. mriqc.workflows.anatomical.base"
            ),
        },
    )


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
    config_params: tuple[str, str], optional
        a globally accessible structure containing inputs to the workflow, e.g. config.workflow.*
        tuple consists of the name of the input and the type of the input
    inputnode : str, optional
        the name of the workflow's input node (to be mapped to lzin), by default 'inputnode'
    outputnode : str, optional
        the name of the workflow's output node (to be mapped to lzout), by default 'outputnode'
    workflow_specs : dict[str, dict]
        The specs of potentially nested workflows functions that may be called within
        the workflow function
    package_mappings : dict[str, str]
        packages that should be mapped to a new location (typically Nipype based deps
        such as niworkflows)
    other_mappings: dict[str, str]
        other name mappings between
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
    output_module: str = attrs.field(
        metadata={
            "help": (
                "name of the output module in which to write the workflow function"
            ),
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
    inputnode: str = attrs.field(
        default="inputnode",
        metadata={
            "help": (
                "Name of the node that is to be considered the input of the workflow, "
                "i.e. its outputs will be the inputs of the workflow"
            ),
        },
    )
    outputnode: str = attrs.field(
        default="outputnode",
        metadata={
            "help": (
                "Name of the node that is to be considered the output of the workflow, "
                "i.e. its inputs will be the outputs of the workflow"
            ),
        },
    )
    workflow_specs: dict[str, dict] = attrs.field(
        factory=dict,
        metadata={
            "help": (
                "workflow specifications of other workflow functions in the package, which "
                "could be potentially nested within the workflow"
            ),
        },
    )
    # omit_interfaces: list[str] = attrs.field(
    #     factory=list,
    #     metadata={
    #         "help": (""),
    #     },
    # )
    package_mappings: dict[str, str] = attrs.field(
        factory=dict,
        metadata={
            "help": ("mappings between nipype packages and their pydra equivalents"),
        },
    )
    other_mappings: dict[str, str] = attrs.field(
        factory=dict,
        metadata={
            "help": (
                "mappings between nipype objects/classes and their pydra equivalents"
            ),
        },
    )
    workflow_variable: str = attrs.field(
        metadata={
            "help": ("name of the workflow variable that is returned"),
        },
    )
    nodes: ty.Dict[str, NodeConverter] = attrs.field(factory=dict)

    @output_module.default
    def _output_module_default(self):
        return f"pydra.tasks.{self.nipype_module.__name__}"

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
            self.nipype_module, [self.func_body], collapse_intra_pkg=False
        )

    @cached_property
    def config_params_regexes(self) -> ty.Dict[str, re.Pattern]:
        regexes = {}
        for name, config_params in self.config_params.items():
            if config_params.type == "struct":
                regex = re.compile(r"\b" + config_params.varname + r"\.(\w+)\b")
            elif config_params.type == "dict":
                regex = re.compile(
                    r"\b" + config_params.varname + r"\[(?:'|\")([^\]]+)(?:'|\")]"
                )
            else:
                assert False
            regexes[name] = regex
        return regexes

    @cached_property
    def config_defaults(self) -> ty.Dict[str, ty.Dict[str, str]]:
        defaults = {}
        for name, config_params in self.config_params.items():
            params = config_params.module
            for part in config_params.varname.split("."):
                params = getattr(params, part)
            if config_params.type == "struct":
                defaults[name] = {
                    a: getattr(params, a)
                    for a in dir(params)
                    if not inspect.isfunction(getattr(params, a))
                }
            elif config_params.type == "dict":
                defaults[name] = params
            else:
                assert False, f"Unrecognised config_params type {config_params.type}"
        return defaults

    @cached_property
    def used_configs(self) -> ty.List[str]:
        used_configs = []
        for name, regex in self.config_params_regexes.items():
            configs = sorted(set(regex.findall(self.func_body)))
            used_configs.extend(
                f"{name}_{g}={self.config_defaults[name][g]!r}" for g in configs
            )
        return used_configs

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
            name: WorkflowConverter(
                name=name,
                nipype_name=spec["nipype_name"],
                nipype_module=spec["nipype_module"],
                output_module=self.output_module,
                config_params=spec["config_params"],
                inputnode=spec["inputnode"],
                outputnode=spec["outputnode"],
                workflow_specs=self.workflow_specs,
                # omit_interfaces=self.omit_interfaces,
                package_mappings=spec["package_mappings"],
                other_mappings=spec["other_mappings"],
                workflow_variable=spec["workflow_variable"],
            )
            for name, spec in self.workflow_specs.items()
            if name in potential_funcs
        }

    def generate(self, package_root: Path, already_converted: ty.Set[str] = None):
        """Generate the Pydra task module

        Parameters
        ----------
        package_root: str
            the root directory of the package to write the module to
        already_converted : set[str], optional
            names of the workflows that have already converted workflows
        """

        if already_converted is None:
            already_converted = set()
        already_converted.add(self.full_name)

        output_module = package_root.joinpath(
            *self.output_module.split(".")
        ).with_suffix(".py")
        output_module.parent.mkdir(parents=True, exist_ok=True)

        used = UsedSymbols(
            imports=copy(self.used_symbols.imports),
            intra_pkg_classes=copy(self.used_symbols.intra_pkg_classes),
            intra_pkg_funcs=copy(self.used_symbols.intra_pkg_funcs),
            local_functions=copy(self.used_symbols.local_functions),
            local_classes=copy(self.used_symbols.local_classes),
            constants=copy(self.used_symbols.constants),
        )

        other_wf_code = ""
        # Convert any nested workflows
        for name, conv in self.nested_workflows.items():
            if conv.full_name in already_converted:
                continue
            already_converted.add(conv.full_name)
            if name in self.used_symbols.local_functions:
                other_wf_code += "\n\n\n" + conv.convert_function_code(
                    already_converted
                )
                used.update(conv.used_symbols)
            else:
                conv.generate(package_root, already_converted=already_converted)

        code_str = (
            "\n".join(used.imports) + "\n" + "from pydra.engine import Workflow\n\n"
        )
        code_str += self.convert_function_code(already_converted)
        code_str += other_wf_code
        for func in sorted(used.local_functions, key=attrgetter("__name__")):
            if func.__name__ in already_converted:
                continue
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

        with open(output_module, "w") as f:
            f.write(code_str)

    def convert_function_code(self, already_converted: ty.Set[str]):
        """Generate the Pydra task module

        Parameters
        ----------
        already_converted : set[str]
            names of the workflows that have already converted workflows

        Returns
        -------
        function_code : str
            the converted function code
        """

        preamble, func_args, post = extract_args(self.func_src)
        return_types = post[1:].split(":", 1)[0]  # Get the return type

        # construct code string with modified signature
        code_str = preamble + ", ".join(func_args + self.used_configs) + ")"
        if return_types:
            code_str += f" -> {return_types}"
        code_str += ":\n\n"

        converted_body = self.func_body
        for config_name, config_regex in self.config_params_regexes.items():
            converted_body = config_regex.sub(config_name + r"_\1", converted_body)
        if self.other_mappings:
            for orig, new in self.other_mappings.items():
                converted_body = re.sub(r"\b" + orig + r"\b", new, converted_body)

        statements = split_source_into_statements(converted_body)

        converted_statements = []
        workflow_name = None
        for statement in statements:
            if re.match(r"^\s*#", statement):  # comments
                converted_statements.append(statement)
            elif match := re.match(
                r"\s+(?:"
                + self.workflow_variable
                + r")\s*=.*\bWorkflow\(.*name\s*=\s*([^,\)]+)",
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
                node_converter = self.nodes[varname] = NodeConverter(
                    name=node_kwargs["name"][1:-1],
                    interface=intf_name[:-1],
                    args=intf_args,
                    iterables=iterables,
                    itersource=node_kwargs.get("itersource"),
                    splits=splits,
                    workflow_converter=self,
                    indent=indent,
                )
                converted_statements.append(node_converter)
            elif match := re.match(  #
                r"(\s+)(\w+) = (" + "|".join(self.nested_workflows) + r")\(",
                statement,
                flags=re.MULTILINE,
            ):
                indent, varname, workflow_name = match.groups()
                nested_workflow_converter = NestedWorkflowConverter(
                    varname=varname,
                    workflow_name=workflow_name,
                    nested_spec=self.nested_workflows[workflow_name],
                    args=args,
                    indent=indent,
                )
                self.nodes[varname] = nested_workflow_converter
                converted_statements.append(nested_workflow_converter)

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
                            out = DelayedVarField(*args)
                        conn_converter = ConnectionConverter(
                            source_name=src,
                            target_name=tgt,
                            source_out=out,
                            target_in=in_,
                            indent=indent,
                            workflow_converter=self,
                        )
                        if not conn_converter.lzouttable:
                            converted_statements.append(conn_converter)
                        self.nodes[src].out_conns.append(conn_converter)
                        self.nodes[tgt].in_conns.append(conn_converter)
            else:
                converted_statements.append(statement)

        if workflow_name is None:
            raise ValueError(
                "Did not detect worklow name in statements:\n\n" + "\n".join(statements)
            )
        try:
            input_node = self.nodes[self.inputnode]
        except KeyError:
            raise ValueError(
                f"Unrecognised input node '{self.inputnode}', not in {list(self.nodes)} "
                f"for {self.full_name}"
            )

        if self.outputnode:
            try:
                output_node = self.nodes[self.outputnode]
            except KeyError:
                raise ValueError(
                    f"Unrecognised output node '{self.outputnode}', not in {list(self.nodes)} "
                    f"for {self.full_name}"
                )
        else:
            output_node = None

        node_stack = [input_node]
        included = []
        while node_stack:
            node = node_stack.pop()
            node.include = True
            included.append(node)
            for conn in node.out_conns:
                conn.include = True
                if conn.target not in included:
                    node_stack.append(conn.target)

        input_node.include = False
        for conn in input_node.out_conns:
            conn.lzin = True
        if output_node:
            output_node.include = False
            for conn in output_node.in_conns:
                conn.include = False

        code_str += (
            f'    {self.workflow_variable} = Workflow(name="{workflow_name}")\n\n'
        )

        # Write out the statements to the code string
        for statement in converted_statements:
            code_str += str(statement) + "\n"

        if output_node:
            for conn in output_node.in_conns:
                if conn.source.include:
                    code_str += (
                        f'    {self.workflow_variable}.set_output([("{conn.target_in}", '
                        f"{self.workflow_variable}.{conn.source_name}.lzout.{conn.source_out})])\n"
                    )

        code_str += f"\n    return {self.workflow_variable}"

        return code_str


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
