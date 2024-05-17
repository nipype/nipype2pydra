from functools import cached_property
import re
import typing as ty
import inspect
import logging
from operator import attrgetter
import attrs
from ..utils import extract_args
from typing_extensions import Self

if ty.TYPE_CHECKING:
    from ..workflow import WorkflowConverter


logger = logging.getLogger(__name__)


@attrs.define
class AssignmentStatement:

    indent: str = attrs.field()
    assignments: ty.Dict[str, str] = attrs.field()

    matches_re = re.compile(
        r"(\s*)(\w[\w\s,]*)\s*=\s*(.*)$", flags=re.MULTILINE | re.DOTALL
    )

    def __iter__(self):
        return iter(self.assignments)

    def items(self):
        return self.assignments.items()

    def keys(self):
        return self.assignments.keys()

    def values(self):
        return self.assignments.values()

    def __getitem__(self, name) -> str:
        return self.assignments[name]

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.matches_re.match(stmt))

    @classmethod
    def parse(cls, statement: str) -> "AssignmentStatement":
        match = cls.matches_re.match(statement)
        indent = match.group(1)
        varnames = [v.strip() for v in match.group(2).split(",")]
        value_str = match.group(3)
        if len(varnames) > 1:
            values = extract_args(
                "(" + value_str + ")" if not value_str.startswith("(") else value_str
            )[1]
            if len(values) == 1:
                values = [value_str + f"[{i}]" for i in range(len(varnames))]
        else:
            values = [value_str]
        if len(varnames) != len(values):
            raise ValueError(
                f"Number of variables ({len(varnames)}) does not match number of values "
                f"({len(values)})"
            )
        return AssignmentStatement(
            indent=indent, assignments=dict(zip(varnames, values))
        )

    def __str__(self):
        return f"{self.indent}{', '.join(self.keys())} = {', '.join(self.values())}"


@attrs.define
class VarField:

    varname: str = attrs.field()
    values: ty.List[AssignmentStatement] = attrs.field()

    def __repr__(self):
        return str(self)

    def __str__(self):
        return self.varname

    def match_to_workflow(self, workflow: "WorkflowConverter"):
        for node_and_field in reversed(self.values):
            match = re.match(r"('|\")(\w+)\.(\w+)\1", node_and_field)
            if not match:
                continue
            node_name, field_name = match.groups()[1:]
            if node_name in workflow.nodes:
                return node_name, field_name
        raise ValueError(
            f"Could not find node in {workflow.name} that match any "
            f"of the nodes referenced by for {self.varname}:\n" + "\n".join(self.values)
        )


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


def field_converter(
    field: str, assignments: ty.Dict[str, ty.List[AssignmentStatement]]
) -> ty.Union[str, VarField]:
    if isinstance(field, DynamicField):
        return field
    match = re.match(r"('|\")?([\w\.]+)\1?", field)
    if not match:
        raise ValueError(f"Could not parse field {field}, unmatched quotes")
    if match.group(1) is None:
        return VarField(field, assignments[field])
    else:
        field = match.group(2)
        if "." in field:
            field = NestedVarField(*field.split("."))
        return field


