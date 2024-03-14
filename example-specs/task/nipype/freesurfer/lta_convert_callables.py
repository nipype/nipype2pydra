"""Module to put any functions that are referred to in the "callables" section of LTAConvert.yaml"""

import os
import attrs


def out_lta_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_lta"]


def out_fsl_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_fsl"]


def out_mni_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_mni"]


def out_reg_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_reg"]


def out_itk_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_itk"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L4206 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    for name, default in (
        ("out_lta", "out.lta"),
        ("out_fsl", "out.mat"),
        ("out_mni", "out.xfm"),
        ("out_reg", "out.dat"),
        ("out_itk", "out.txt"),
    ):
        attr = getattr(inputs, name)
        if attr:
            fname = default if attr is True else attr
            outputs[name] = os.path.abspath(fname)

    return outputs
