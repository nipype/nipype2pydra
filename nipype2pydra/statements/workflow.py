from functools import cached_property
import re
import typing as ty
import inspect
import attrs
from ..utils import extract_args
from typing_extensions import Self

if ty.TYPE_CHECKING:
    from ..workflow import WorkflowConverter


@attrs.define
class VarField:

    varname: str = attrs.field()

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.varname


@attrs.define
class DynamicField(VarField):

    varname: str = attrs.field(
        converter=lambda s: s[1:-1] if s.startswith("'") or s.startswith('"') else s
    )
    callable: ty.Callable = attrs.field()

    def __repr__(self):
        return f"DelayedVarField({self.varname}, callable={self.callable})"


@attrs.define
class NestedVarField:

    node_name: str = attrs.field()
    varname: str = attrs.field()

    def __repr__(self):
        return repr(self.varname)

    def __str__(self):
        return self.varname


def field_converter(field: str) -> ty.Union[str, VarField]:
    if isinstance(field, DynamicField):
        return field
    match = re.match(r"('|\")?([\w\.]+)\1?", field)
    if not match:
        raise ValueError(f"Could not parse field {field}, unmatched quotes")
    if match.group(1) is None:
        return VarField(field)
    else:
        field = match.group(2)
        if "." in field:
            field = NestedVarField(*field.split("."))
        return field


@attrs.define
class ConnectionStatement:

    source_name: str
    target_name: str
    source_out: ty.Union[str, VarField] = attrs.field(converter=field_converter)
    target_in: ty.Union[str, VarField] = attrs.field(converter=field_converter)
    indent: str = attrs.field()
    workflow_converter: "WorkflowConverter" = attrs.field(repr=False)
    include: bool = attrs.field(default=False)
    wf_in: bool = False
    wf_out: bool = False

    @classmethod
    def match_re(cls, workflow_variable: str) -> bool:
        return re.compile(
            r"(\s*)" + workflow_variable + r"\.connect\(",
            flags=re.MULTILINE | re.DOTALL,
        )

    @classmethod
    def matches(cls, stmt, workflow_variable: str) -> bool:
        return bool(cls.match_re(workflow_variable).match(stmt))

    @cached_property
    def sources(self):
        return self.workflow_converter.nodes[self.source_name]

    @cached_property
    def targets(self):
        return self.workflow_converter.nodes[self.target_name]

    @cached_property
    def conditional(self):
        return len(self.indent) != 4

    @property
    def lzouttable(self) -> bool:
        return (
            not (self.conditional or any(s.conditional for s in self.sources))
            and not isinstance(self.target_in, VarField)
            and not isinstance(self.source_out, DynamicField)
            and all(all(s.index < t.index for t in self.targets) for s in self.sources)
        )

    @cached_property
    def workflow_variable(self):
        return self.workflow_converter.workflow_variable

    @property
    def wf_in_name(self):
        if not self.wf_in:
            raise ValueError(
                f"Cannot get wf_in_name for {self} as it is not a workflow input"
            )
        source_out_name = (
            self.source_out
            if not isinstance(self.source_out, DynamicField)
            else self.source_out.varname
        )
        return self.workflow_converter.input_name(self.source_name, source_out_name)

    @property
    def wf_out_name(self):
        if not self.wf_out:
            raise ValueError(
                f"Cannot get wf_out_name for {self} as it is not a workflow output"
            )
        return self.workflow_converter.output_name(self.target_name, self.target_in)

    def __str__(self):
        if not self.include:
            return ""
        code_str = ""
        # Get source lazy-field
        if self.wf_in:
            src = f"{self.workflow_variable}.lzin.{self.wf_in_name}"
        else:
            src = f"{self.workflow_variable}.{self.source_name}.lzout.{self.source_out}"
        if isinstance(self.source_out, DynamicField):
            base_task_name = f"{self.source_name}_{self.source_out.varname}_to_{self.target_name}_{self.target_in}"
            intf_name = f"{base_task_name}_callable"
            code_str += (
                f"\n{self.indent}@pydra.mark.task\n"
                f"{self.indent}def {intf_name}(in_: ty.Any) -> ty.Any:\n"
                f"{self.indent}    return {self.source_out.callable}(in_)\n\n"
                f"{self.indent}{self.workflow_variable}.add("
                f'{intf_name}(in_={src}, name="{intf_name}"))\n\n'
            )
            src = f"{self.workflow_variable}.{intf_name}.lzout.out"
        else:
            base_task_name = f"{self.source_name}_{self.source_out}_to_{self.target_name}_{self.target_in}"
            if isinstance(self.source_out, VarField):
                src = f"getattr({self.workflow_variable}.{self.source_name}.lzout, {self.source_out!r})"

        # Set src lazy field to target input
        if self.wf_out:
            if self.wf_in:
                # Workflow input is passed directly through to the output (because we have omitted the node)
                # that generated it and taken it as an input to the current node), so we need
                # to add an "identity" node to pass it through
                intf_name = f"{base_task_name}_identity"
                code_str += (
                    f"\n{self.indent}@pydra.mark.task\n"
                    f"{self.indent}def {intf_name}({self.wf_in_name}: ty.Any) -> ty.Any:\n"
                    f"{self.indent}    return {self.wf_in_name}\n\n"
                    f"{self.indent}{self.workflow_variable}.add("
                    f'{intf_name}({self.wf_in_name}={src}, name="{intf_name}"))\n\n'
                )
                src = f"{self.workflow_variable}.{intf_name}.lzout.out"
            code_str += f"{self.indent}{self.workflow_variable}.set_output([({self.wf_out_name!r}, {src})])"
        elif isinstance(self.target_in, VarField):
            code_str += f"{self.indent}setattr({self.workflow_variable}.{self.target_name}.inputs, {self.target_in}, {src})"
        else:
            code_str += f"{self.indent}{self.workflow_variable}.{self.target_name}.inputs.{self.target_in} = {src}"
        return code_str

    @classmethod
    def parse(
        cls, statement: str, workflow_converter: "WorkflowConverter"
    ) -> ty.List[Self]:
        match = cls.match_re(workflow_converter.workflow_variable).match(statement)
        indent = match.group(1)
        args = extract_args(statement)[1]
        if len(args) == 1:
            conns = extract_args(args[0])[1]
        else:
            conns = [args]
        conn_converters = []
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
                conn_converters.append(
                    ConnectionStatement(
                        source_name=src,
                        target_name=tgt,
                        source_out=out,
                        target_in=in_,
                        indent=indent,
                        workflow_converter=workflow_converter,
                    )
                )
        return conn_converters


