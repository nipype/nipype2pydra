from importlib import import_module
from functools import cached_property, partial
import inspect
import re
import typing as ty
from copy import copy
import logging
from collections import defaultdict
from types import ModuleType
import itertools
from pathlib import Path
import black.report
import attrs
import yaml
from fileformats.core import from_mime, FileSet, Field
from fileformats.core.exceptions import FormatRecognitionError
from .utils import (
    UsedSymbols,
    split_source_into_statements,
    extract_args,
    full_address,
    multiline_comment,
    from_named_dicts_converter,
    unwrap_nested_type,
)
from .statements import (
    ImportStatement,
    parse_imports,
    AddInterfaceStatement,
    ConnectionStatement,
    AddNestedWorkflowStatement,
    CommentStatement,
    DocStringStatement,
    ReturnStatement,
    NodeAssignmentStatement,
    WorkflowInitStatement,
    AssignmentStatement,
    OtherStatement,
)
import nipype2pydra.package

logger = logging.getLogger(__name__)


def convert_node_prefixes(
    nodes: ty.Union[ty.Dict[str, str], ty.Sequence[ty.Union[ty.Tuple[str, str], str]]]
) -> ty.Dict[str, str]:
    if isinstance(nodes, dict):
        nodes_it = nodes.items()
    else:
        nodes_it = [(n, "") if isinstance(n, str) else n for n in nodes]
    return {n: v if v is not None else "" for n, v in nodes_it}


def convert_type(tp: ty.Union[str, type]) -> type:
    if not isinstance(tp, str):
        return tp
    try:
        return from_mime(tp)
    except FormatRecognitionError:
        return eval(tp)


@attrs.define
class WorkflowInterfaceField:

    name: str = attrs.field(
        converter=str,
        metadata={
            "help": "Name of the input/output field in the converted workflow",
        },
    )
    node_name: ty.Optional[str] = attrs.field(
        metadata={
            "help": "The name of the node that the input/output is connected to",
        },
    )
    field: str = attrs.field(
        converter=str,
        metadata={
            "help": "The name of the field in the node that the input/output is connected to",
        },
    )
    type: type = attrs.field(
        default=ty.Any,
        converter=convert_type,
        metadata={
            "help": "The type of the input/output of the converted workflow",
        },
    )
    replaces: ty.Tuple[ty.Tuple[str, str]] = attrs.field(
        converter=lambda lst: tuple(sorted(tuple(t) for t in lst)),
        factory=list,
        metadata={
            "help": (
                "node-name/field-name pairs of other fields that are to be routed to "
                "from other node fields to this input/output",
            )
        },
    )
    export: bool = attrs.field(
        default=False,
        metadata={
            "help": (
                "whether the input and output should be propagated out from "
                "nested workflows to the top-level workflow."
            )
        },
    )

    @property
    def type_repr(self):
        """Get a representation of the input/output type that can be written to code"""

        def type_repr_(t):
            args = ty.get_args(t)
            if args:
                return (
                    type_repr_(ty.get_origin(t))
                    + "["
                    + ", ".join(type_repr_(a) for a in args)
                    + "]"
                )
            if t in (ty.Any, ty.Union, ty.List, ty.Tuple):
                try:
                    t_name = t.__name__
                except AttributeError:
                    t_name = t._name
                return f"ty.{t_name}"
            elif issubclass(t, Field):
                return t.primitive.__name__
            elif issubclass(t, FileSet):
                return t.__name__
            elif t.__module__ == "builtins":
                return t.__name__
            else:
                return f"{t.__module__}.{t.__name__}"

        return type_repr_(self.type)

    @field.default
    def _field_name_default(self):
        return self.name

    def __hash__(self):
        return hash(
            (
                self.name,
                self.node_name,
                self.field,
                self.type,
                self.replaces,
                self.export,
            )
        )


@attrs.define
class WorkflowInput(WorkflowInterfaceField):

    out_conns: ty.List[ConnectionStatement] = attrs.field(
        factory=list,
        eq=False,
        hash=False,
        metadata={
            "help": (
                "The list of connections that are connected from this output, "
                "populated during parsing"
            )
        },
    )

    include: bool = attrs.field(
        default=False,
        eq=False,
        hash=False,
        metadata={
            "help": (
                "Whether the input is required for the workflow once the unused nodes "
                "have been filtered out"
            )
        },
    )

    def __hash__(self):
        return super().__hash__()


