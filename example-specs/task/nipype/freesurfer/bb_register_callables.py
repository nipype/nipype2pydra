"""Module to put any functions that are referred to in the "callables" section of BBRegister.yaml"""

import os.path as op
from pathlib import Path
import attrs


def out_reg_file_default(inputs):
    return _gen_filename("out_reg_file", inputs=inputs)


def out_reg_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_reg_file"]


def out_fsl_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_fsl_file"]


def out_lta_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_lta_file"]


def min_cost_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["min_cost_file"]


def init_cost_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["init_cost_file"]


def registered_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["registered_file"]


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


# Original source at L1894 of <nipype-install>/interfaces/freesurfer/preprocess.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_reg_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


# Original source at L1835 of <nipype-install>/interfaces/freesurfer/preprocess.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    _in = inputs

    if _in.out_reg_file is not attrs.NOTHING:
        outputs["out_reg_file"] = op.abspath(_in.out_reg_file)
    elif _in.source_file:
        suffix = "_bbreg_%s.dat" % _in.subject_id
        outputs["out_reg_file"] = fname_presuffix(
            _in.source_file, suffix=suffix, use_ext=False
        )

    if _in.registered_file is not attrs.NOTHING:
        if isinstance(_in.registered_file, bool):
            outputs["registered_file"] = fname_presuffix(
                _in.source_file, suffix="_bbreg"
            )
        else:
            outputs["registered_file"] = op.abspath(_in.registered_file)

    if _in.out_lta_file is not attrs.NOTHING:
        if isinstance(_in.out_lta_file, bool):
            suffix = "_bbreg_%s.lta" % _in.subject_id
            out_lta_file = fname_presuffix(
                _in.source_file, suffix=suffix, use_ext=False
            )
            outputs["out_lta_file"] = out_lta_file
        else:
            outputs["out_lta_file"] = op.abspath(_in.out_lta_file)

    if _in.out_fsl_file is not attrs.NOTHING:
        if isinstance(_in.out_fsl_file, bool):
            suffix = "_bbreg_%s.mat" % _in.subject_id
            out_fsl_file = fname_presuffix(
                _in.source_file, suffix=suffix, use_ext=False
            )
            outputs["out_fsl_file"] = out_fsl_file
        else:
            outputs["out_fsl_file"] = op.abspath(_in.out_fsl_file)

    if _in.init_cost_file is not attrs.NOTHING:
        if isinstance(_in.out_fsl_file, bool):
            outputs["init_cost_file"] = outputs["out_reg_file"] + ".initcost"
        else:
            outputs["init_cost_file"] = op.abspath(_in.init_cost_file)

    outputs["min_cost_file"] = outputs["out_reg_file"] + ".mincost"
    return outputs
