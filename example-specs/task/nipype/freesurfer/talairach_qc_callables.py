"""Module to put any functions that are referred to in the "callables" section of TalairachQC.yaml"""

import os


def log_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["log_file"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L216 of <nipype-install>/interfaces/freesurfer/base.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["log_file"] = os.path.abspath("output.nipype")
    return outputs
