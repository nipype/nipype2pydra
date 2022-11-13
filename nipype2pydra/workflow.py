import json
from collections import defaultdict
import black
from nipype.interfaces.base import isdefined
from .utils import load_class_or_func
from nipype.pipeline.engine.workflows import Workflow


class WorkflowConverter:
#creating the wf
    def __init__(self, spec):
        self.spec = spec
        self.wf = load_class_or_func(self.spec['function'])(
            **self._parse_workflow_args(self.spec['args'])
        ) #loads the 'function' in smriprep.yaml, and implement the args (creates a dictionary)

    def node_connections(self, workflow):
        connections = defaultdict(dict)

        # iterates over wf graph, Get connections from workflow graph, store connections in a dictionary
        for edge, props in workflow._graph.edges.items():
            src_node = edge[0].name
            dest_node = edge[1].name
            for node_conn in props['connect']:
                src_field = node_conn[1]
                dest_field = node_conn[0]
                if src_field.startswith('def'):
                    print(f"Not sure how to deal with {src_field} in {src_node} to "
                          f"{dest_node}.{dest_field}")
                    continue
                else:
                    src_field = src_field.split('.')[-1]
                connections[dest_node][dest_field] = f"{src_node}.lzout.{src_field}"

        # Look for connections in nested workflows via recursion
        for node in workflow._get_all_nodes():  #TODO: find the method that iterates through the nodes of the workflow (but not nested nodes)---placeholder: find_name_of_appropriate_method
            if isinstance(node, Workflow):  # TODO: find a way to check whether the node is a standard node or a nested workflow
                connections.update(self.node_connections(node))
        return connections

    def generate(self, format_with_black=False):

        connections = self.node_connections(self.wf)
        out_text = ""
        for node_name in self.wf.list_node_names():
            node = self.wf.get_node(node_name)

            interface_type = type(node.interface)

            task_type = interface_type.__module__ + "." + interface_type.__name__
            node_args = ""
            for arg in node.inputs.visible_traits():
                val = getattr(node.inputs, arg)  # Enclose strings in quotes
                if isdefined(val):
                    try:
                        val = json.dumps(val)
                    except TypeError:
                        pass
                    if isinstance(val, str) and '\n' in val:
                        val = '"""' + val + '""""'
                    node_args += f",\n        {arg}={val}"

            for arg, val in connections[node.name].items():
                node_args += f",\n        {arg}=wf.{val}"

            out_text += f"""
    wf.add({task_type}(
        name="{node.name}"{node_args}
)"""

        if format_with_black:
            out_text = black.format_file_contents(out_text, fast=False, mode=black.FileMode())
        return out_text

    @classmethod
    def _parse_workflow_args(cls, args):
        dct = {}
        for name, val in args.items():
            if isinstance(val, dict) and sorted(val.keys()) == ['args', 'type']:
                val = load_class_or_func(val['type'])(
                    **cls._parse_workflow_args(val['args'])
                )
            dct[name] = val
        return dct
