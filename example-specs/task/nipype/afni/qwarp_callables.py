"""Module to put any functions that are referred to in the "callables" section of Qwarp.yaml"""

from looseversion import LooseVersion
import attrs
import os
import os.path as op
from pathlib import Path


def warped_source_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["warped_source"]


def warped_base_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["warped_base"]


def source_warp_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["source_warp"]


def base_warp_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["base_warp"]


def weights_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["weights"]


# Original source at L1069 of <nipype-install>/interfaces/base/core.py
class PackageInfo(object):
    _version = None
    version_cmd = None
    version_file = None

    @classmethod
    def version(klass):
        if klass._version is None:
            if klass.version_cmd is not None:
                try:
                    clout = CommandLine(
                        command=klass.version_cmd,
                        resource_monitor=False,
                        terminal_output="allatonce",
                    ).run()
                except IOError:
                    return None

                raw_info = clout.runtime.stdout
            elif klass.version_file is not None:
                try:
                    with open(klass.version_file, "rt") as fobj:
                        raw_info = fobj.read()
                except OSError:
                    return None
            else:
                return None

            klass._version = klass.parse_version(raw_info)

        return klass._version

    @staticmethod
    def parse_version(raw_info):
        raise NotImplementedError


# Original source at L260 of <nipype-install>/interfaces/afni/base.py
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
    """
    Generate a filename based on the given parameters.

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
    if not basename:
        msg = "Unable to generate filename for command %s. " % "3dQwarp"
        msg += "basename is not set!"
        raise ValueError(msg)

    if cwd is None:
        cwd = output_dir
    if ext is None:
        ext = Info.output_type_to_ext(inputs.outputtype)
    if change_ext:
        suffix = "".join((suffix, ext)) if suffix else ext

    if suffix is None:
        suffix = ""
    fname = fname_presuffix(basename, suffix=suffix, use_ext=False, newpath=cwd)
    return fname


# Original source at L26 of <nipype-install>/interfaces/afni/base.py
class Info(PackageInfo):
    """Handle afni output type and version information."""

    __outputtype = "AFNI"
    ftypes = {"NIFTI": ".nii", "AFNI": "", "NIFTI_GZ": ".nii.gz"}
    version_cmd = "afni --version"

    @staticmethod
    def parse_version(raw_info):
        """Check and parse AFNI's version."""
        version_stamp = raw_info.split("\n")[0].split("Version ")[1]
        if version_stamp.startswith("AFNI"):
            version_stamp = version_stamp.split("AFNI_")[1]
        elif version_stamp.startswith("Debian"):
            version_stamp = version_stamp.split("Debian-")[1].split("~")[0]
        else:
            return None

        version = LooseVersion(version_stamp.replace("_", ".")).version[:3]
        if version[0] < 1000:
            version[0] = version[0] + 2000
        return tuple(version)

    @classmethod
    def output_type_to_ext(cls, outputtype):
        """
        Get the file extension for the given output type.

        Parameters
        ----------
        outputtype : {'NIFTI', 'NIFTI_GZ', 'AFNI'}
            String specifying the output type.

        Returns
        -------
        extension : str
            The file extension for the output type.

        """
        try:
            return cls.ftypes[outputtype]
        except KeyError as e:
            msg = "Invalid AFNIOUTPUTTYPE: ", outputtype
            raise KeyError(msg) from e

    @classmethod
    def outputtype(cls):
        """
        Set default output filetype.

        AFNI has no environment variables, Output filetypes get set in command line calls
        Nipype uses ``AFNI`` as default


        Returns
        -------
        None

        """
        return "AFNI"

    @staticmethod
    def standard_image(img_name):
        """
        Grab an image from the standard location.

        Could be made more fancy to allow for more relocatability

        """
        clout = CommandLine(
            "which afni",
            ignore_exception=True,
            resource_monitor=False,
            terminal_output="allatonce",
        ).run()
        if clout.runtime.returncode != 0:
            return None

        out = clout.runtime.stdout
        basedir = os.path.split(out)[0]
        return os.path.join(basedir, img_name)


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


# Original source at L4449 of <nipype-install>/interfaces/afni/preprocess.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _gen_fname(
            inputs.in_file,
            suffix="_QW",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )


# Original source at L4372 of <nipype-install>/interfaces/afni/preprocess.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    if inputs.out_file is attrs.NOTHING:
        prefix = _gen_fname(
            inputs.in_file,
            suffix="_QW",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
        outputtype = inputs.outputtype
        if outputtype == "AFNI":
            ext = ".HEAD"
            suffix = "+tlrc"
        else:
            ext = Info.output_type_to_ext(outputtype)
            suffix = ""
    else:
        prefix = inputs.out_file
        ext_ind = max([prefix.lower().rfind(".nii.gz"), prefix.lower().rfind(".nii")])
        if ext_ind == -1:
            ext = ".HEAD"
            suffix = "+tlrc"
        else:
            ext = prefix[ext_ind:]
            suffix = ""

    # All outputs should be in the same directory as the prefix
    out_dir = os.path.dirname(os.path.abspath(prefix))

    outputs["warped_source"] = (
        fname_presuffix(prefix, suffix=suffix, use_ext=False, newpath=out_dir) + ext
    )
    if not inputs.nowarp:
        outputs["source_warp"] = (
            fname_presuffix(
                prefix, suffix="_WARP" + suffix, use_ext=False, newpath=out_dir
            )
            + ext
        )
    if inputs.iwarp:
        outputs["base_warp"] = (
            fname_presuffix(
                prefix, suffix="_WARPINV" + suffix, use_ext=False, newpath=out_dir
            )
            + ext
        )
    if inputs.out_weight_file is not attrs.NOTHING:
        outputs["weights"] = os.path.abspath(inputs.out_weight_file)

    if inputs.plusminus:
        outputs["warped_source"] = (
            fname_presuffix(
                prefix, suffix="_PLUS" + suffix, use_ext=False, newpath=out_dir
            )
            + ext
        )
        outputs["warped_base"] = (
            fname_presuffix(
                prefix, suffix="_MINUS" + suffix, use_ext=False, newpath=out_dir
            )
            + ext
        )
        outputs["source_warp"] = (
            fname_presuffix(
                prefix, suffix="_PLUS_WARP" + suffix, use_ext=False, newpath=out_dir
            )
            + ext
        )
        outputs["base_warp"] = (
            fname_presuffix(
                prefix,
                suffix="_MINUS_WARP" + suffix,
                use_ext=False,
                newpath=out_dir,
            )
            + ext
        )
    return outputs
