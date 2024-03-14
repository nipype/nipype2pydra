"""Module to put any functions that are referred to in the "callables" section of SurfaceTransform.yaml"""

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


filemap = dict(
    cor="cor",
    mgh="mgh",
    mgz="mgz",
    minc="mnc",
    afni="brik",
    brik="brik",
    bshort="bshort",
    spm="img",
    analyze="img",
    analyze4d="img",
    bfloat="bfloat",
    nifti1="img",
    nii="nii",
    niigz="nii.gz",
    gii="gii",
)


# Original source at L663 of <nipype-install>/interfaces/freesurfer/utils.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


# Original source at L613 of <nipype-install>/interfaces/freesurfer/utils.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = inputs.out_file
    if outputs["out_file"] is attrs.NOTHING:
        if inputs.source_file is not attrs.NOTHING:
            source = inputs.source_file
        else:
            source = inputs.source_annot_file

        # Some recon-all files don't have a proper extension (e.g. "lh.thickness")
        # so we have to account for that here
        bad_extensions = [
            ".%s" % e
            for e in [
                "area",
                "mid",
                "pial",
                "avg_curv",
                "curv",
                "inflated",
                "jacobian_white",
                "orig",
                "nofix",
                "smoothwm",
                "crv",
                "sphere",
                "sulc",
                "thickness",
                "volume",
                "white",
            ]
        ]
        use_ext = True
        if split_filename(source)[2] in bad_extensions:
            source = source + ".stripme"
            use_ext = False
        ext = ""
        if inputs.target_type is not attrs.NOTHING:
            ext = "." + filemap[inputs.target_type]
            use_ext = False
        outputs["out_file"] = fname_presuffix(
            source,
            suffix=".%s%s" % (inputs.target_subject, ext),
            newpath=output_dir,
            use_ext=use_ext,
        )
    else:
        outputs["out_file"] = os.path.abspath(inputs.out_file)
    return outputs


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
