"""Module to put any functions that are referred to in the "callables" section of UploadIQMs.yaml"""


def api_id_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["api_id"]


# Original source at L568 of <nipype-install>/interfaces/base/core.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    return _results
