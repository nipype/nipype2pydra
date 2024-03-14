"""Module to put any functions that are referred to in the "callables" section of L2Model.yaml"""

import attrs


def design_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["design_mat"]


def design_con_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["design_con"]


def design_grp_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["design_grp"]


def _gen_filename(field, inputs, output_dir, stdout, stderr):
    raise NotImplementedError(
        "Could not find '_gen_filename' method in nipype.interfaces.fsl.model.L2Model"
    )