@attrs.define
class IterableStatement:

    fieldname: str = attrs.field(converter=field_converter)
    variable: str = attrs.field()


@attrs.define
class AddInterfaceStatement:

    name: str
    interface: str
    args: ty.List[str]
    iterables: ty.List[IterableStatement]
    itersource: ty.Optional[str]
    indent: str
    workflow_converter: "WorkflowConverter" = attrs.field(repr=False)
    splits: ty.List[str] = attrs.field(
        converter=attrs.converters.default_if_none(factory=list), factory=list
    )
    in_conns: ty.List[ConnectionStatement] = attrs.field(factory=list)
    out_conns: ty.List[ConnectionStatement] = attrs.field(factory=list)
    include: bool = attrs.field(default=False)
    index: int = attrs.field()
    is_factory: bool = attrs.field(default=False)

    @index.default
    def _index_default(self):
        return len(self.workflow_converter.nodes)

    @property
    def inputs(self):
        return [c.target_in for c in self.in_conns]

    @property
    def arg_name_vals(self) -> ty.List[ty.Tuple[str, str]]:
        if self.args is None:
            return []
        name_vals = [a.split("=", 1) for a in self.args]
        return [(n, v) for n, v in name_vals if n not in self.splits]

    @cached_property
    def split_args(self) -> ty.List[str]:
        if self.args is None:
            return []
        return [a for a in self.args if a.split("=", 1)[0] in self.splits]

    @property
    def converted_interface(self):
        """To be overridden by sub classes"""
        return self.interface

    def __str__(self):
        if not self.include:
            return ""
        code_str = f"{self.indent}{self.workflow_variable}.add("
        args = ["=".join(a) for a in self.arg_name_vals]
        conn_args = []
        for conn in self.in_conns:
            if not conn.include or not conn.lzouttable:
                continue
            if conn.wf_in:
                arg = (
                    f"{conn.target_in}={self.workflow_variable}.lzin.{conn.wf_in_name}"
                )
            else:
                arg = (
                    f"{conn.target_in}={self.workflow_variable}."
                    f"{conn.source_name}.lzout.{conn.source_out}"
                )
            conn_args.append(arg)

        code_str += (
            f"{self.workflow_variable}.add({self.converted_interface}("
            + sorted((args if self.is_factory else args + conn_args))
            + [f'name="{self.name}"']
            + "))"
        )
        if self.is_factory:
            for conn_arg in conn_args:
                code_str += f"\n{self.indent}{self.workflow_variable}.inputs.{conn_arg}"

        if self.split_args:
            code_str += (
                f"{self.indent}{self.workflow_variable}.{self.name}.split("
                + ", ".join(self.split_args)
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
        return len(self.indent) != 4

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

    match_re = re.compile(r"(\s+)(\w+)\s*=.*\b(Map)?Node\(", flags=re.MULTILINE)

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.match_re.match(stmt))

    @classmethod
    def parse(
        cls, statement: str, workflow_converter: "WorkflowConverter"
    ) -> "AddInterfaceStatement":
        from .utility import UTILITY_CONVERTERS

        match = cls.match_re.match(statement)
        indent = match.group(1)
        varname = match.group(2)
        args = extract_args(statement)[1]
        node_kwargs = match_kwargs(args, AddInterfaceStatement.SIGNATURE)
        intf_name, intf_args, intf_post = extract_args(node_kwargs["interface"])
        if "iterables" in node_kwargs:
            iterables = [
                IterableStatement(*extract_args(a)[1])
                for a in extract_args(node_kwargs["iterables"])[1]
            ]
        else:
            iterables = []

        splits = node_kwargs["iterfield"] if match.group(3) else None
        if intf_name.endswith("("):  # strip trailing parenthesis
            intf_name = intf_name[:-1]
        imported_obj = workflow_converter.used_symbols.get_imported_object(intf_name)
        if re.match(r"nipype.interfaces.utility\b", imported_obj.__module__):
            converter_cls = UTILITY_CONVERTERS[imported_obj.__name__]
        else:
            converter_cls = AddInterfaceStatement
        return converter_cls(
            name=varname,
            interface=intf_name,
            args=intf_args,
            iterables=iterables,
            itersource=node_kwargs.get("itersource"),
            splits=splits,
            workflow_converter=workflow_converter,
            indent=indent,
            is_factory=inspect.isfunction(imported_obj),
        )