@attrs.define
class ConnectionStatement:

    source_name: ty.Optional[str]
    target_name: ty.Optional[str]
    source_out: ty.Union[str, VarField] = attrs.field()
    target_in: ty.Union[str, VarField] = attrs.field()
    indent: str = attrs.field()
    workflow_converter: "WorkflowConverter" = attrs.field(repr=False)
    include: bool = attrs.field(default=False)
    # wf_in: bool = False
    # wf_out: bool = False

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
        if self.wf_in:
            return []
        return self.workflow_converter.nodes[self.source_name]

    @cached_property
    def targets(self):
        if self.wf_out:
            return []
        return self.workflow_converter.nodes[self.target_name]

    @property
    def wf_in(self):
        try:
            self.workflow_converter.get_input_from_conn(self)
        except KeyError:
            return False
        else:
            return True

    @property
    def wf_out(self):
        try:
            self.workflow_converter.get_output_from_conn(self)
        except KeyError:
            return False
        else:
            return True

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
        return self.workflow_converter.get_input_from_conn(self).name

    @property
    def wf_out_name(self):
        return self.workflow_converter.get_output_from_conn(self).name

    def __str__(self):
        if not self.include or (
            self.wf_in and not self.workflow_converter.inputs[self.source_out].include
        ):
            return f"{self.indent}pass" if self.conditional else ""
        code_str = ""
        # Get source lazy-field
        if self.wf_in:
            src = f"{self.workflow_variable}.lzin.{self.source_out}"
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
            dynamic_src = True
        else:
            base_task_name = f"{self.source_name}_{self.source_out}_to_{self.target_name}_{self.target_in}"
            if isinstance(self.source_out, VarField):
                src = f"getattr({self.workflow_variable}.{self.source_name}.lzout, {self.source_out!r})"
            dynamic_src = False

        # Set src lazy field to target input
        if self.wf_out:
            if self.wf_in and not dynamic_src:
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
            code_str += f"{self.indent}{self.workflow_variable}.set_output([('{self.wf_out_name}', {src})])"
        elif isinstance(self.target_in, VarField):
            code_str += f"{self.indent}setattr({self.workflow_variable}.{self.target_name}.inputs, {self.target_in}, {src})"
        else:
            code_str += f"{self.indent}{self.workflow_variable}.{self.target_name}.inputs.{self.target_in} = {src}"
        return code_str

    @classmethod
    def parse(
        cls,
        statement: str,
        workflow_converter: "WorkflowConverter",
        assignments: ty.Dict[str, ty.List[AssignmentStatement]],
    ) -> ty.List[Self]:
        match = cls.match_re(workflow_converter.workflow_variable).match(statement)
        indent = match.group(1)
        args = extract_args(statement)[1]
        if len(args) == 1:
            conns = extract_args(args[0])[1]
        else:
            conns = [args]
        conn_stmts = []
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
                    varname, callable_str = args
                    out = DynamicField(
                        varname=varname,
                        callable=callable_str,
                        values=assignments[varname],
                    )
                if src == workflow_converter.input_node:
                    src = None  # Input node
                if tgt == workflow_converter.output_node:
                    tgt = None
                conn_stmts.append(
                    ConnectionStatement(
                        source_name=src,
                        target_name=tgt,
                        source_out=field_converter(out, assignments),
                        target_in=field_converter(in_, assignments),
                        indent=indent,
                        workflow_converter=workflow_converter,
                    )
                )
        return conn_stmts


@attrs.define
class IterableStatement:

    fieldname: str = attrs.field(converter=field_converter)
    variable: str = attrs.field()


@attrs.define(kw_only=True)
class AddNodeStatement:

    name: str
    args: ty.List[str]
    indent: str
    workflow_converter: "WorkflowConverter" = attrs.field(repr=False)
    in_conns: ty.List[ConnectionStatement] = attrs.field(factory=list)
    out_conns: ty.List[ConnectionStatement] = attrs.field(factory=list)
    include: bool = attrs.field(default=False)
    index: int = attrs.field()

    @index.default
    def _index_default(self):
        return len(self.workflow_converter.nodes)

    @cached_property
    def conditional(self):
        return len(self.indent) != 4

    @cached_property
    def workflow_variable(self):
        return self.workflow_converter.workflow_variable

    def add_input_connection(self, conn: ConnectionStatement):
        """Adds and input connection to a node, setting as an input of the whole
        workflow if the connection is to an input node and the workflow is marked as
        an "interface" to the package

        Parameters
        ----------
        conn : ConnectionStatement
            the connection to add

        Returns
        -------
        bool
            whether the connection is an input of the workflow
        """
        # Ensure that there is only 1 non-conditional connection to the input
        if not conn.conditional:
            try:
                prev = next(
                    c
                    for c in self.in_conns
                    if c.target_in == conn.target_in and not c.conditional
                )
            except StopIteration:
                pass
            else:
                logger.warning(
                    "'%s' input field of '%s' node receives multiple connections: "
                    "replacing %s:%s with %s:%s",
                    conn.target_in,
                    self.name,
                    prev.source_name,
                    prev.source_out,
                    conn.source_name,
                    conn.source_out,
                )
                self.in_conns.remove(prev)
        self.in_conns.append(conn)

    def add_output_connection(self, conn: ConnectionStatement) -> bool:
        """Adds and output connection to a node, setting as an output of the whole
        workflow if the connection is to an output nodeand the workflow is marked as
        an "interface" to the package

        Parameters
        ----------
        conn : ConnectionStatement
            the connection to add

        Returns
        -------
        bool
            whether the connection is an output of the workflow
        """
        self.out_conns.append(conn)


