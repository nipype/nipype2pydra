"""Module to put any functions that are referred to in the "callables" section of Synthesize.yaml"""

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


# Original source at L728 of <nipype-install>/interfaces/afni/model.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    for key in outputs.keys():
        if inputs.get()[key] is not attrs.NOTHING:
            outputs[key] = os.path.abspath(inputs.get()[key])

    return outputs