@attrs.define
class AddNestedWorkflowStatement:

    name: str
    workflow_name: str
    nested_spec: ty.Optional["WorkflowConverter"]
    indent: str
    args: ty.List[str]
    workflow_converter: "WorkflowConverter" = attrs.field(repr=False)
    include: bool = attrs.field(default=False)
    in_conns: ty.List[ConnectionStatement] = attrs.field(factory=list)
    out_conns: ty.List[ConnectionStatement] = attrs.field(factory=list)
    index: int = attrs.field()

    @index.default
    def _index_default(self):
        return len(self.workflow_converter.nodes)

    def __str__(self):
        if not self.include:
            return ""
        if self.nested_spec:
            config_params = [
                f"{n}_{c}={n}_{c}" for n, c in self.nested_spec.used_configs
            ]
        else:
            config_params = []
        args = []
        for conn in self.in_conns:
            if not conn.include or not conn.lzouttable:
                continue
            if conn.wf_in:
                arg = (
                    f"{conn.target_in}={self.workflow_variable}.lzin.{conn.wf_in_name}"
                )
            else:
                arg = (
                    f"{conn.target_in}={self.workflow_variable}."
                    f"{conn.source_name}.lzout.{conn.source_out}"
                )
            args.append(arg)
        args_str = ", ".join(self.args + config_params + args + [f"name='{self.name}'"])
        return f"{self.indent}{self.workflow_variable}.add({self.workflow_name}({args_str}))"

    @cached_property
    def conditional(self):
        return len(self.indent) != 4

    @cached_property
    def workflow_variable(self):
        return self.workflow_converter.workflow_variable

    @classmethod
    def match_re(cls, workflow_symbols: ty.List[str]):
        return re.compile(
            r"(\s+)(\w+) = (" + "|".join(workflow_symbols) + r")\(",
            flags=re.MULTILINE,
        )

    @classmethod
    def matches(cls, stmt, workflow_symbols: ty.List[str]) -> bool:
        return bool(cls.match_re(workflow_symbols).match(stmt))

    @classmethod
    def parse(
        cls, statement: str, workflow_converter: "WorkflowConverter"
    ) -> "AddNestedWorkflowStatement":
        match = cls.match_re(workflow_converter.nested_workflow_symbols).match(
            statement
        )
        indent, varname, wf_name = match.groups()
        return AddNestedWorkflowStatement(
            name=varname,
            workflow_name=wf_name,
            nested_spec=workflow_converter.nested_workflows.get(wf_name),
            args=extract_args(statement)[1],
            indent=indent,
            workflow_converter=workflow_converter,
        )


