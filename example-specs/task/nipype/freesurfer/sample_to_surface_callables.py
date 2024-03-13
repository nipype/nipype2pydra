"""Module to put any functions that are referred to in the "callables" section of SampleToSurface.yaml"""

from pathlib import Path
import os.path as op
import attrs
import os


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def hits_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["hits_file"]


def vox_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["vox_file"]


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


def _get_outfilename(
    opt="out_file", inputs=None, stdout=None, stderr=None, output_dir=None
):
    outfile = getattr(inputs, opt)
    if (outfile is attrs.NOTHING) or isinstance(outfile, bool):
        if inputs.out_type is not attrs.NOTHING:
            if opt == "hits_file":
                suffix = "_hits." + filemap[inputs.out_type]
            else:
                suffix = "." + filemap[inputs.out_type]
        elif opt == "hits_file":
            suffix = "_hits.mgz"
        else:
            suffix = ".mgz"
        outfile = fname_presuffix(
            inputs.source_file,
            newpath=output_dir,
            prefix=inputs.hemi + ".",
            suffix=suffix,
            use_ext=False,
        )
    return outfile


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = os.path.abspath(
        _get_outfilename(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )
    )
    hitsfile = inputs.hits_file
    if hitsfile is not attrs.NOTHING:
        outputs["hits_file"] = hitsfile
        if isinstance(hitsfile, bool):
            hitsfile = _get_outfilename(
                "hits_file",
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
    voxfile = inputs.vox_file
    if voxfile is not attrs.NOTHING:
        if isinstance(voxfile, bool):
            voxfile = fname_presuffix(
                inputs.source_file,
                newpath=output_dir,
                prefix=inputs.hemi + ".",
                suffix="_vox.txt",
                use_ext=False,
            )
        outputs["vox_file"] = voxfile
    return outputs
