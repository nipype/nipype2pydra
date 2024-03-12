"""Module to put any functions that are referred to in the "callables" section of RobustTemplate.yaml"""

import os
import attrs


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def transform_outputs_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["transform_outputs"]


def scaled_intensity_outputs_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["scaled_intensity_outputs"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = os.path.abspath(inputs.out_file)
    n_files = len(inputs.in_files)
    fmt = "{}{:02d}.{}" if n_files > 9 else "{}{:d}.{}"
    if inputs.transform_outputs is not attrs.NOTHING:
        fnames = inputs.transform_outputs
        if fnames is True:
            fnames = [fmt.format("tp", i + 1, "lta") for i in range(n_files)]
        outputs["transform_outputs"] = [os.path.abspath(x) for x in fnames]
    if inputs.scaled_intensity_outputs is not attrs.NOTHING:
        fnames = inputs.scaled_intensity_outputs
        if fnames is True:
            fnames = [fmt.format("is", i + 1, "txt") for i in range(n_files)]
        outputs["scaled_intensity_outputs"] = [os.path.abspath(x) for x in fnames]
    return outputs