@attrs.define
class NodeAssignmentStatement:

    nodes: ty.List[AddInterfaceStatement]
    attribute: str
    value: str
    indent: str
    is_workflow: bool

    def __str__(self):
        if not any(n.include for n in self.nodes):
            return ""
        node = self.nodes[0]
        node_name = node.name
        workflow_variable = self.nodes[0].workflow_variable
        if self.is_workflow:
            nested_wf = node.nested_spec
            parts = self.attribute.split(".")
            nested_node_name = parts[2]
            attribute_name = parts[3]
            target_in = nested_wf.input_name(nested_node_name, attribute_name)
            attribute = ".".join(parts[:2] + [target_in] + parts[4:])
            workflow_variable = self.nodes[0].workflow_variable
            assert (n.workflow_variable == workflow_variable for n in self.nodes)
            return f"{self.indent}{workflow_variable}{attribute} = {self.value}"
        else:
            assert (n.name == node_name for n in self.nodes)
            assert (n.workflow_variable == workflow_variable for n in self.nodes)
            return f"{self.indent}{workflow_variable}.{node_name}{self.attribute} = {self.value}"

    @classmethod
    def match_re(cls, node_names: ty.List[str]) -> re.Pattern:
        return re.compile(
            r"(\s*)(" + "|".join(node_names) + r")\b([\w\.]+)\s*=\s*(.*)",
            flags=re.MULTILINE | re.DOTALL,
        )

    @classmethod
    def matches(cls, stmt, node_names: ty.List[str]) -> bool:
        if not node_names:
            return False
        return bool(cls.match_re(node_names).match(stmt))

    @classmethod
    def parse(
        cls, statement: str, workflow_converter: "WorkflowConverter"
    ) -> "NodeAssignmentStatement":
        match = cls.match_re(list(workflow_converter.nodes)).match(statement)
        indent, node_name, attribute, value = match.groups()
        nodes = workflow_converter.nodes[node_name]
        assert all(n.name == nodes[0].name for n in nodes)
        if isinstance(nodes[0], AddNestedWorkflowStatement):
            assert all(isinstance(n, AddNestedWorkflowStatement) for n in nodes)
            is_workflow = True
        else:
            assert all(isinstance(n, AddInterfaceStatement) for n in nodes)
            is_workflow = False
        return NodeAssignmentStatement(
            nodes=nodes,
            attribute=attribute,
            value=value,
            indent=indent,
            is_workflow=is_workflow,
        )


@attrs.define
class WorkflowInitStatement:

    varname: str
    workflow_name: str
    input_spec: ty.Optional[ty.List[str]] = None

    match_re = re.compile(
        r"\s+(\w+)\s*=.*\bWorkflow\(.*name\s*=\s*([^,=\)]+)",
        flags=re.MULTILINE,
    )

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.match_re.match(stmt))

    @classmethod
    def parse(cls, statement: str) -> "WorkflowInitStatement":
        match = cls.match_re.match(statement)
        varname, workflow_name = match.groups()
        return WorkflowInitStatement(varname=varname, workflow_name=workflow_name)

    def __str__(self):
        # Initialise the workflow object
        if self.input_spec is None:
            raise RuntimeError(
                "Workflow input spec not set, cannot initialise workflow object"
            )
        return (
            f"    {self.varname} = Workflow("
            f'name={self.workflow_name}, input_spec=["'
            + '", "'.join(sorted(self.input_spec))
            + '"], '
            + ", ".join(f"{i}={i}" for i in sorted(self.input_spec))
            + ")\n\n"
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
