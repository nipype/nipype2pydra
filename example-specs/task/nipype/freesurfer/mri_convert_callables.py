"""Module to put any functions that are referred to in the "callables" section of MRIConvert.yaml"""

from nibabel import load
import attrs
import os
import os.path as op
from pathlib import Path


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


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


# Original source at L550 of <nipype-install>/interfaces/freesurfer/preprocess.py
def _get_outfilename(inputs=None, stdout=None, stderr=None, output_dir=None):
    outfile = inputs.out_file
    if outfile is attrs.NOTHING:
        if inputs.out_type is not attrs.NOTHING:
            suffix = "_out." + filemap[inputs.out_type]
        else:
            suffix = "_out.nii.gz"
        outfile = fname_presuffix(
            inputs.in_file, newpath=output_dir, suffix=suffix, use_ext=False
        )
    return os.path.abspath(outfile)


# Original source at L603 of <nipype-install>/interfaces/freesurfer/preprocess.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _get_outfilename(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )
    return None


# Original source at L562 of <nipype-install>/interfaces/freesurfer/preprocess.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outfile = _get_outfilename(
        inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
    )
    if (inputs.split is not attrs.NOTHING) and inputs.split:
        size = load(inputs.in_file).shape
        if len(size) == 3:
            tp = 1
        else:
            tp = size[-1]
        if outfile.endswith(".mgz"):
            stem = outfile.split(".mgz")[0]
            ext = ".mgz"
        elif outfile.endswith(".nii.gz"):
            stem = outfile.split(".nii.gz")[0]
            ext = ".nii.gz"
        else:
            stem = ".".join(outfile.split(".")[:-1])
            ext = "." + outfile.split(".")[-1]
        outfile = []
        for idx in range(0, tp):
            outfile.append(stem + "%04d" % idx + ext)
    if inputs.out_type is not attrs.NOTHING:
        if inputs.out_type in ["spm", "analyze"]:
            # generate all outputs
            size = load(inputs.in_file).shape
            if len(size) == 3:
                tp = 1
            else:
                tp = size[-1]
                # have to take care of all the frame manipulations
                raise Exception(
                    "Not taking frame manipulations into account- please warn the developers"
                )
            outfiles = []
            outfile = _get_outfilename(
                inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
            )
            for i in range(tp):
                outfiles.append(fname_presuffix(outfile, suffix="%03d" % (i + 1)))
            outfile = outfiles
    outputs["out_file"] = outfile
    return outputs
