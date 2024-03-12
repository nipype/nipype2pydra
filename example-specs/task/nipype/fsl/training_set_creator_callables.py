"""Module to put any functions that are referred to in the "callables" section of TrainingSetCreator.yaml"""


def mel_icas_out_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mel_icas_out"]


def _gen_filename(field, inputs, output_dir, stdout, stderr):
    raise NotImplementedError(
        "Could not find '_gen_filename' method in nipype.interfaces.fsl.fix.TrainingSetCreator"
    )
