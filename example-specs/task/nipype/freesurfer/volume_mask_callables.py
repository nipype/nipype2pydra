"""Module to put any functions that are referred to in the "callables" section of VolumeMask.yaml"""

import os
import attrs


def out_ribbon_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_ribbon"]


def lh_ribbon_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["lh_ribbon"]


def rh_ribbon_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["rh_ribbon"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L3326 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    out_dir = os.path.join(inputs.subjects_dir, inputs.subject_id, "mri")
    outputs["out_ribbon"] = os.path.join(out_dir, "ribbon.mgz")
    if inputs.save_ribbon:
        outputs["rh_ribbon"] = os.path.join(out_dir, "rh.ribbon.mgz")
        outputs["lh_ribbon"] = os.path.join(out_dir, "lh.ribbon.mgz")
    return outputs
