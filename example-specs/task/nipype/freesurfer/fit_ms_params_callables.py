"""Module to put any functions that are referred to in the "callables" section of FitMSParams.yaml"""

import attrs
import os


def out_dir_default(inputs):
    return _gen_filename("out_dir", inputs=inputs)


def t1_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["t1_image"]


def pd_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["pd_image"]


def t2star_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["t2star_image"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_dir":
        return output_dir
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.out_dir is attrs.NOTHING:
        out_dir = _gen_filename(
            "out_dir",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    else:
        out_dir = inputs.out_dir
    outputs["t1_image"] = os.path.join(out_dir, "T1.mgz")
    outputs["pd_image"] = os.path.join(out_dir, "PD.mgz")
    outputs["t2star_image"] = os.path.join(out_dir, "T2star.mgz")
    return outputs
