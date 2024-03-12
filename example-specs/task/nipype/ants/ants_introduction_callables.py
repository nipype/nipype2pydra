"""Module to put any functions that are referred to in the "callables" section of antsIntroduction.yaml"""

import os
import attrs


def affine_transformation_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["affine_transformation"]


def warp_field_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["warp_field"]


def inverse_warp_field_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["inverse_warp_field"]


def input_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["input_file"]


def output_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["output_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    transmodel = inputs.transformation_model

    # When transform is set as 'RI'/'RA', wrap fields should not be expected
    # The default transformation is GR, which outputs the wrap fields
    if (transmodel is attrs.NOTHING) or (
        (transmodel is not attrs.NOTHING) and transmodel not in ["RI", "RA"]
    ):
        outputs["warp_field"] = os.path.join(
            output_dir, inputs.out_prefix + "Warp.nii.gz"
        )
        outputs["inverse_warp_field"] = os.path.join(
            output_dir, inputs.out_prefix + "InverseWarp.nii.gz"
        )

    outputs["affine_transformation"] = os.path.join(
        output_dir, inputs.out_prefix + "Affine.txt"
    )
    outputs["input_file"] = os.path.join(
        output_dir, inputs.out_prefix + "repaired.nii.gz"
    )
    outputs["output_file"] = os.path.join(
        output_dir, inputs.out_prefix + "deformed.nii.gz"
    )

    return outputs
