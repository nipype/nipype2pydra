"""Module to put any functions that are referred to in the "callables" section of NonSteadyStateDetector.yaml"""


def n_volumes_to_discard_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["n_volumes_to_discard"]


# Original source at L999 of <nipype-install>/algorithms/confounds.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    return _results
