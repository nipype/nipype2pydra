import attrs
import typing as ty
from .workflow import AddNodeStatement, AddNestedWorkflowStatement


@attrs.define
class NodeAssignmentStatement:

    nodes: ty.List[AddNodeStatement] = attrs.field()
    attribute: str = attrs.field()
    value: str = attrs.field()
    indent: str = attrs.field()

    def __str__(self):
        if not any(n.include for n in self.nodes):
            return ""
        node_name = self.nodes[0].name
        workflow_variable = self.nodes[0].workflow_variable
        assert (n.name == node_name for n in self.nodes)
        assert (n.workflow_variable == workflow_variable for n in self.nodes)
        return f"{self.indent}{workflow_variable}.{node_name}{self.attribute} = {self.value}"


@attrs.define
class NestedWorkflowAssignmentStatement:

    nodes: ty.List[AddNestedWorkflowStatement] = attrs.field()
    attribute: str = attrs.field()
    value: str = attrs.field()
    indent: str = attrs.field()

    def __str__(self):
        if not any(n.include for n in self.nodes):
            return ""
        node = self.nodes[0]
        if not node.nested_spec:
            raise NotImplementedError(
                f"Need specification for nested workflow {node.workflow_name} in order to "
                "assign to it"
            )
        nested_wf = node.nested_spec
        parts = self.attribute.split(".")
        nested_node_name = parts[2]
        attribute_name = parts[3]
        target_in = nested_wf.input_name(nested_node_name, attribute_name)
        attribute = ".".join(parts[:2] + [target_in] + parts[4:])
        workflow_variable = self.nodes[0].workflow_variable
        assert (n.workflow_variable == workflow_variable for n in self.nodes)
        return f"{self.indent}{workflow_variable}{attribute} = {self.value}"
