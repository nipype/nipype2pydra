"""Module to put any functions that are referred to in the "callables" section of AverageAffineTransform.yaml"""

import os


def affine_transform_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["affine_transform"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["affine_transform"] = os.path.abspath(inputs.output_affine_transform)
    return outputs
