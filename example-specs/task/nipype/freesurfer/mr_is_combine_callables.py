"""Module to put any functions that are referred to in the "callables" section of MRIsCombine.yaml"""

import os


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    # mris_convert --combinesurfs uses lh. as the default prefix
    # regardless of input file names, except when path info is
    # specified
    path, base = os.path.split(inputs.out_file)
    if path == "" and base[:3] not in ("lh.", "rh."):
        base = "lh." + base
    outputs["out_file"] = os.path.abspath(os.path.join(path, base))

    return outputs