@attrs.define(kw_only=True)
class AddInterfaceStatement(AddNodeStatement):

    interface: str
    iterables: ty.List[IterableStatement]
    itersource: ty.Optional[str]
    splits: ty.List[str] = attrs.field(
        converter=attrs.converters.default_if_none(factory=list), factory=list
    )

    is_factory: bool = attrs.field(default=False)

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
            return f"{self.indent}pass" if self.conditional else ""
        args = ["=".join(a) for a in self.arg_name_vals]
        conn_args = []
        for conn in sorted(self.in_conns, key=attrgetter("target_in")):
            if not conn.include or not conn.lzouttable:
                continue
            if conn.wf_in:
                arg = (
                    f"{conn.target_in}={self.workflow_variable}.lzin.{conn.source_out}"
                )
            else:
                arg = (
                    f"{conn.target_in}={self.workflow_variable}."
                    f"{conn.source_name}.lzout.{conn.source_out}"
                )
            conn_args.append(arg)

        if self.is_factory:
            code_str = f"{self.indent}{self.name} = {self.interface}"
            if self.is_factory != "already-initialised":
                code_str += "(" + ",".join(args) + ")"
            code_str += f"\n{self.indent}{self.name}.name = '{self.name}'"
            for conn_arg in conn_args:
                code_str += f"\n{self.indent}{self.name}.inputs.{conn_arg}"
            code_str += f"\n{self.indent}{self.workflow_variable}.add({self.name})"
        else:
            code_str = (
                f"{self.indent}{self.workflow_variable}.add({self.converted_interface}("
                + ", ".join(sorted(args) + conn_args + [f'name="{self.name}"'])
                + "))"
            )

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
        cls,
        statement: str,
        workflow_converter: "WorkflowConverter",
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
        try:
            imported_obj = workflow_converter.used_symbols.get_imported_object(
                intf_name
            )
        except ImportError:
            imported_obj = None
            is_factory = "already-initialised"
            converter_cls = AddInterfaceStatement
        else:
            is_factory = inspect.isfunction(imported_obj)
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
            is_factory=is_factory,
        )


@attrs.define(kw_only=True)
class AddNestedWorkflowStatement(AddNodeStatement):

    workflow_name: str
    nested_workflow: ty.Optional["WorkflowConverter"]

    def __str__(self):
        if not self.include:
            return f"{self.indent}pass" if self.conditional else ""
        if self.nested_workflow:
            config_params = [
                f"{n}_{c}={n}_{c}" for n, c in self.nested_workflow.used_configs
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
            nested_workflow=workflow_converter.nested_workflows.get(wf_name),
            args=extract_args(statement)[1],
            indent=indent,
            workflow_converter=workflow_converter,
        )

    def add_input_connection(self, conn: ConnectionStatement):
        """Adds and input connection to a node, setting as an input of the whole
        workflow if the connection is to an input node and the workflow is marked as
        an "interface" to the package

        Parameters
        ----------
        conn : ConnectionStatement
            the connection to add

        Returns
        -------
        bool
            whether the connection is an input of the workflow
        """
        if isinstance(conn.target_in, VarField):
            target_name, target_in = conn.target_in.match_to_workflow(
                self.nested_workflow
            )
        elif isinstance(conn.target_in, NestedVarField):
            target_name = conn.target_in.node_name
            target_in = conn.target_in.varname
        else:
            target_in = conn.target_in
            target_name = None
        # Check for replacements for the given target field
        replacements = [
            i
            for i in self.nested_workflow.inputs.values()
            if any(n == target_name and f == target_in for n, f in i.replaces)
        ]
        if len(replacements) > 1:
            raise ValueError(
                f"Multiple inputs found for replacements of '{target_in}' "
                f"field in '{target_name}' node in '{self.name}' workflow: "
                + ", ".join(str(m) for m in replacements)
            )
        elif len(replacements) == 1:
            nested_input = replacements[0]
            target_name = None
        else:
            # If no replacements, create an input for the nested workflow
            if target_name == self.nested_workflow.input_node:
                target_name = None
            nested_input = self.nested_workflow.make_input(
                target_in,
                node_name=target_name,
            )
        conn.target_in = nested_input.name
        super().add_input_connection(conn)
        if target_name:
            # If not connected to the input node, add connections from the nested
            # workflow input to the target node
            for node in self.nested_workflow.nodes[target_name]:
                node_conn = ConnectionStatement(
                    source_name=None,
                    source_out=nested_input.name,
                    target_name=target_name,
                    target_in=target_in,
                    indent=conn.indent,
                    workflow_converter=self.nested_workflow,
                )
                self.nested_workflow._unprocessed_connections.append(node_conn)
                node.add_input_connection(node_conn)

    def add_output_connection(self, conn: ConnectionStatement):
        """Adds and output connection to a node, setting as an output of the whole
        workflow if the connection is to an output nodeand the workflow is marked as
        an "interface" to the package

        Parameters
        ----------
        conn : ConnectionStatement
            the connection to add

        Returns
        -------
        bool
            whether the connection is an output of the workflow
        """
        if isinstance(conn.source_out, VarField):
            source_name, source_out = conn.source_out.match_to_workflow(
                self.nested_workflow
            )
        elif isinstance(conn.source_out, NestedVarField):
            source_name = conn.source_out.node_name
            source_out = conn.source_out.varname
        else:
            source_out = conn.source_out
            source_name = None
        replacements = [
            o
            for o in self.nested_workflow.outputs.values()
            if any(n == source_name and f == source_out for n, f in o.replaces)
        ]
        if len(replacements) > 1:
            raise KeyError(
                f"Multiple outputs found for replacements of '{source_out}' "
                f"field in '{source_name}' node in '{self.name}' workflow: "
                + ", ".join(str(m) for m in replacements)
            )
        elif len(replacements) == 1:
            nested_output = replacements[0]
            source_name = None
        else:
            if source_name == self.nested_workflow.output_node:
                source_name = None
            nested_output = self.nested_workflow.make_output(
                source_out, node_name=source_name
            )
        conn.source_out = nested_output.name
        super().add_output_connection(conn)
        if source_name:
            # If not the output node, add connections to the nested workflow output
            # from the source node
            for node in self.nested_workflow.nodes[source_name]:
                node_conn = ConnectionStatement(
                    source_name=source_name,
                    source_out=source_out,
                    target_name=None,
                    target_in=nested_output.name,
                    indent=conn.indent,
                    workflow_converter=self.nested_workflow,
                )
                self.nested_workflow._unprocessed_connections.append(node_conn)
                node.add_output_connection(node_conn)


