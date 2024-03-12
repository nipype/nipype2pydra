"""Module to put any functions that are referred to in the "callables" section of Curvature.yaml"""

import os


def out_mean_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_mean"]


def out_gauss_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_gauss"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.copy_input:
        in_file = os.path.basename(inputs.in_file)
    else:
        in_file = inputs.in_file
    outputs["out_mean"] = os.path.abspath(in_file) + ".H"
    outputs["out_gauss"] = os.path.abspath(in_file) + ".K"
    return outputs
