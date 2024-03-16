"""Module to put any functions that are referred to in the "callables" section of MRIsInflate.yaml"""

import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def out_sulc_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_sulc"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L2392 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = os.path.abspath(inputs.out_file)
    if not inputs.no_save_sulc:
        # if the sulc file will be saved
        outputs["out_sulc"] = os.path.abspath(inputs.out_sulc)
    return outputs
