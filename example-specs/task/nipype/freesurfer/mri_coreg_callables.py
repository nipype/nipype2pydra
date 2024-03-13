"""Module to put any functions that are referred to in the "callables" section of MRICoreg.yaml"""

import attrs
import os


def out_reg_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_reg_file"]


def out_lta_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_lta_file"]


def out_params_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_params_file"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    out_lta_file = inputs.out_lta_file
    if out_lta_file is not attrs.NOTHING:
        if out_lta_file is True:
            out_lta_file = "registration.lta"
        outputs["out_lta_file"] = os.path.abspath(out_lta_file)

    out_reg_file = inputs.out_reg_file
    if out_reg_file is not attrs.NOTHING:
        if out_reg_file is True:
            out_reg_file = "registration.dat"
        outputs["out_reg_file"] = os.path.abspath(out_reg_file)

    out_params_file = inputs.out_params_file
    if out_params_file is not attrs.NOTHING:
        if out_params_file is True:
            out_params_file = "registration.par"
        outputs["out_params_file"] = os.path.abspath(out_params_file)

    return outputs
