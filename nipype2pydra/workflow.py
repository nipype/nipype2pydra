from __future__ import annotations
import json
import tempfile
from pathlib import Path
import subprocess as sp
from collections import defaultdict
import black
from nipype.interfaces.base import isdefined
from .utils import load_class_or_func
from nipype.pipeline.engine.workflows import Workflow


class WorkflowConverter:
    # creating the wf
    def __init__(self, spec):
        self.spec = spec

        self.wf = load_class_or_func(self.spec["function"])(
            **self._parse_workflow_args(self.spec["args"])
        )  # loads the 'function' in smriprep.yaml, and implement the args (creates a dictionary)

    def node_connections(self, workflow, functions: dict[str, dict], wf_inputs: dict[str, str], wf_outputs: dict[str, str]):
        connections = defaultdict(dict)

        # iterates over wf graph, Get connections from workflow graph, store connections in a dictionary
        for edge, props in workflow._graph.edges.items():
            src_node = edge[0].name
            dest_node = edge[1].name
            dest_node_fullname = workflow.get_node(dest_node).fullname
            for node_conn in props["connect"]:
                src_field = node_conn[0]
                dest_field = node_conn[1]
                if src_field.startswith("def"):
                    functions[dest_node_fullname][dest_field] = src_field
                else:
                    connections[dest_node_fullname][
                        dest_field
                    ] = f"{src_node}.lzout.{src_field}"

        for nested_wf in workflow._nested_workflows_cache:
            connections.update(self.node_connections(nested_wf, functions=functions))
        return connections


    def generate(self, format_with_black=False):

        functions = defaultdict(dict)
        connections = self.node_connections(self.wf, functions=functions)
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
                    if isinstance(val, str) and "\n" in val:
                        val = '"""' + val + '""""'
                    node_args += f",\n        {arg}={val}"

            for arg, val in connections[node.fullname].items():
                node_args += f",\n        {arg}=wf.{val}"

            out_text += f"""
    wf.add({task_type}(
        name="{node.name}"{node_args}
)"""

        if format_with_black:
            out_text = black.format_file_contents(
                out_text, fast=False, mode=black.FileMode()
            )
        return out_text

    @classmethod
    def _parse_workflow_args(cls, args):
        dct = {}
        for name, val in args.items():
            if isinstance(val, dict) and sorted(val.keys()) == ["args", "type"]:
                val = load_class_or_func(val["type"])(
                    **cls._parse_workflow_args(val["args"])
                )
            dct[name] = val
        return dct

    def save_graph(self, out_path: Path, format: str = "svg", work_dir: Path = None):
        if work_dir is None:
            work_dir = tempfile.mkdtemp()
        work_dir = Path(work_dir)
        graph_dot_path = work_dir / "wf-graph.dot"
        self.wf.write_hierarchical_dotfile(graph_dot_path)
        dot_path = sp.check_output("which dot", shell=True).decode("utf-8").strip()
        sp.check_call(
            f"{dot_path} -T{format} {str(graph_dot_path)} > {str(out_path)}", shell=True
        )
