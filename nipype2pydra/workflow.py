import json
from collections import defaultdict
import black
from nipype.interfaces.base import isdefined
from .utils import load_class_or_func


class WorkflowConverter:

    def __init__(self, spec):
        self.spec = spec
        self.wf = load_class_or_func(self.spec['function'])(
            **self._parse_workflow_args(self.spec['args'])
        )

    def node_connections(self):
        connections = defaultdict(dict)

        for edge, props in self.wf._graph.edges.items():
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
        return connections

    def generate(self):

        connections = self.node_connections()
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
                node_args += f",\n        {arg}={val}"

            out_text += f"""
        wf.add({task_type}(
            name="{node.name}"{node_args}
        )"""

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
