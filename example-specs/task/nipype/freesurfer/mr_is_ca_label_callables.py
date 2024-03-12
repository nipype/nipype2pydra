"""Module to put any functions that are referred to in the "callables" section of MRIsCALabel.yaml"""

import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    out_basename = os.path.basename(inputs.out_file)
    outputs["out_file"] = os.path.join(
        inputs.subjects_dir, inputs.subject_id, "label", out_basename
    )
    return outputs
