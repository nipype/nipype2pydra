"""Module to put any functions that are referred to in the "callables" section of OutlierCount.yaml"""

import os.path as op


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def out_outliers_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_outliers"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L1848 of <nipype-install>/interfaces/afni/preprocess.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = op.abspath(inputs.out_file)
    if inputs.save_outliers:
        outputs["out_outliers"] = op.abspath(inputs.outliers_file)
    return outputs
