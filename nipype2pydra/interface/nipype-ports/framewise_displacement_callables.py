"""Module to put any functions that are referred to in the "callables" section of FramewiseDisplacement.yaml"""


def fd_average_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fd_average"]


def out_figure_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_figure"]


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


# Original source at L390 of <nipype-install>/algorithms/confounds.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    return _results
