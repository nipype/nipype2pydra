"""Module to put any functions that are referred to in the "callables" section of MRIsExpand.yaml"""

import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


# Original source at L191 of <nipype-install>/interfaces/freesurfer/base.py
@staticmethod
def _associated_file(out_name, inputs=None, stdout=None, stderr=None, output_dir=None):
    """Based on MRIsBuildFileName in freesurfer/utils/mrisurf.c

    If no path information is provided for out_name, use path and
    hemisphere (if also unspecified) from in_file to determine the path
    of the associated file.
    Use in_file prefix to indicate hemisphere for out_name, rather than
    inspecting the surface data structure.
    """
    path, base = os.path.split(out_name)
    if path == "":
        path, in_file = os.path.split(in_file)
        hemis = ("lh.", "rh.")
        if in_file[:3] in hemis and base[:3] not in hemis:
            base = in_file[:3] + base
    return os.path.join(path, base)


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L4072 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = _associated_file(
        inputs.in_file,
        inputs.out_name,
        inputs=inputs,
        stdout=stdout,
        stderr=stderr,
        output_dir=output_dir,
    )
    return outputs
