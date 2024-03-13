"""Module to put any functions that are referred to in the "callables" section of AlignEpiAnatPy.yaml"""

from looseversion import LooseVersion
from pathlib import Path
import os.path as op
import os


def anat_al_orig_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["anat_al_orig"]


def epi_al_orig_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_al_orig"]


def epi_tlrc_al_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_tlrc_al"]


def anat_al_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["anat_al_mat"]


def epi_al_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_al_mat"]


def epi_vr_al_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_vr_al_mat"]


def epi_reg_al_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_reg_al_mat"]


def epi_al_tlrc_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_al_tlrc_mat"]


def epi_vr_motion_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi_vr_motion"]


def skullstrip_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["skullstrip"]


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
        msg = "Unable to generate filename for command %s. " % "align_epi_anat.py"
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


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


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


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    anat_prefix = _gen_fname(
        inputs.anat, inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
    )
    epi_prefix = _gen_fname(
        inputs.in_file,
        inputs=inputs,
        stdout=stdout,
        stderr=stderr,
        output_dir=output_dir,
    )
    if "+" in anat_prefix:
        anat_prefix = "".join(anat_prefix.split("+")[:-1])
    if "+" in epi_prefix:
        epi_prefix = "".join(epi_prefix.split("+")[:-1])
    outputtype = inputs.outputtype
    if outputtype == "AFNI":
        ext = ".HEAD"
    else:
        ext = Info.output_type_to_ext(outputtype)
    matext = ".1D"
    suffix = inputs.suffix
    if inputs.anat2epi:
        outputs["anat_al_orig"] = _gen_fname(
            anat_prefix,
            suffix=suffix + "+orig",
            ext=ext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
        outputs["anat_al_mat"] = _gen_fname(
            anat_prefix,
            suffix=suffix + "_mat.aff12",
            ext=matext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    if inputs.epi2anat:
        outputs["epi_al_orig"] = _gen_fname(
            epi_prefix,
            suffix=suffix + "+orig",
            ext=ext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
        outputs["epi_al_mat"] = _gen_fname(
            epi_prefix,
            suffix=suffix + "_mat.aff12",
            ext=matext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    if inputs.volreg == "on":
        outputs["epi_vr_al_mat"] = _gen_fname(
            epi_prefix,
            suffix="_vr" + suffix + "_mat.aff12",
            ext=matext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
        if inputs.tshift == "on":
            outputs["epi_vr_motion"] = _gen_fname(
                epi_prefix,
                suffix="tsh_vr_motion",
                ext=matext,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
        elif inputs.tshift == "off":
            outputs["epi_vr_motion"] = _gen_fname(
                epi_prefix,
                suffix="vr_motion",
                ext=matext,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
    if inputs.volreg == "on" and inputs.epi2anat:
        outputs["epi_reg_al_mat"] = _gen_fname(
            epi_prefix,
            suffix="_reg" + suffix + "_mat.aff12",
            ext=matext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    if inputs.save_skullstrip:
        outputs.skullstrip = _gen_fname(
            anat_prefix,
            suffix="_ns" + "+orig",
            ext=ext,
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    return outputs
