"""Module to put any functions that are referred to in the "callables" section of OneDToolPy.yaml"""

import os
import attrs


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L2332 of <nipype-install>/interfaces/afni/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    if inputs.out_file is not attrs.NOTHING:
        outputs["out_file"] = os.path.join(output_dir, inputs.out_file)
    if inputs.show_cormat_warnings is not attrs.NOTHING:
        outputs["out_file"] = os.path.join(output_dir, inputs.show_cormat_warnings)
    if inputs.censor_motion is not attrs.NOTHING:
        outputs["out_file"] = os.path.join(
            output_dir, inputs.censor_motion[1] + "_censor.1D"
        )
    return outputs
