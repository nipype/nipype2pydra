"""Module to put any functions that are referred to in the "callables" section of SliceTimer.yaml"""

import attrs
from fileformats.generic import File
import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    return _gen_filename(
        "out_file", output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )["slice_time_corrected_file"]
    return None


def _outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    """Returns a bunch containing output fields for the class"""
    outputs = None
    if output_spec:
        outputs = output_spec(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )

    return outputs


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = _outputs(
        inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
    ).get()
    out_file = inputs.out_file
    if out_file is attrs.NOTHING:
        out_file = _gen_fname(
            inputs.in_file,
            suffix="_st",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    outputs["slice_time_corrected_file"] = os.path.abspath(out_file)
    return outputs


def _gen_fname(
    basename,
    cwd=None,
    suffix=None,
    change_ext=True,
    ext=None,
    inputs=None,
    stdout=None,
    stderr=None,
    output_dir=None,
):
    """Generate a filename based on the given parameters.

    The filename will take the form: cwd/basename<suffix><ext>.
    If change_ext is True, it will use the extensions specified in
    <instance>inputs.output_type.

    Parameters
    ----------
    basename : str
        Filename to base the new filename on.
    cwd : str
        Path to prefix to the new filename. (default is output_dir)
    suffix : str
        Suffix to add to the `basename`.  (defaults is '' )
    change_ext : bool
        Flag to change the filename extension to the FSL output type.
        (default True)

    Returns
    -------
    fname : str
        New filename based on given parameters.

    """

    if basename == "":
        msg = "Unable to generate filename for command %s. " % "slicetimer"
        msg += "basename is not set!"
        raise ValueError(msg)
    if cwd is None:
        cwd = output_dir
    if ext is None:
        ext = Info.output_type_to_ext(inputs.output_type)
    if change_ext:
        if suffix:
            suffix = "".join((suffix, ext))
        else:
            suffix = ext
    if suffix is None:
        suffix = ""
    fname = fname_presuffix(basename, suffix=suffix, use_ext=False, newpath=cwd)
    return fname


class SliceTimerOutputSpec(inputs=None, stdout=None, stderr=None, output_dir=None):
    slice_time_corrected_file = File(exists=True, desc="slice time corrected file")
