"""Module to put any functions that are referred to in the "callables" section of CreateJacobianDeterminantImage.yaml"""

import os


def jacobian_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["jacobian_image"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L756 of <nipype-install>/interfaces/ants/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["jacobian_image"] = os.path.abspath(inputs.outputImage)
    return outputs
