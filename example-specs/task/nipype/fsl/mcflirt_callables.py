"""Module to put any functions that are referred to in the "callables" section of MCFLIRT.yaml"""

import logging
from pathlib import Path
from looseversion import LooseVersion
from glob import glob
import os.path as op
from nibabel.loadsave import load
import attrs
import os


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def variance_img_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["variance_img"]


def std_img_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["std_img"]


def mean_img_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mean_img"]


def par_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["par_file"]


def mat_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mat_file"]


def rms_files_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["rms_files"]


IFLOGGER = logging.getLogger("nipype.interface")


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
    """
    Handle FSL ``output_type`` and version information.

    output type refers to the type of file fsl defaults to writing
    eg, NIFTI, NIFTI_GZ

    Examples
    --------

    >>> from nipype.interfaces.fsl import Info
    >>> Info.version()  # doctest: +SKIP
    >>> Info.output_type()  # doctest: +SKIP

    """

    ftypes = {
        "NIFTI": ".nii",
        "NIFTI_PAIR": ".img",
        "NIFTI_GZ": ".nii.gz",
        "NIFTI_PAIR_GZ": ".img.gz",
    }

    if os.getenv("FSLDIR"):
        version_file = os.path.join(os.getenv("FSLDIR"), "etc", "fslversion")

    @staticmethod
    def parse_version(raw_info):
        return raw_info.splitlines()[0]

    @classmethod
    def output_type_to_ext(cls, output_type):
        """Get the file extension for the given output type.

        Parameters
        ----------
        output_type : {'NIFTI', 'NIFTI_GZ', 'NIFTI_PAIR', 'NIFTI_PAIR_GZ'}
            String specifying the output type.

        Returns
        -------
        extension : str
            The file extension for the output type.
        """

        try:
            return cls.ftypes[output_type]
        except KeyError:
            msg = "Invalid FSLOUTPUTTYPE: ", output_type
            raise KeyError(msg)

    @classmethod
    def output_type(cls):
        """Get the global FSL output file type FSLOUTPUTTYPE.

        This returns the value of the environment variable
        FSLOUTPUTTYPE.  An exception is raised if it is not defined.

        Returns
        -------
        fsl_ftype : string
            Represents the current environment setting of FSLOUTPUTTYPE
        """
        try:
            return os.environ["FSLOUTPUTTYPE"]
        except KeyError:
            IFLOGGER.warning(
                "FSLOUTPUTTYPE environment variable is not set. "
                "Setting FSLOUTPUTTYPE=NIFTI"
            )
            return "NIFTI"

    @staticmethod
    def standard_image(img_name=None):
        """Grab an image from the standard location.

        Returns a list of standard images if called without arguments.

        Could be made more fancy to allow for more relocatability"""
        try:
            fsldir = os.environ["FSLDIR"]
        except KeyError:
            raise Exception("FSL environment variables not set")
        stdpath = os.path.join(fsldir, "data", "standard")
        if img_name is None:
            return [
                filename.replace(stdpath + "/", "")
                for filename in glob(os.path.join(stdpath, "*nii*"))
            ]
        return os.path.join(stdpath, img_name)


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
    """Generate a filename based on the given parameters.

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

    if basename == "":
        msg = "Unable to generate filename for command %s. " % "mcflirt"
        msg += "basename is not set!"
        raise ValueError(msg)
    if cwd is None:
        cwd = output_dir
    if ext is None:
        ext = Info.output_type_to_ext(inputs.output_type)
    if change_ext:
        if suffix:
            suffix = "".join((suffix, ext))
        else:
            suffix = ext
    if suffix is None:
        suffix = ""
    fname = fname_presuffix(basename, suffix=suffix, use_ext=False, newpath=cwd)
    return fname


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


class Info(PackageInfo):
    """
    Handle FSL ``output_type`` and version information.

    output type refers to the type of file fsl defaults to writing
    eg, NIFTI, NIFTI_GZ

    Examples
    --------

    >>> from nipype.interfaces.fsl import Info
    >>> Info.version()  # doctest: +SKIP
    >>> Info.output_type()  # doctest: +SKIP

    """

    ftypes = {
        "NIFTI": ".nii",
        "NIFTI_PAIR": ".img",
        "NIFTI_GZ": ".nii.gz",
        "NIFTI_PAIR_GZ": ".img.gz",
    }

    if os.getenv("FSLDIR"):
        version_file = os.path.join(os.getenv("FSLDIR"), "etc", "fslversion")

    @staticmethod
    def parse_version(raw_info):
        return raw_info.splitlines()[0]

    @classmethod
    def output_type_to_ext(cls, output_type):
        """Get the file extension for the given output type.

        Parameters
        ----------
        output_type : {'NIFTI', 'NIFTI_GZ', 'NIFTI_PAIR', 'NIFTI_PAIR_GZ'}
            String specifying the output type.

        Returns
        -------
        extension : str
            The file extension for the output type.
        """

        try:
            return cls.ftypes[output_type]
        except KeyError:
            msg = "Invalid FSLOUTPUTTYPE: ", output_type
            raise KeyError(msg)

    @classmethod
    def output_type(cls):
        """Get the global FSL output file type FSLOUTPUTTYPE.

        This returns the value of the environment variable
        FSLOUTPUTTYPE.  An exception is raised if it is not defined.

        Returns
        -------
        fsl_ftype : string
            Represents the current environment setting of FSLOUTPUTTYPE
        """
        try:
            return os.environ["FSLOUTPUTTYPE"]
        except KeyError:
            IFLOGGER.warning(
                "FSLOUTPUTTYPE environment variable is not set. "
                "Setting FSLOUTPUTTYPE=NIFTI"
            )
            return "NIFTI"

    @staticmethod
    def standard_image(img_name=None):
        """Grab an image from the standard location.

        Returns a list of standard images if called without arguments.

        Could be made more fancy to allow for more relocatability"""
        try:
            fsldir = os.environ["FSLDIR"]
        except KeyError:
            raise Exception("FSL environment variables not set")
        stdpath = os.path.join(fsldir, "data", "standard")
        if img_name is None:
            return [
                filename.replace(stdpath + "/", "")
                for filename in glob(os.path.join(stdpath, "*nii*"))
            ]
        return os.path.join(stdpath, img_name)


def _gen_outfilename(inputs=None, stdout=None, stderr=None, output_dir=None):
    out_file = inputs.out_file
    if out_file is not attrs.NOTHING:
        out_file = os.path.realpath(out_file)
    if (out_file is attrs.NOTHING) and (inputs.in_file is not attrs.NOTHING):
        out_file = _gen_fname(
            inputs.in_file,
            suffix="_mcf",
            inputs=inputs,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
    return os.path.abspath(out_file)


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _gen_outfilename(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}

    outputs["out_file"] = _gen_outfilename(
        inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
    )
    output_dir = os.path.dirname(outputs["out_file"])

    if (inputs.stats_imgs is not attrs.NOTHING) and inputs.stats_imgs:
        if LooseVersion(Info.version()) < LooseVersion("6.0.0"):
            # FSL <6.0 outputs have .nii.gz_variance.nii.gz as extension
            outputs["variance_img"] = _gen_fname(
                outputs["out_file"] + "_variance.ext",
                cwd=output_dir,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
            outputs["std_img"] = _gen_fname(
                outputs["out_file"] + "_sigma.ext",
                cwd=output_dir,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
        else:
            outputs["variance_img"] = _gen_fname(
                outputs["out_file"],
                suffix="_variance",
                cwd=output_dir,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
            outputs["std_img"] = _gen_fname(
                outputs["out_file"],
                suffix="_sigma",
                cwd=output_dir,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )

    # The mean image created if -stats option is specified ('meanvol')
    # is missing the top and bottom slices. Therefore we only expose the
    # mean image created by -meanvol option ('mean_reg') which isn't
    # corrupted.
    # Note that the same problem holds for the std and variance image.

    if (inputs.mean_vol is not attrs.NOTHING) and inputs.mean_vol:
        if LooseVersion(Info.version()) < LooseVersion("6.0.0"):
            # FSL <6.0 outputs have .nii.gz_mean_img.nii.gz as extension
            outputs["mean_img"] = _gen_fname(
                outputs["out_file"] + "_mean_reg.ext",
                cwd=output_dir,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
        else:
            outputs["mean_img"] = _gen_fname(
                outputs["out_file"],
                suffix="_mean_reg",
                cwd=output_dir,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )

    if (inputs.save_mats is not attrs.NOTHING) and inputs.save_mats:
        _, filename = os.path.split(outputs["out_file"])
        matpathname = os.path.join(output_dir, filename + ".mat")
        _, _, _, timepoints = load(inputs.in_file).shape
        outputs["mat_file"] = []
        for t in range(timepoints):
            outputs["mat_file"].append(os.path.join(matpathname, "MAT_%04d" % t))
    if (inputs.save_plots is not attrs.NOTHING) and inputs.save_plots:
        # Note - if e.g. out_file has .nii.gz, you get .nii.gz.par,
        # which is what mcflirt does!
        outputs["par_file"] = outputs["out_file"] + ".par"
    if (inputs.save_rms is not attrs.NOTHING) and inputs.save_rms:
        outfile = outputs["out_file"]
        outputs["rms_files"] = [outfile + "_abs.rms", outfile + "_rel.rms"]
    return outputs
