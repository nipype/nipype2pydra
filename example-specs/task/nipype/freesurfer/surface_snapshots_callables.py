"""Module to put any functions that are referred to in the "callables" section of SurfaceSnapshots.yaml"""


def tcl_script_callable(output_dir, inputs, stdout, stderr):
    return _gen_filename(
        "tcl_script", output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "tcl_script":
        return "snapshots.tcl"
    return None
