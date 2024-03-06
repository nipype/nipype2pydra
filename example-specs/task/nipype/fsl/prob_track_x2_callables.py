"""Module to put any functions that are referred to in ProbTrackX2.yaml"""


def out_dir_callable(output_dir, inputs, stdout, stderr):
    return _gen_filename(
        "out_dir", output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_dir":
        return output_dir
    elif name == "mode":
        if isinstance(inputs.seed, list) and isinstance(inputs.seed[0], list):
            return "simple"
        else:
            return "seedmask"
