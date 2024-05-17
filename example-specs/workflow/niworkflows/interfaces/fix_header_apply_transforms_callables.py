"""Module to put any functions that are referred to in the "callables" section of FixHeaderApplyTransforms.yaml"""

import attrs
import os
from nipype.utils.filemanip import split_filename


def output_image_default(inputs):
    return _gen_filename("output_image", inputs=inputs)


def output_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["output_image"]


# Original source at L465 of <nipype-install>/interfaces/ants/resampling.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "output_image":
        output = inputs.output_image
        if output is attrs.NOTHING:
            _, name, ext = split_filename(inputs.input_image)
            output = name + inputs.out_postfix + ext
        return output
    return None


# Original source at L522 of <nipype-install>/interfaces/ants/resampling.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["output_image"] = os.path.abspath(
        _gen_filename(
            "output_image",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    )
    return outputs
