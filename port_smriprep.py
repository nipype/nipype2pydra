import json
from collections import defaultdict
import click
from bids import BIDSLayout
from nipype.interfaces.base import isdefined
from niworkflows.utils.spaces import SpatialReferences, Reference
from smriprep.workflows.base import init_single_subject_wf


@click.command("Print out auto-generated port of Nipype to Pydra")
@click.argument("out-file")
@click.argument("bids-dataset")
def port(out_file, bids_dataset):

    wf = build_workflow(bids_dataset)

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


def build_workflow(bids_dataset):

    wf = init_single_subject_wf(
        debug=False,
        freesurfer=True,
        fast_track=False,
        hires=True,
        layout=BIDSLayout(bids_dataset),
        longitudinal=False,
        low_mem=False,
        name="single_subject_wf",
        omp_nthreads=1,
        output_dir=".",
        skull_strip_fixed_seed=False,
        skull_strip_mode="force",
        skull_strip_template=Reference("OASIS30ANTs"),
        spaces=SpatialReferences(spaces=["MNI152NLin2009cAsym", "fsaverage5"]),
        subject_id="test",
        bids_filters=None,
    )

    return wf


if __name__ == "__main__":
    port()
