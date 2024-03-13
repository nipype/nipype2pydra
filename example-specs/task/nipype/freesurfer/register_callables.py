"""Module to put any functions that are referred to in the "callables" section of Register.yaml"""

import attrs
import os


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.out_file is not attrs.NOTHING:
        outputs["out_file"] = os.path.abspath(inputs.out_file)
    else:
        outputs["out_file"] = os.path.abspath(inputs.in_surf) + ".reg"
    return outputs
