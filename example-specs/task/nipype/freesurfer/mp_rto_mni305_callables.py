"""Module to put any functions that are referred to in the "callables" section of MPRtoMNI305.yaml"""

import os
import os.path as op
import attrs


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def log_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["log_file"]


# Original source at L216 of <nipype-install>/interfaces/freesurfer/base.py
def nipype_interfaces_freesurfer__FSScriptCommand___list_outputs(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    outputs = {}
    outputs["log_file"] = os.path.abspath("output.nipype")
    return outputs


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


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


# Original source at L97 of <nipype-install>/interfaces/freesurfer/registration.py
def _get_fname(fname, inputs=None, stdout=None, stderr=None, output_dir=None):
    return split_filename(fname)[1]


# Original source at L100 of <nipype-install>/interfaces/freesurfer/registration.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = nipype_interfaces_freesurfer__FSScriptCommand___list_outputs()
    fullname = "_".join(
        [
            _get_fname(
                inputs.in_file,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            ),
            "to",
            inputs.target,
            "t4",
            "vox2vox.txt",
        ]
    )
    outputs["out_file"] = os.path.abspath(fullname)
    return outputs
