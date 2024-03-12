"""Module to put any functions that are referred to in the "callables" section of NwarpAdjust.yaml"""

import os
import os.path as op


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    if inputs.in_files:
        if inputs.out_file:
            outputs["out_file"] = os.path.abspath(inputs.out_file)
        else:
            basename = os.path.basename(inputs.in_files[0])
            basename_noext, ext = op.splitext(basename)
            if ".gz" in ext:
                basename_noext, ext2 = op.splitext(basename_noext)
                ext = ext2 + ext
            outputs["out_file"] = os.path.abspath(basename_noext + "_NwarpAdjust" + ext)
    return outputs
