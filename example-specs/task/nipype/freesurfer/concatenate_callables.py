"""Module to put any functions that are referred to in the "callables" section of Concatenate.yaml"""

import os
import attrs


def concatenated_file_default(inputs):
    return _gen_filename("concatenated_file", inputs=inputs)


def concatenated_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["concatenated_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "concatenated_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    fname = inputs.concatenated_file
    if fname is attrs.NOTHING:
        fname = "concat_output.nii.gz"
    outputs["concatenated_file"] = os.path.join(output_dir, fname)
    return outputs