@attrs.define
class NodeAssignmentStatement:

    nodes: ty.List[AddInterfaceStatement]
    attribute: str
    value: str
    indent: str
    is_workflow: bool

    def __str__(self):
        if not any(n.include for n in self.nodes):
            return f"{self.indent}pass" if self.conditional else ""
        node = self.nodes[0]
        node_name = node.name
        workflow_variable = self.nodes[0].workflow_variable
        if self.is_workflow:
            nested_wf = node.nested_workflow
            parts = self.attribute.split(".")
            nested_node_name = parts[2]
            attribute_name = parts[3]
            target_in = nested_wf.make_input(attribute_name, nested_node_name).name
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

    @property
    def conditional(self):
        return len(self.indent) != 4

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
    workflow_converter: "WorkflowConverter"

    match_re = re.compile(
        r"\s+(\w+)\s*=.*\bWorkflow\(.*name\s*=\s*([^,=\)]+)",
        flags=re.MULTILINE,
    )

    @classmethod
    def matches(cls, stmt) -> bool:
        return bool(cls.match_re.match(stmt))

    @classmethod
    def parse(
        cls, statement: str, workflow_converter: "WorkflowConverter"
    ) -> "WorkflowInitStatement":
        match = cls.match_re.match(statement)
        varname, workflow_name = match.groups()
        return WorkflowInitStatement(
            varname=varname,
            workflow_name=workflow_name,
            workflow_converter=workflow_converter,
        )

    def __str__(self):
        return (
            f"    {self.varname} = Workflow("
            f"name={self.workflow_name}, input_spec={{"
            + ", ".join(
                f"'{i.name}': {i.type_repr}"
                for i in sorted(
                    self.workflow_converter.used_inputs, key=attrgetter("name")
                )
            )
            + "}, output_spec={"
            + ", ".join(
                f"'{o.name}': {o.type_repr}"
                for o in sorted(
                    self.workflow_converter.outputs.values(), key=attrgetter("name")
                )
            )
            + "}, "
            + ", ".join(
                f"{i}={i}"
                for i in sorted(j.name for j in self.workflow_converter.used_inputs)
            )
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


@attrs.define
class OtherStatement:

    indent: str
    statement: str

    def __str__(self):
        return self.indent + self.statement

    @classmethod
    def parse(cls, statement: str) -> "OtherStatement":
        return OtherStatement(
            *re.match(r"(\s*)(.*)$", statement, flags=re.MULTILINE | re.DOTALL).groups()
        )
