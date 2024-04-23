"""Module to put any functions that are referred to in the "callables" section of TSNR.yaml"""

import os.path as op


def detrended_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["detrended_file"]


def mean_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mean_file"]


def stddev_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["stddev_file"]


def tsnr_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["tsnr_file"]


# Original source at L959 of <nipype-install>/algorithms/confounds.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    for k in ["tsnr_file", "mean_file", "stddev_file"]:
        outputs[k] = op.abspath(getattr(inputs, k))

    if inputs.regress_poly is not attrs.NOTHING:
        outputs["detrended_file"] = op.abspath(inputs.detrended_file)
    return outputs
