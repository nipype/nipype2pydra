"""Module to put any functions that are referred to in the "callables" section of MultiplyImages.yaml"""

import os


def output_product_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["output_product_image"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["output_product_image"] = os.path.abspath(inputs.output_product_image)
    return outputs
