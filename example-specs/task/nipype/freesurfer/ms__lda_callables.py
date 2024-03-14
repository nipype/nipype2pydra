"""Module to put any functions that are referred to in the "callables" section of MS_LDA.yaml"""

import os
import attrs


def weight_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["weight_file"]


def vol_synth_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["vol_synth_file"]


# Original source at L1416 of <nipype-install>/interfaces/freesurfer/model.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    pass


# Original source at L1391 of <nipype-install>/interfaces/freesurfer/model.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.output_synth is not attrs.NOTHING:
        outputs["vol_synth_file"] = os.path.abspath(inputs.output_synth)
    else:
        outputs["vol_synth_file"] = os.path.abspath(inputs.vol_synth_file)
    if (inputs.use_weights is attrs.NOTHING) or inputs.use_weights is False:
        outputs["weight_file"] = os.path.abspath(inputs.weight_file)
    return outputs
