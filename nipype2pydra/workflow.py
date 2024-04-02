from importlib import import_module
from functools import cached_property
import inspect
import re
import typing as ty
from operator import attrgetter
from copy import deepcopy
from types import ModuleType
from pathlib import Path
import attrs
from .utils import (
    UsedSymbols,
    split_source_into_statements,
    extract_args,
    cleanup_function_body,
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
    input_struct: tuple[str, str], optional
        a globally accessible structure containing inputs to the workflow, e.g. config.workflow.*
        tuple consists of the name of the input and the type of the input
    inputnode : str, optional
        the name of the workflow's input node (to be mapped to lzin), by default 'inputnode'
    outputnode : str, optional
        the name of the workflow's output node (to be mapped to lzout), by default 'outputnode'
    workflow_specs : dict[str, dict]
        The specs of potentially nested workflows functions that may be called within
        the workflow function
    omit_interfaces : list[str]
        the list of interfaces to be omitted from the workflow (e.g. DataGrabber)
    package_mappings : dict[str, str]
        packages that should be mapped to a new location (typically Nipype based deps
        such as niworkflows)
    other_mappings: dict[str, str]
        other name mappings between
    workflow_variable: str, optional
        the variable name that the workflow function returns, by default detected from the
        return statement. If multiple return statements are found, this must be specified
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
    workflow_specs: dict[str, dict] = attrs.field(factory=dict)
    omit_interfaces: list[str] = attrs.field(factory=list)
    package_mappings: dict[str, str] = attrs.field(factory=dict)
    other_mappings: dict[str, str] = attrs.field(factory=dict)
    workflow_variable: str = attrs.field()

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

    @workflow_variable.default
    def workflow_variable_default(self):
        returns = set(
            re.findall(r"^\s+return (\w+)", self.func_body, flags=re.MULTILINE)
        )
        if len(returns) > 1:
            raise RuntimeError(
                f"Ambiguous return statements {returns}, please specify explicitly"
            )
        return list(returns)[0]

    @cached_property
    def nipype_function(self) -> ty.Callable:
        func = getattr(self.nipype_module, self.nipype_name)
        if not isinstance(self.nipype_function, ty.Callable):
            raise ValueError(
                f"Could not find function {self.nipype_name} in module {self.nipype_module}, found "
                f"{self.nipype_name}=={func} instead"
            )
        return func

    @cached_property
    def used_symbols(self) -> UsedSymbols:
        return UsedSymbols.find(
            self.nipype_module, [self.func_body], collapse_intra_pkg=False
        )

    @cached_property
    def input_struct_re(self) -> ty.Optional[re.Pattern]:
        if not self.input_struct:
            return None
        if self.input_struct[1] == "class":
            regex = re.compile(r"\b" + self.input_struct + r"\.(\w+)\b")
        elif self.input_struct[1] == "dict":
            regex = re.compile(
                r"\b" + self.input_struct + r"\[(?:'|\")([^\]]+)(?:'|\")]"
            )
        else:
            assert False
        return regex

    @cached_property
    def used_inputs(self) -> ty.List[str]:
        if not self.input_struct_re:
            return []
        return sorted(self.input_struct_re.findall(self.func_body))

    @cached_property
    def func_src(self):
        return inspect.getsource(self.nipype_function)

    @cached_property
    def func_body(self):
        preamble, args, post = extract_args(self.func_src)
        return post.split(":", 1)[1]

    @cached_property
    def nested_workflows(self):
        potential_funcs = (
            self.used_symbols.intra_pkg_funcs + self.used_symbols.local_functions
        )
        return {
            name: WorkflowConverter(
                name=name,
                nipype_name=spec["nipype_name"],
                nipype_module=self.nipype_module,
                output_module=self.output_module,
                input_struct=self.input_struct,
                inputnode=self.inputnode,
                outputnode=self.outputnode,
                workflow_specs=self.workflow_specs,
                omit_interfaces=self.omit_interfaces,
                package_mappings=self.package_mappings,
                other_mappings=self.other_mappings,
                workflow_variable=self.workflow_variable,
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

        output_module = package_root.joinpath(
            self.output_module.split(".")
        ).with_suffix(".py")
        output_module.parent.mkdir(parents=True, exist_ok=True)

        used = deepcopy(self.used_symbols)

        other_wf_code = ""
        # Convert any nested workflows
        for name, conv in self.nested_workflows.items():
            already_converted.add(name)
            if name in self.used_symbols.local_functions:
                other_wf_code += "\n\n\n" + conv.convert_function_code(
                    already_converted
                )
                used.update(conv.used_symbols)
            else:
                conv.generate(package_root, already_converted=already_converted)

        code_str = "\n".join(used.imports) + "\n\n"
        code_str += self.convert_function_code(already_converted)
        code_str += other_wf_code
        for func in sorted(used.local_functions, key=attrgetter("__name__")):
            code_str += "\n\n" + cleanup_function_body(inspect.getsource(func))

        code_str += "\n".join(f"{n} = {d}" for n, d in used.constants)
        for klass in sorted(used.local_classes, key=attrgetter("__name__")):
            code_str += "\n\n" + cleanup_function_body(inspect.getsource(klass))

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

        preamble, args, post = extract_args(self.func_src)
        return_types = post.split(":", 1)[0]  # Get the return type

        # construct code string with modified signature
        code_str = (
            preamble + ", ".join(args + self.used_inputs) + f" -> {return_types}:\n"
        )

        converted_body = self.func_body
        if self.input_struct_re:
            converted_body = self.input_struct_re.sub("\1", converted_body)
        if self.other_mappings:
            for orig, new in self.other_mappings.items():
                converted_body = re.sub(r"\b" + orig + r"\b", new, converted_body)

        statements = split_source_into_statements(converted_body)

        nodes: ty.Dict[str, NodeConverter] = {}

        converted_statements = []
        for statement in statements:
            if match := re.match(
                r"\s+(\w+)\s+=.*\bNode\($", statement, flags=re.MULTILINE
            ):
                varname = match.group(1)
                args = extract_args(statement)[1]
                node_kwargs = match_kwargs(args, NodeConverter.SIGNATURE)
                intf_name, intf_args, intf_post = extract_args(node_kwargs["interface"])
                assert intf_post == ")"
                if "iterables" in node_kwargs:
                    iterables = [
                        IterableConverter(*extract_args(a)[1])
                        for a in extract_args(node_kwargs["iterables"])[1]
                    ]
                else:
                    iterables = []
                node_converter = nodes[varname] = NodeConverter(
                    name=node_kwargs["name"][1:-1],
                    interface=intf_name[:-1],
                    args=intf_args,
                    iterables=iterables,
                    itersource=node_kwargs.get("itersource"),
                    workflow_variable=self.workflow_variable,
                )
                converted_statements.append(node_converter)
            elif match := re.match(
                r"(\s+)(\w+) = (" + "|".join(self.nested_workflows) + r")\(",
                statement,
                flags=re.MULTILINE,
            ):
                varname, workflow_name = match.groups()
                converted_statements.append(
                    f"{varname} = {workflow_name}("
                    + ", ".join(args + self.nested_workflows[workflow_name].used_inputs)
                    + ")"
                )
            elif match := re.match(
                r"(\s*)" + self.workflow_variable + r"\.connect\(",
                statement,
                flags=re.MULTILINE | re.DOTALL,
            ):
                indent = match.group(1)
                args = extract_args(statement)[1]
                if len(args) == 1:
                    conns = extract_args()[1]
                else:
                    conns = [args]
                for conn in conns:
                    src, tgt, field_conns_str = extract_args(conn)[1]
                    field_conns = extract_args(field_conns_str)[1]
                    for field_conn in field_conns:
                        out, in_ = extract_args(field_conn)[1]
                        try:
                            out = DelayedVarField(extract_args(out)[1])
                        except ValueError:
                            pass
                        conn_converter = ConnectionConverter(
                            src, tgt, out, in_, indent, self.workflow_variable
                        )
                        if conn_converter.lzouttable and not nodes[tgt].conditional:
                            nodes[tgt].conns.append(conn_converter)
                        else:
                            converted_statements.append(conn_converter)

        # Write out the statements to the code string
        for statement in converted_statements:
            code_str += str(statement) + "\n"

        return code_str


VarField = ty.NewType("VarField", str)


@attrs.define
class DelayedVarField:

    name: str
    callable: ty.Callable


def field_converter(field: str) -> ty.Union[str, VarField]:
    match = re.match(r"('|\")?(\w+)('|\")?", field)
    if len(match.groups()) == 3:
        return VarField(match.group(2))
    elif len(match.groups()) == 1:
        field = match.group(1)
        if field.startswith("inputnode."):
            field = field[: len("inputnode.")]
            return DelayedVarField(field)
    else:
        raise ValueError(f"Could not parse field {field}, unmatched quotes")


@attrs.define
class ConnectionConverter:

    source: str
    target: str
    source_out: ty.Union[str, VarField] = attrs.field(converter=field_converter)
    target_in: ty.Union[str, VarField] = attrs.field(converter=field_converter)
    indent: str = attrs.field()
    workflow_converter: WorkflowConverter = attrs.field()

    @cached_property
    def lzouttable(self) -> bool:
        return (
            len(self.indent) == 4
            and isinstance(self.source_out, str)
            and isinstance(self.target_in, str)
        )

    @cached_property
    def workflow_variable(self):
        return self.workflow_converter.workflow_variable

    def __str__(self):
        code_str = ""
        if isinstance(self.source_out, VarField):
            src = f"getattr({self.workflow_variable}.outputs.{self.source}, {self.source_out})"
        elif isinstance(self.source_out, DelayedVarField):
            code_str += (
                f"\n{self.indent}@pydra.task.mark\n"
                f"{self.indent}def {self.source_out}_{self.source_out}_callable(in_: str):\n"
                f"{self.indent}    return {self.source_out.callable}(in_)\n\n"
                f"{self.indent}{self.workflow_variable}.add("
                f"{self.source_out}_{self.source_out}_callable("
                f"{self.workflow_variable}.{self.source}.lzout.{self.source_out.name}))\n\n"
            )
            src = f"{self.workflow_variable}.{self.source}_{self.source_out}_callable.lzout.out"
        else:
            src = f"{self.workflow_variable}.{self.source}.lzout.{self.source_out}"
        if isinstance(self.target_in, VarField):
            code_str += f"{self.indent}setattr({self.workflow_variable}.inputs.{self.target}, {src})"
        else:
            code_str += f"{self.indent}{self.target}.inputs.{self.target_in} = {src}"
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
    workflow_converter: WorkflowConverter
    conns: ty.List[ConnectionConverter] = attrs.field(factory=list)

    def __str__(self):
        code_str = (
            f"{self.indent}{self.workflow_variable}.add({self.interface}("
            + ", ".join(
                self.args
                + [
                    (
                        f"{conn.target_in}="
                        f"{self.workflow_variable}.{conn.source}.lzout.{conn.source_out}"
                    )
                    for conn in self.conns
                ]
            )
            + f', name="{self.name}"))'
        )
        for iterable in self.iterables:
            code_str += (
                f"{self.indent}{self.workflow_variable}.{self.name}.split("
                f"{iterable.fieldname}={iterable.variable})"
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
        "synchronize",
        "overwrite",
        "needed_outputs",
        "run_without_submitting",
        "n_procs",
        "mem_gb",
    ]


def match_kwargs(args: ty.List[str], sig: ty.List[str]) -> ty.Dict[str]:
    """Matches up the args with given signature"""
    kwargs = {}
    found_kw = False
    for i, arg in enumerate(args):
        try:
            key, val = arg.split("=")
        except ValueError:
            if found_kw:
                raise ValueError(
                    f"Non-keyword arg '{arg}' found after keyword arg in {args}"
                )
            kwargs[sig[i]] = val
        else:
            found_kw = True
            kwargs[key] = val
    return kwargs
