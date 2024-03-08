"""Module to put any functions that are referred to in the "callables" section of MRIsConvert.yaml"""

import attrs
import os.path as op
import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    return _gen_filename(
        "out_file", output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return os.path.abspath(
            _gen_outfilename(
                inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
            )
        )
    else:
        return None


def _gen_outfilename(inputs=None, stdout=None, stderr=None, output_dir=None):
    if inputs.out_file is not attrs.NOTHING:
        return inputs.out_file
    elif inputs.annot_file is not attrs.NOTHING:
        _, name, ext = split_filename(inputs.annot_file)
    elif inputs.parcstats_file is not attrs.NOTHING:
        _, name, ext = split_filename(inputs.parcstats_file)
    elif inputs.label_file is not attrs.NOTHING:
        _, name, ext = split_filename(inputs.label_file)
    elif inputs.scalarcurv_file is not attrs.NOTHING:
        _, name, ext = split_filename(inputs.scalarcurv_file)
    elif inputs.functional_file is not attrs.NOTHING:
        _, name, ext = split_filename(inputs.functional_file)
    elif inputs.in_file is not attrs.NOTHING:
        _, name, ext = split_filename(inputs.in_file)

    return name + ext + "_converted." + inputs.out_datatype


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