@attrs.define
class WorkflowOutput(WorkflowInterfaceField):

    in_conns: ty.List[ConnectionStatement] = attrs.field(
        factory=list,
        eq=False,
        hash=False,
        metadata={
            "help": (
                "The list of connections that are connected to this input, "
                "populated during parsing"
            )
        },
    )

    def __hash__(self):
        return super().__hash__()


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
    input_node : str, optional
        the name of the workflow's input node (to be mapped to lzin), by default 'inputnode'
    output_node :  str, optional
        the name of the workflow's output node (to be mapped to lzout), by default 'outputnode'
    inputs: dict[str, WorkflowInput], optional
        explicitly defined inputs of the workflow (i.e. as opposed to implicit ones determined
        by the input_nodes of the workflow)
    outputs: dict[str, WorkflowOutput], optional
        explicitly defined output of the workflow (i.e. as opposed to implicit ones determined
        by the output_nodes of the workflow)
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
    input_node: ty.Optional[str] = attrs.field(
        default=None,
        metadata={
            "help": (
                "Name of the node that is to be considered the input of the workflow, "
                "i.e. all of its outputs will be the inputs of the workflow, unless "
                'explicitly overridden by an "input" value.'
            ),
        },
    )
    output_node: ty.Optional[str] = attrs.field(
        default=None,
        metadata={
            "help": (
                "Name of the node that is to be considered the output of the workflow, "
                "i.e. its inputs will be the outputs of the workflow unless "
                'explicitly overridden by an "output" value.'
            ),
        },
    )
    inputs: ty.Dict[str, WorkflowInput] = attrs.field(
        converter=partial(from_named_dicts_converter, klass=WorkflowInput),
        factory=dict,
        metadata={
            "help": (
                "Explicitly defined inputs of the workflow (i.e. as opposed to implicit "
                "ones determined by the input_nodes of the workflow)"
            ),
        },
    )
    outputs: ty.Dict[str, WorkflowOutput] = attrs.field(
        converter=partial(from_named_dicts_converter, klass=WorkflowOutput),
        factory=dict,
        metadata={
            "help": (
                "Explicitly defined output of the workflow (i.e. as opposed to implicit "
                "ones determined by the output_nodes of the workflow)"
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
    test_inputs: ty.Dict[str, ty.Any] = attrs.field(
        metadata={
            "help": ("the inputs to the test function"),
        },
        converter=attrs.converters.default_if_none(factory=dict),
        factory=dict,
    )
    external: bool = attrs.field(
        default=False,
        metadata={
            "help": "Whether the workflow is to be treated as an external workflow, "
            "i.e. all inputs and outputs are to be exported"
        },
    )
    nodes: ty.Dict[str, ty.List[AddInterfaceStatement]] = attrs.field(
        factory=dict, repr=False
    )
    _unprocessed_connections: ty.List[ConnectionStatement] = attrs.field(
        factory=list, repr=False
    )
    used_inputs: ty.Optional[ty.Set[WorkflowInput]] = attrs.field(
        default=None, repr=False
    )

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
    def address(self):
        return f"{self.nipype_module_name}.{self.nipype_name}"

    @property
    def exported_inputs(self):
        return (i for i in self.inputs.values() if i.export)

    @property
    def exported_outputs(self):
        return (o for o in self.outputs.values() if o.export)

    def get_input_from_conn(self, conn: ConnectionStatement) -> WorkflowInput:
        """
        Returns the name of the input field in the workflow for the given node and field
        escaped by the prefix of the node if present"""
        try:
            return self.make_input(
                field_name=conn.source_out,
                node_name=conn.source_name,
                input_node_only=None,
            )
        except KeyError:
            pass
        if conn.source_name is None or conn.source_name == self.input_node:
            return self.make_input(field_name=conn.source_out)
        elif conn.target_name is None:
            raise KeyError(
                f"Could not find output corresponding to '{conn.source_out}' input"
            )
        return self.make_input(
            field_name=conn.source_out, node_name=conn.source_name, input_node_only=True
        )

    def get_output_from_conn(self, conn: ConnectionStatement) -> WorkflowOutput:
        """
        Returns the name of the input field in the workflow for the given node and field
        escaped by the prefix of the node if present"""
        try:
            return self.make_output(
                field_name=conn.source_out,
                node_name=conn.source_name,
                output_node_only=None,
            )
        except KeyError:
            pass
        if conn.target_name is None or conn.target_name == self.output_node:
            return self.make_output(field_name=conn.target_in)
        elif conn.source_name is None:
            raise KeyError(
                f"Could not find output corresponding to '{conn.source_out}' input"
            )
        return self.make_output(
            field_name=conn.source_out,
            node_name=conn.source_name,
            output_node_only=True,
        )

    def make_input(
        self,
        field_name: str,
        node_name: ty.Optional[str] = None,
        input_node_only: ty.Optional[bool] = False,
    ) -> WorkflowInput:
        """
        Returns the name of the input field in the workflow for the given node and field
        escaped by the prefix of the node if present"""
        field_name = str(field_name)
        matching = [
            i
            for i in self.inputs.values()
            if i.node_name == node_name and i.field == field_name
        ]
        if len(matching) > 1:
            raise RuntimeError(
                f"Multiple inputs found for '{field_name}' field in "
                f"'{node_name}' node in '{self.name}' workflow"
            )
        elif len(matching) == 1:
            return matching[0]
        else:
            if input_node_only is None:
                raise KeyError
            if node_name is None or node_name == self.input_node:
                inpt_name = field_name
            elif input_node_only:
                raise KeyError(
                    f"Could not find input corresponding to '{field_name}' field in "
                    f"'{node_name}' node in '{self.name}' workflow, set "
                    "`only_input_node=False` to make an input for any node input"
                ) from None
            else:
                inpt_name = f"{node_name}_{field_name}"
            try:
                return self.inputs[inpt_name]
            except KeyError:
                inpt = WorkflowInput(
                    name=inpt_name, field=field_name, node_name=node_name
                )
                self.inputs[inpt_name] = inpt
                return inpt

    def make_output(
        self,
        field_name: str,
        node_name: ty.Optional[str] = None,
        output_node_only: ty.Optional[bool] = False,
    ) -> WorkflowOutput:
        """
        Returns the name of the input field in the workflow for the given node and field
        escaped by the prefix of the node if present"""
        field_name = str(field_name)
        matching = [
            o
            for o in self.outputs.values()
            if o.node_name == node_name and o.field == field_name
        ]
        if len(matching) > 1:
            raise RuntimeError(
                f"Multiple outputs found for '{field_name}' field in "
                f"'{node_name}' node in '{self.name}' workflow: "
                + ", ".join(str(m) for m in matching)
            )
        elif len(matching) == 1:
            return matching[0]
        else:
            if output_node_only is None:
                raise KeyError
            if node_name is None or node_name == self.output_node:
                outpt_name = field_name
            elif output_node_only:
                raise KeyError(
                    f"Could not find output corresponding to '{field_name}' field in "
                    f"'{node_name}' node in '{self.name}' workflow, set "
                    "`only_output_node=False` to make an output for any node output"
                ) from None
            else:
                outpt_name = f"{node_name}_{field_name}"
            try:
                return self.outputs[outpt_name]
            except KeyError:
                outpt = WorkflowOutput(
                    name=outpt_name, field=field_name, node_name=node_name
                )
                self.outputs[outpt_name] = outpt
                return outpt

    def add_connection_to_input(self, in_conn: ConnectionStatement):
        """Add a in_connection to an input of the workflow, adding the input if not present"""
        node_name = in_conn.target_name
        field_name = str(in_conn.target_in)
        try:
            inpt = self._input_mapping[(node_name, field_name)]
        except KeyError:
            if node_name == self.input_node:
                inpt = WorkflowInput(
                    name=field_name,
                    node_name=self.input_node,
                    field=field_name,
                )
            name = in_conn.source_out
            if in_conn.source_name != in_conn.workflow_converter.input_node:
                name = f"{in_conn.source_name}_{name}"
            inpt = WorkflowInput(
                name=name,
                node_name=self.input_node,
                field=field_name,
            )
            raise KeyError(
                f"Could not find input corresponding to '{field_name}' field in "
                f"'{in_conn.target_name}' node in '{self.name}' workflow"
            )
            self._input_mapping[(node_name, field_name)] = inpt
            self.inputs[field_name] = inpt

    def add_connection_from_input(self, out_conn: ConnectionStatement):
        """Add a connection to an input of the workflow, adding the input if not present"""
        node_name = out_conn.source_name
        field_name = str(out_conn.source_out)
        try:
            inpt = self._input_mapping[(node_name, field_name)]
        except KeyError:
            if node_name == self.input_node:
                inpt = WorkflowInput(
                    name=field_name,
                    node_name=self.input_node,
                    field=field_name,
                )
            else:
                raise KeyError(
                    f"Could not find input corresponding to '{field_name}' field in "
                    f"'{out_conn.target_name}' node in '{self.name}' workflow"
                )
            self._input_mapping[(node_name, field_name)] = inpt
            self.inputs[field_name] = inpt

        inpt.in_out_conns.append(out_conn)

    def add_connection_to_output(self, in_conn: ConnectionStatement):
        """Add a connection to an input of the workflow, adding the input if not present"""
        self._add_output_conn(in_conn, "in")

    def add_connection_from_output(self, out_conn: ConnectionStatement):
        """Add a connection to an input of the workflow, adding the input if not present"""
        self._add_output_conn(out_conn, "from")

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
            always_include=self.package.all_explicit,
            translations=self.package.all_import_translations,
        )

    @property
    def used_configs(self) -> ty.List[str]:
        return self._converted_code[1]

    @property
    def converted_code(self) -> ty.List[str]:
        try:
            return self._converted_code[0]
        except AttributeError as e:
            raise RuntimeError("caught AttributeError") from e

    @cached_property
    def input_output_imports(self) -> ty.List[ImportStatement]:
        nonstd_types = self._converted_code[2]
        stmts = []
        for tp in itertools.chain(*(unwrap_nested_type(t) for t in nonstd_types)):
            stmts.append(ImportStatement.from_object(tp))
        return ImportStatement.collate(stmts)

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
            full_address(f[1]): f[0] for f in self.used_symbols.intra_pkg_funcs if f[0]
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

    @cached_property
    def nested_workflow_statements(self) -> ty.List[AddNestedWorkflowStatement]:
        """Returns the statements in the workflow that are AddNestedWorkflowStatements"""
        return [
            stmt
            for stmt in self.parsed_statements
            if isinstance(stmt, AddNestedWorkflowStatement)
        ]

    def write(
        self,
        package_root: Path,
        already_converted: ty.Set[str] = None,
        additional_funcs: ty.List[str] = None,
        nested: bool = False,
    ) -> UsedSymbols:
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

        Returns
        -------
        all_used: UsedSymbols
            all the symbols used in the workflow and its nested workflows
        """

        if already_converted is None:
            already_converted = set()
        already_converted.add(self.address)

        if additional_funcs is None:
            additional_funcs = []

        used = self.used_symbols.copy()
        all_used = self.used_symbols.copy()

        # Start writing output module with used imports and converted function body of
        # main workflow
        code_str = self.converted_code

        local_func_names = {f.__name__ for f in used.local_functions}
        # Convert any nested workflows
        for name, conv in self.nested_workflows.items():
            if conv.address in already_converted:
                continue
            already_converted.add(conv.address)
            all_used.update(conv.used_symbols)
            if name in local_func_names:
                code_str += "\n\n\n" + conv.converted_code
                used.update(conv.used_symbols)
            else:
                conv_all_used = conv.write(
                    package_root,
                    already_converted=already_converted,
                )
                all_used.update(conv_all_used)

        self.package.write_to_module(
            package_root,
            module_name=self.output_module,
            converted_code=code_str,
            used=used,
            additional_imports=self.input_output_imports,
        )

        self.package.write_pkg_inits(
            package_root,
            self.output_module,
            names=[self.name],
            depth=self.package.init_depth,
            auto_import_depth=self.package.auto_import_init_depth,
            import_find_replace=self.package.import_find_replace,
        )

        # Write test code
        test_module_fspath = self.package.write_to_module(
            package_root,
            module_name=ImportStatement.join_relative_package(
                self.output_module,
                (
                    ".tests.test_"
                    + "_".join(
                        self.output_module.split(".")[
                            len(self.package.name.split(".")) :
                        ]
                    )
                    + "_"
                    + self.name
                ),
            ),
            converted_code=self.test_code,
            used=self.test_used,
            additional_imports=self.input_output_imports,
        )

        conftest_fspath = test_module_fspath.parent / "conftest.py"
        if not conftest_fspath.exists():
            with open(conftest_fspath, "w") as f:
                f.write(self.CONFTEST)

        all_used.update(self.test_used)
        return all_used

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

        for nested_workflow in self.nested_workflows.values():
            # processing nested workflows first so we know which inputs are required
            nested_workflow._converted_code

        declaration, func_args, post = extract_args(self.func_src)
        return_types = post[1:].split(":", 1)[0]  # Get the return type

        nonstd_types = set()

        def add_nonstd_types(tp):
            if ty.get_origin(tp) in (list, ty.Union):
                for tp_arg in ty.get_args(tp):
                    add_nonstd_types(tp_arg)
            elif tp.__module__ not in ["builtins", "pathlib", "typing"]:
                nonstd_types.add(tp)

        # Walk through the DAG and include all nodes and connections that are connected to
        # the input nodes and their connections up until the output nodes
        conn_stack: ty.List[ConnectionStatement] = []

        for inpt in self.inputs.values():
            conn_stack.extend(inpt.out_conns)
            add_nonstd_types(inpt.type)

        while conn_stack:
            conn = conn_stack.pop()
            # Will only be included if connected from inputs to outputs. If included
            # from input->output traversal nodes and conns are flagged as include=None,
            # because this coerces to False but is differentiable from False when we
            # come to do the traversal in the other direction
            conn.include = None
            if conn.target_name:
                sibling_target_nodes = self.nodes[conn.target_name]
                exclude = True
                for target_node in sibling_target_nodes:
                    # Check to see if the input is required, so we can change its include
                    # flag back to false if not
                    if (
                        not isinstance(target_node, AddNestedWorkflowStatement)
                        or target_node.nested_workflow.inputs[conn.target_in].include
                    ):
                        target_node.include = None
                        conn_stack.extend(target_node.out_conns)
                        exclude = False
                if exclude:
                    conn.include = False

        # Walk through the graph backwards from the outputs and trim any unnecessary
        # connections
        assert not conn_stack
        for outpt in self.outputs.values():
            conn_stack.extend(outpt.in_conns)
            add_nonstd_types(outpt.type)

        nonstd_types.discard(ty.Any)

        self.used_inputs = set()

        while conn_stack:
            conn = conn_stack.pop()
            # if included forward from inputs and backwards from outputs
            if conn.include is None:
                conn.include = True
            else:
                continue
            if conn.source_name:
                sibling_source_nodes = self.nodes[conn.source_name]
                for source_node in sibling_source_nodes:
                    # if included forward from inputs and backwards from outputs
                    if source_node.include is None:
                        source_node.include = True
                        conn_stack.extend(source_node.in_conns)
            else:
                inpt = self.inputs[conn.source_out]
                inpt.include = True
                self.used_inputs.add(inpt)

        preamble = ""
        statements = copy(self.parsed_statements)
        # Write out the preamble (e.g. docstring, comments, etc..)
        while statements and isinstance(
            statements[0],
            (DocStringStatement, CommentStatement, ImportStatement),
        ):
            preamble += str(statements.pop(0)) + "\n"

        # Write out the statements to the code string
        code_str = ""
        for statement in statements:
            code_str += str(statement) + "\n"

        nested_configs = set()
        for nested_workflow in self.nested_workflows.values():
            nested_configs.update(nested_workflow.used_configs)

        code_str, config_sig, used_configs = (
            self.package.find_and_replace_config_params(code_str, nested_configs)
        )

        inputs_sig = [f"{i.name}=attrs.NOTHING" for i in self.used_inputs]

        # construct code string with modified signature
        signature = (
            declaration + ", ".join(sorted(func_args + config_sig + inputs_sig)) + ")"
        )
        if return_types:
            signature += f" -> {return_types}"
        code_str = signature + ":\n\n" + preamble + code_str

        if not isinstance(statements[-1], ReturnStatement):
            code_str += f"\n    return {self.workflow_variable}"

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

        return code_str, used_configs, nonstd_types

    @cached_property
    def parsed_statements(self):
        # Parse the statements in the function body into converter objects and strings
        return self._parse_statements(self.func_body)

    @property
    def test_code(self):
        args_str = ", ".join(f"{n}={v}" for n, v in self.test_inputs.items())

        return f"""

def test_{self.name}():
    workflow = {self.name}({args_str})
    assert isinstance(workflow, Workflow)
"""

    @property
    def test_used(self):
        return UsedSymbols(
            module_name=self.nipype_module.__name__,
            imports=parse_imports(
                [
                    f"from {self.output_module} import {self.name}",
                    "from pydra.engine import Workflow",
                ]
            ),
        )

    def prepare(self):
        """Prepare workflow for writing by populating all members via parsing the
        statments within it. It is delayed until all workflow converters are initiated
        so that they can detect inputs/outputs in each other"""
        self.parsed_statements

    def prepare_connections(self):
        """Prepare workflow connections by assigning all connections to inputs and outputs
        of each node statement, inputs and outputs of the workflow are also assigned"""
        self.prepare()
        # Ensure that nested workflows are prepared first
        for nested_workflow in self.nested_workflows.values():
            nested_workflow.prepare_connections()
        # Propagate exported inputs and outputs to the top-level workflow
        for node_name, nodes in self.nodes.items():
            exported_inputs = set()
            exported_outputs = set()
            for node in nodes:
                if isinstance(node, AddNestedWorkflowStatement):
                    exported_inputs.update(
                        (i.name, self.make_input(i.name, node_name))
                        for i in node.nested_workflow.exported_inputs
                    )
                    exported_outputs.update(
                        (o.name, self.make_output(o.name, node_name))
                        for o in node.nested_workflow.exported_outputs
                    )
            for inpt_name, exp_inpt in exported_inputs:
                exp_inpt.export = True
                self._unprocessed_connections.append(
                    ConnectionStatement(
                        indent="    ",
                        source_name=None,
                        source_out=exp_inpt.name,
                        target_name=node_name,
                        target_in=inpt_name,
                        workflow_converter=self,
                    )
                )
            for outpt_name, exp_outpt in exported_outputs:
                exp_outpt.export = True
                conn_stmt = ConnectionStatement(
                    indent="    ",
                    source_name=node_name,
                    source_out=outpt_name,
                    target_name=None,
                    target_in=exp_outpt.name,
                    workflow_converter=self,
                )
                self._unprocessed_connections.append(conn_stmt)
                # append to parsed statements so set_output can be set
                self.parsed_statements.append(conn_stmt)
        while self._unprocessed_connections:
            conn = self._unprocessed_connections.pop()
            try:
                inpt = self.get_input_from_conn(conn)
            except KeyError:
                for src_node in self.nodes[conn.source_name]:
                    src_node.add_output_connection(conn)
            else:
                conn.source_name = None
                conn.source_out = inpt.name
                inpt.out_conns.append(conn)
            try:
                outpt = self.get_output_from_conn(conn)
            except KeyError:
                for tgt_node in self.nodes[conn.target_name]:
                    tgt_node.add_input_connection(conn)
            else:
                conn.target_name = None
                conn.target_in = outpt.name
                outpt.in_conns.append(conn)

    def _parse_statements(self, func_body: str) -> ty.Tuple[
        ty.List[
            ty.Union[
                str,
                ImportStatement,
                AddInterfaceStatement,
                ConnectionStatement,
                AddNestedWorkflowStatement,
                NodeAssignmentStatement,
                WorkflowInitStatement,
                DocStringStatement,
                CommentStatement,
                ReturnStatement,
            ]
        ],
        WorkflowInitStatement,
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
        output_names = []
        workflow_init = None
        workflow_init_index = None
        assignments = defaultdict(list)
        for i, statement in enumerate(statements):
            if not statement.strip():
                continue
            if CommentStatement.matches(statement):  # comments
                parsed_stmt = CommentStatement.parse(statement)
                parsed.append(parsed_stmt)
            elif DocStringStatement.matches(statement):  # docstrings
                parsed_stmt = DocStringStatement.parse(statement)
                parsed.append(parsed_stmt)
            elif ImportStatement.matches(statement):
                parsed_imports = parse_imports(
                    statement,
                    relative_to=self.nipype_module.__name__,
                    translations=self.package.all_import_translations,
                )
                parsed.extend(parsed_imports)
                parsed_stmt = parsed_imports[-1]
            elif WorkflowInitStatement.matches(statement):
                workflow_init = parsed_stmt = WorkflowInitStatement.parse(
                    statement, self
                )
                if workflow_init_index is None:
                    parsed.append(parsed_stmt)
                else:
                    parsed.insert(workflow_init_index, parsed_stmt)
            elif AddInterfaceStatement.matches(statement):
                if workflow_init_index is None:
                    workflow_init_index = i
                parsed_stmt = AddInterfaceStatement.parse(statement, self)
                self._add_node_converter(parsed_stmt)
                parsed.append(parsed_stmt)
            elif AddNestedWorkflowStatement.matches(
                statement, self.nested_workflow_symbols
            ):
                if workflow_init_index is None:
                    workflow_init_index = i
                parsed_stmt = AddNestedWorkflowStatement.parse(statement, self)
                self._add_node_converter(parsed_stmt)
                parsed.append(parsed_stmt)
            elif ConnectionStatement.matches(statement, self.workflow_variable):
                if workflow_init_index is None:
                    workflow_init_index = i
                conn_stmts = ConnectionStatement.parse(statement, self, assignments)
                for conn_stmt in conn_stmts:
                    self._unprocessed_connections.append(conn_stmt)
                    if conn_stmt.wf_out:
                        output_name = self.get_output_from_conn(conn_stmt).name
                        conn_stmt.target_in = output_name
                        if conn_stmt.conditional:
                            parsed.append(conn_stmt)
                        elif output_name not in output_names:
                            parsed.append(conn_stmt)
                            output_names.append(output_name)
                    elif not conn_stmt.lzouttable:
                        parsed.append(conn_stmt)
                parsed_stmt = conn_stmts[-1]
            elif ReturnStatement.matches(statement):
                parsed_stmt = ReturnStatement.parse(statement)
                parsed.append(parsed_stmt)
            elif NodeAssignmentStatement.matches(statement, list(self.nodes)):
                if workflow_init_index is None:
                    workflow_init_index = i
                parsed_stmt = NodeAssignmentStatement.parse(statement, self)
                parsed.append(parsed_stmt)
            elif AssignmentStatement.matches(statement):
                parsed_stmt = AssignmentStatement.parse(statement)
                for varname, value in parsed_stmt.items():
                    assignments[varname].append(value)
                parsed.append(parsed_stmt)
            else:  # A statement we don't need to parse in a special way so leave as string
                parsed_stmt = OtherStatement.parse(statement)
                parsed.append(parsed_stmt)

        if workflow_init is None:
            raise ValueError(
                "Did not detect worklow initialisation in statements:\n\n"
                + "\n".join(statements)
            )

        # Pop return statement so that other statements can be appended if necessary.
        # An explicit return statement will be added before it is written to file
        if isinstance(parsed[-1], ReturnStatement):
            parsed.pop()

        return parsed

    def _add_node_converter(
        self, converter: ty.Union[AddInterfaceStatement, AddNestedWorkflowStatement]
    ):
        if converter.name in self.nodes:
            self.nodes[converter.name].append(converter)
        else:
            self.nodes[converter.name] = [converter]

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
            input_node="inputnode",
            output_node="outputnode",
            **{n: eval(v) for n, v in defaults},
        )
        dct = attrs.asdict(conv)
        dct["nipype_module"] = dct["nipype_module"].__name__
        for n in ["package", "nodes", "used_inputs", "_unprocessed_connections"]:
            del dct[n]
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
                    multiline_comment(hlp) + r"\1:",
                    yaml_str,
                    flags=re.MULTILINE,
                )
        return yaml_str

    CONFTEST = """
# For debugging in IDE's don't catch raised exceptions and let the IDE
# break at it
import os
import pytest


if os.getenv("_PYTEST_RAISE", "0") != "0":

    @pytest.hookimpl(tryfirst=True)
    def pytest_exception_interact(call):
        raise call.excinfo.value  # raise internal errors instead of capturing them

    @pytest.hookimpl(tryfirst=True)
    def pytest_internalerror(excinfo):
        raise excinfo.value  # raise internal errors instead of capturing them

    def pytest_configure(config):
        config.option.capture = 'no'  # allow print statements to show up in the console
        config.option.log_cli = True  # show log messages in the console
        config.option.log_level = "INFO"  # set the log level to INFO

    CATCH_CLI_EXCEPTIONS = False
else:
    CATCH_CLI_EXCEPTIONS = True
"""
