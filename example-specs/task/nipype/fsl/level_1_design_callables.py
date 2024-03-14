"""Module to put any functions that are referred to in the "callables" section of Level1Design.yaml"""

import attrs


def fsf_files_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fsf_files"]


def ev_files_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["ev_files"]


def _gen_filename(field, inputs, output_dir, stdout, stderr):
    raise NotImplementedError(
        "Could not find '_gen_filename' method in nipype.interfaces.fsl.model.Level1Design"
    )
