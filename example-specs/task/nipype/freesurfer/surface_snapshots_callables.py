"""Module to put any functions that are referred to in the "callables" section of SurfaceSnapshots.yaml"""

import os.path as op
from pathlib import Path
import attrs


def tcl_script_default(inputs):
    return _gen_filename("tcl_script", inputs=inputs)


def snapshots_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["snapshots"]


# Original source at L108 of <nipype-install>/utils/filemanip.py
def fname_presuffix(fname, prefix="", suffix="", newpath=None, use_ext=True):
    """Manipulates path and name of input filename

    Parameters
    ----------
    fname : string
        A filename (may or may not include path)
    prefix : string
        Characters to prepend to the filename
    suffix : string
        Characters to append to the filename
    newpath : string
        Path to replace the path of the input fname
    use_ext : boolean
        If True (default), appends the extension of the original file
        to the output name.

    Returns
    -------
    Absolute path of the modified filename

    >>> from nipype.utils.filemanip import fname_presuffix
    >>> fname = 'foo.nii.gz'
    >>> fname_presuffix(fname,'pre','post','/tmp')
    '/tmp/prefoopost.nii.gz'

    >>> from nipype.interfaces.base import attrs.NOTHING
    >>> fname_presuffix(fname, 'pre', 'post', attrs.NOTHING) == \
            fname_presuffix(fname, 'pre', 'post')
    True

    """
    pth, fname, ext = split_filename(fname)
    if not use_ext:
        ext = ""

    # No need for : bool(attrs.NOTHING is not attrs.NOTHING) evaluates to False
    if newpath:
        pth = op.abspath(newpath)
    return op.join(pth, prefix + fname + suffix + ext)


# Original source at L58 of <nipype-install>/utils/filemanip.py
def split_filename(fname):
    """Split a filename into parts: path, base filename and extension.

    Parameters
    ----------
    fname : str
        file or path name

    Returns
    -------
    pth : str
        base path from fname
    fname : str
        filename from fname, without extension
    ext : str
        file extension from fname

    Examples
    --------
    >>> from nipype.utils.filemanip import split_filename
    >>> pth, fname, ext = split_filename('/home/data/subject.nii.gz')
    >>> pth
    '/home/data'

    >>> fname
    'subject'

    >>> ext
    '.nii.gz'

    """

    special_extensions = [".nii.gz", ".tar.gz", ".niml.dset"]

    pth = op.dirname(fname)
    fname = op.basename(fname)

    ext = None
    for special_ext in special_extensions:
        ext_len = len(special_ext)
        if (len(fname) > ext_len) and (fname[-ext_len:].lower() == special_ext.lower()):
            ext = fname[-ext_len:]
            fname = fname[:-ext_len]
            break
    if not ext:
        fname, ext = op.splitext(fname)

    return pth, fname, ext


# Original source at L151 of <nipype-install>/interfaces/freesurfer/base.py
def _gen_fname(
    basename,
    fname=None,
    cwd=None,
    suffix="_fs",
    use_ext=True,
    inputs=None,
    stdout=None,
    stderr=None,
    output_dir=None,
):
    """Define a generic mapping for a single outfile

    The filename is potentially autogenerated by suffixing inputs.infile

    Parameters
    ----------
    basename : string (required)
        filename to base the new filename on
    fname : string
        if not None, just use this fname
    cwd : string
        prefix paths with cwd, otherwise output_dir
    suffix : string
        default suffix
    """
    if basename == "":
        msg = "Unable to generate filename for command %s. " % "tksurfer"
        msg += "basename is not set!"
        raise ValueError(msg)
    if cwd is None:
        cwd = output_dir
    fname = fname_presuffix(basename, suffix=suffix, use_ext=use_ext, newpath=cwd)
    return fname


# Original source at L1106 of <nipype-install>/interfaces/freesurfer/utils.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "tcl_script":
        return "snapshots.tcl"
    return None


# Original source at L1085 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.screenshot_stem is attrs.NOTHING:
        stem = "%s_%s_%s" % (
            inputs.subject_id,
            inputs.hemi,
            inputs.surface,
        )
    else:
        stem = inputs.screenshot_stem
        stem_args = inputs.stem_template_args
        if stem_args is not attrs.NOTHING:
            args = tuple([getattr(inputs, arg) for arg in stem_args])
            stem = stem % args
    snapshots = ["%s-lat.tif", "%s-med.tif", "%s-dor.tif", "%s-ven.tif"]
    if inputs.six_images:
        snapshots.extend(["%s-pos.tif", "%s-ant.tif"])
    snapshots = [
        _gen_fname(
            f % stem,
            suffix="",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
        for f in snapshots
    ]
    outputs["snapshots"] = snapshots
    return outputs
