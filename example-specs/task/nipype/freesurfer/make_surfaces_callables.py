"""Module to put any functions that are referred to in the "callables" section of MakeSurfaces.yaml"""

import attrs
import os


def out_area_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_area"]


def out_cortex_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_cortex"]


def out_curv_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_curv"]


def out_pial_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_pial"]


def out_thickness_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_thickness"]


def out_white_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_white"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L2850 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    # Outputs are saved in the surf directory
    dest_dir = os.path.join(inputs.subjects_dir, inputs.subject_id, "surf")
    # labels are saved in the label directory
    label_dir = os.path.join(inputs.subjects_dir, inputs.subject_id, "label")
    if not inputs.no_white:
        outputs["out_white"] = os.path.join(dest_dir, str(inputs.hemisphere) + ".white")
    # The curv and area files must have the hemisphere names as a prefix
    outputs["out_curv"] = os.path.join(dest_dir, str(inputs.hemisphere) + ".curv")
    outputs["out_area"] = os.path.join(dest_dir, str(inputs.hemisphere) + ".area")
    # Something determines when a pial surface and thickness file is generated
    # but documentation doesn't say what.
    # The orig_pial input is just a guess
    if (inputs.orig_pial is not attrs.NOTHING) or inputs.white == "NOWRITE":
        outputs["out_curv"] = outputs["out_curv"] + ".pial"
        outputs["out_area"] = outputs["out_area"] + ".pial"
        outputs["out_pial"] = os.path.join(dest_dir, str(inputs.hemisphere) + ".pial")
        outputs["out_thickness"] = os.path.join(
            dest_dir, str(inputs.hemisphere) + ".thickness"
        )
    else:
        # when a pial surface is generated, the cortex label file is not
        # generated
        outputs["out_cortex"] = os.path.join(
            label_dir, str(inputs.hemisphere) + ".cortex.label"
        )
    return outputs
