import json
from importlib import import_module
from collections import defaultdict
import click
from nipype.interfaces.base import isdefined


@click.command("Print out auto-generated port of Nipype to Pydra")
@click.argument("yaml-spec")
@click.argument("out-file")
@click.option('--output-required-tasks', type=click.File)
def workflow_converter(yaml_spec, out_file):

    wf = build_workflow(yaml_spec['workflow'])

    connections = defaultdict(dict)

    for edge, props in wf._graph.edges.items():
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

    out_text = ""
    for node_name in wf.list_node_names():
        node = wf.get_node(node_name)

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

    with open(out_file, "w") as f:
        f.write(out_text)


def build_workflow(spec):
    return load_class_or_func(spec['function'])(**_parse_args(spec['args']))


def load_class_or_func(location_str):
    module_str, name = location_str.split(':')
    module = import_module(module_str)
    return getattr(module, name)


def _parse_args(args):
    dct = {}
    for name, val in args.items():
        if isinstance(val, dict) and sorted(val.keys()) == ['type', 'args']:
            val = load_class_or_func(val['type'])(**_parse_args(val['args']))
        dct[name] = val
    return dct
