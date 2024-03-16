"""Module to put any functions that are referred to in the "callables" section of MRIMarchingCubes.yaml"""

import attrs
import os
import os.path as op


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def surface_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["surface"]


# Original source at L1647 of <nipype-install>/interfaces/freesurfer/utils.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _gen_outfilename(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )
    else:
        return None


# Original source at L1653 of <nipype-install>/interfaces/freesurfer/utils.py
def _gen_outfilename(inputs=None, stdout=None, stderr=None, output_dir=None):
    if inputs.out_file is not attrs.NOTHING:
        return os.path.abspath(inputs.out_file)
    else:
        _, name, ext = split_filename(inputs.in_file)
        return os.path.abspath(name + ext + "_" + str(inputs.label_value))


# Original source at L1642 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["surface"] = _gen_outfilename(
        inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
    )
    return outputs


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
