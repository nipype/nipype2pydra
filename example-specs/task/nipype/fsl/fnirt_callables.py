"""Module to put any functions that are referred to in the "callables" section of FNIRT.yaml"""

import logging
from traits.trait_errors import TraitError
from pathlib import Path
from fileformats.generic import File
from glob import glob
from traits.trait_type import TraitType
from traits.trait_base import _Undefined
import os.path as op
import attrs
import os


def warped_file_default(inputs):
    return _gen_filename("warped_file", inputs=inputs)


def log_file_default(inputs):
    return _gen_filename("log_file", inputs=inputs)


def fieldcoeff_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fieldcoeff_file"]


def warped_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["warped_file"]


def field_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["field_file"]


def jacobian_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["jacobian_file"]


def modulatedref_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["modulatedref_file"]


def out_intensitymap_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_intensitymap_file"]


def log_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["log_file"]


Undefined = _Undefined()


IMG_ZIP_FMT = set([".nii.gz", "tar.gz", ".gii.gz", ".mgz", ".mgh.gz", "img.gz"])


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
        msg = "Unable to generate filename for command %s. " % "fnirt"
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


class BasePath(TraitType):
    """Defines a trait whose value must be a valid filesystem path."""

    # A description of the type of value this trait accepts:
    exists = False
    resolve = False
    _is_file = False
    _is_dir = False

    @property
    def info_text(self):
        """Create the trait's general description."""
        info_text = "a pathlike object or string"
        if any((self.exists, self._is_file, self._is_dir)):
            info_text += " representing a"
            if self.exists:
                info_text += "n existing"
            if self._is_file:
                info_text += " file"
            elif self._is_dir:
                info_text += " directory"
            else:
                info_text += " file or directory"
        return info_text

    def __init__(self, value=attrs.NOTHING, exists=False, resolve=False, **metadata):
        """Create a BasePath trait."""
        self.exists = exists
        self.resolve = resolve
        super(BasePath, self).__init__(value, **metadata)

    def validate(self, objekt, name, value, return_pathlike=False):
        """Validate a value change."""
        try:
            value = Path(value)  # Use pathlib's validation
        except Exception:
            self.error(objekt, name, str(value))

        if self.exists:
            if not value.exists():
                self.error(objekt, name, str(value))

            if self._is_file and not value.is_file():
                self.error(objekt, name, str(value))

            if self._is_dir and not value.is_dir():
                self.error(objekt, name, str(value))

        if self.resolve:
            value = path_resolve(value, strict=self.exists)

        if not return_pathlike:
            value = str(value)

        return value


class File(BasePath):
    """
    Defines a trait whose value must be a file path.

    >>> from nipype.interfaces.base import File, TraitedSpec, TraitError
    >>> class A(TraitedSpec):
    ...     foo = File()
    >>> a = A()
    >>> a.foo
    <undefined>

    >>> a.foo = '/some/made/out/path/to/file'
    >>> a.foo
    '/some/made/out/path/to/file'

    >>> class A(TraitedSpec):
    ...     foo = File(exists=False, resolve=True)
    >>> a = A(foo='idontexist.txt')
    >>> a.foo  # doctest: +ELLIPSIS
    '.../idontexist.txt'

    >>> class A(TraitedSpec):
    ...     foo = File(exists=True, resolve=True)
    >>> a = A()
    >>> a.foo = 'idontexist.txt'  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    TraitError:

    >>> open('idoexist.txt', 'w').close()
    >>> a.foo = 'idoexist.txt'
    >>> a.foo  # doctest: +ELLIPSIS
    '.../idoexist.txt'

    >>> class A(TraitedSpec):
    ...     foo = File('idoexist.txt')
    >>> a = A()
    >>> a.foo
    <undefined>

    >>> class A(TraitedSpec):
    ...     foo = File('idoexist.txt', usedefault=True)
    >>> a = A()
    >>> a.foo
    'idoexist.txt'

    >>> class A(TraitedSpec):
    ...     foo = File(exists=True, resolve=True, extensions=['.txt', 'txt.gz'])
    >>> a = A()
    >>> a.foo = 'idoexist.badtxt'  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    TraitError:

    >>> a.foo = 'idoexist.txt'
    >>> a.foo  # doctest: +ELLIPSIS
    '.../idoexist.txt'

    >>> class A(TraitedSpec):
    ...     foo = File(extensions=['.nii', '.nii.gz'])
    >>> a = A()
    >>> a.foo = 'badext.txt'  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    TraitError:

    >>> class A(TraitedSpec):
    ...     foo = File(extensions=['.nii', '.nii.gz'])
    >>> a = A()
    >>> a.foo = 'goodext.nii'
    >>> a.foo
    'goodext.nii'

    >>> a = A()
    >>> a.foo = 'idontexist.000.nii'
    >>> a.foo  # doctest: +ELLIPSIS
    'idontexist.000.nii'

    >>> a = A()
    >>> a.foo = 'idontexist.000.nii.gz'
    >>> a.foo  # doctest: +ELLIPSIS
    'idontexist.000.nii.gz'

    """

    _is_file = True
    _exts = None

    def __init__(
        self,
        value=NoDefaultSpecified,
        exists=False,
        resolve=False,
        allow_compressed=True,
        extensions=None,
        **metadata
    ):
        """Create a File trait."""
        if extensions is not None:
            if isinstance(extensions, (bytes, str)):
                extensions = [extensions]

            if allow_compressed is False:
                extensions = list(set(extensions) - IMG_ZIP_FMT)

            self._exts = sorted(
                set(
                    [
                        ".%s" % ext if not ext.startswith(".") else ext
                        for ext in extensions
                    ]
                )
            )

        super(File, self).__init__(
            value=value,
            exists=exists,
            resolve=resolve,
            extensions=self._exts,
            **metadata
        )

    def validate(self, objekt, name, value, return_pathlike=False):
        """Validate a value change."""
        value = super(File, self).validate(objekt, name, value, return_pathlike=True)
        if self._exts:
            fname = value.name
            if not any((fname.endswith(e) for e in self._exts)):
                self.error(objekt, name, str(value))

        if not return_pathlike:
            value = str(value)

        return value


def path_resolve(path, strict=False):
    try:
        return _resolve_with_filenotfound(path, strict=strict)
    except TypeError:  # PY35
        pass

    path = path.absolute()
    if strict or path.exists():
        return _resolve_with_filenotfound(path)

    # This is a hacky shortcut, using path.absolute() unmodified
    # In cases where the existing part of the path contains a
    # symlink, different results will be produced
    return path


def _resolve_with_filenotfound(path, **kwargs):
    """Raise FileNotFoundError instead of OSError"""
    try:
        return path.resolve(**kwargs)
    except OSError as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise FileNotFoundError(str(path))


class FNIRTOutputSpec(TraitedSpec):
    fieldcoeff_file = File(exists=True, desc="file with field coefficients")
    warped_file = File(exists=True, desc="warped image")
    field_file = File(desc="file with warp field")
    jacobian_file = File(desc="file containing Jacobian of the field")
    modulatedref_file = File(desc="file containing intensity modulated --ref")
    out_intensitymap_file = traits.List(
        File,
        minlen=2,
        maxlen=2,
        desc="files containing info pertaining to intensity mapping",
    )
    log_file = File(desc="Name of log-file")


class FNIRTInputSpec(FSLCommandInputSpec):
    ref_file = File(
        exists=True, argstr="--ref=%s", mandatory=True, desc="name of reference image"
    )
    in_file = File(
        exists=True, argstr="--in=%s", mandatory=True, desc="name of input image"
    )
    affine_file = File(
        exists=True, argstr="--aff=%s", desc="name of file containing affine transform"
    )
    inwarp_file = File(
        exists=True,
        argstr="--inwarp=%s",
        desc="name of file containing initial non-linear warps",
    )
    in_intensitymap_file = traits.List(
        File(exists=True),
        argstr="--intin=%s",
        copyfile=False,
        minlen=1,
        maxlen=2,
        desc=(
            "name of file/files containing "
            "initial intensity mapping "
            "usually generated by previous "
            "fnirt run"
        ),
    )
    fieldcoeff_file = traits.Either(
        traits.Bool,
        File,
        argstr="--cout=%s",
        desc="name of output file with field coefficients or true",
    )
    warped_file = File(
        argstr="--iout=%s", desc="name of output image", genfile=True, hash_files=False
    )
    field_file = traits.Either(
        traits.Bool,
        File,
        argstr="--fout=%s",
        desc="name of output file with field or true",
        hash_files=False,
    )
    jacobian_file = traits.Either(
        traits.Bool,
        File,
        argstr="--jout=%s",
        desc=(
            "name of file for writing out the "
            "Jacobian of the field (for "
            "diagnostic or VBM purposes)"
        ),
        hash_files=False,
    )
    modulatedref_file = traits.Either(
        traits.Bool,
        File,
        argstr="--refout=%s",
        desc=(
            "name of file for writing out "
            "intensity modulated --ref (for "
            "diagnostic purposes)"
        ),
        hash_files=False,
    )
    out_intensitymap_file = traits.Either(
        traits.Bool,
        File,
        argstr="--intout=%s",
        desc=(
            "name of files for writing "
            "information pertaining to "
            "intensity mapping"
        ),
        hash_files=False,
    )
    log_file = File(
        argstr="--logout=%s", desc="Name of log-file", genfile=True, hash_files=False
    )
    config_file = traits.Either(
        traits.Enum("T1_2_MNI152_2mm", "FA_2_FMRIB58_1mm"),
        File(exists=True),
        argstr="--config=%s",
        desc="Name of config file specifying command line arguments",
    )
    refmask_file = File(
        exists=True,
        argstr="--refmask=%s",
        desc="name of file with mask in reference space",
    )
    inmask_file = File(
        exists=True,
        argstr="--inmask=%s",
        desc="name of file with mask in input image space",
    )
    skip_refmask = traits.Bool(
        argstr="--applyrefmask=0",
        xor=["apply_refmask"],
        desc="Skip specified refmask if set, default false",
    )
    skip_inmask = traits.Bool(
        argstr="--applyinmask=0",
        xor=["apply_inmask"],
        desc="skip specified inmask if set, default false",
    )
    apply_refmask = traits.List(
        traits.Enum(0, 1),
        argstr="--applyrefmask=%s",
        xor=["skip_refmask"],
        desc=("list of iterations to use reference mask on (1 to use, 0 to " "skip)"),
        sep=",",
    )
    apply_inmask = traits.List(
        traits.Enum(0, 1),
        argstr="--applyinmask=%s",
        xor=["skip_inmask"],
        desc="list of iterations to use input mask on (1 to use, 0 to skip)",
        sep=",",
    )
    skip_implicit_ref_masking = traits.Bool(
        argstr="--imprefm=0",
        desc=("skip implicit masking  based on value in --ref image. " "Default = 0"),
    )
    skip_implicit_in_masking = traits.Bool(
        argstr="--impinm=0",
        desc=("skip implicit masking  based on value in --in image. " "Default = 0"),
    )
    refmask_val = traits.Float(
        argstr="--imprefval=%f", desc="Value to mask out in --ref image. Default =0.0"
    )
    inmask_val = traits.Float(
        argstr="--impinval=%f", desc="Value to mask out in --in image. Default =0.0"
    )
    max_nonlin_iter = traits.List(
        traits.Int,
        argstr="--miter=%s",
        desc="Max # of non-linear iterations list, default [5, 5, 5, 5]",
        sep=",",
    )
    subsampling_scheme = traits.List(
        traits.Int,
        argstr="--subsamp=%s",
        desc="sub-sampling scheme, list, default [4, 2, 1, 1]",
        sep=",",
    )
    warp_resolution = traits.Tuple(
        traits.Int,
        traits.Int,
        traits.Int,
        argstr="--warpres=%d,%d,%d",
        desc=(
            "(approximate) resolution (in mm) of warp basis in x-, y- and "
            "z-direction, default 10, 10, 10"
        ),
    )
    spline_order = traits.Int(
        argstr="--splineorder=%d",
        desc="Order of spline, 2->Qadratic spline, 3->Cubic spline. Default=3",
    )
    in_fwhm = traits.List(
        traits.Int,
        argstr="--infwhm=%s",
        desc=(
            "FWHM (in mm) of gaussian smoothing kernel for input volume, "
            "default [6, 4, 2, 2]"
        ),
        sep=",",
    )
    ref_fwhm = traits.List(
        traits.Int,
        argstr="--reffwhm=%s",
        desc=(
            "FWHM (in mm) of gaussian smoothing kernel for ref volume, "
            "default [4, 2, 0, 0]"
        ),
        sep=",",
    )
    regularization_model = traits.Enum(
        "membrane_energy",
        "bending_energy",
        argstr="--regmod=%s",
        desc=(
            "Model for regularisation of warp-field [membrane_energy "
            "bending_energy], default bending_energy"
        ),
    )
    regularization_lambda = traits.List(
        traits.Float,
        argstr="--lambda=%s",
        desc=(
            "Weight of regularisation, default depending on --ssqlambda and "
            "--regmod switches. See user documentation."
        ),
        sep=",",
    )
    skip_lambda_ssq = traits.Bool(
        argstr="--ssqlambda=0",
        desc="If true, lambda is not weighted by current ssq, default false",
    )
    jacobian_range = traits.Tuple(
        traits.Float,
        traits.Float,
        argstr="--jacrange=%f,%f",
        desc="Allowed range of Jacobian determinants, default 0.01, 100.0",
    )
    derive_from_ref = traits.Bool(
        argstr="--refderiv",
        desc=("If true, ref image is used to calculate derivatives. " "Default false"),
    )
    intensity_mapping_model = traits.Enum(
        "none",
        "global_linear",
        "global_non_linear",
        "local_linear",
        "global_non_linear_with_bias",
        "local_non_linear",
        argstr="--intmod=%s",
        desc="Model for intensity-mapping",
    )
    intensity_mapping_order = traits.Int(
        argstr="--intorder=%d",
        desc="Order of poynomial for mapping intensities, default 5",
    )
    biasfield_resolution = traits.Tuple(
        traits.Int,
        traits.Int,
        traits.Int,
        argstr="--biasres=%d,%d,%d",
        desc=(
            "Resolution (in mm) of bias-field modelling local intensities, "
            "default 50, 50, 50"
        ),
    )
    bias_regularization_lambda = traits.Float(
        argstr="--biaslambda=%f",
        desc="Weight of regularisation for bias-field, default 10000",
    )
    skip_intensity_mapping = traits.Bool(
        argstr="--estint=0",
        xor=["apply_intensity_mapping"],
        desc="Skip estimate intensity-mapping default false",
    )
    apply_intensity_mapping = traits.List(
        traits.Enum(0, 1),
        argstr="--estint=%s",
        xor=["skip_intensity_mapping"],
        desc=(
            "List of subsampling levels to apply intensity mapping for "
            "(0 to skip, 1 to apply)"
        ),
        sep=",",
    )
    hessian_precision = traits.Enum(
        "double",
        "float",
        argstr="--numprec=%s",
        desc=("Precision for representing Hessian, double or float. " "Default double"),
    )


class FNIRT(FSLCommand):
    """FSL FNIRT wrapper for non-linear registration

    For complete details, see the `FNIRT Documentation.
    <https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FNIRT>`_

    Examples
    --------
    >>> from nipype.interfaces import fsl
    >>> from nipype.testing import example_data
    >>> fnt = fsl.FNIRT(affine_file=example_data('trans.mat'))
    >>> res = fnt.run(ref_file=example_data('mni.nii', in_file=example_data('structural.nii')) #doctest: +SKIP

    T1 -> Mni153

    >>> from nipype.interfaces import fsl
    >>> fnirt_mprage = fsl.FNIRT()
    >>> fnirt_mprage.inputs.in_fwhm = [8, 4, 2, 2]
    >>> fnirt_mprage.inputs.subsampling_scheme = [4, 2, 1, 1]

    Specify the resolution of the warps

    >>> fnirt_mprage.inputs.warp_resolution = (6, 6, 6)
    >>> res = fnirt_mprage.run(in_file='structural.nii', ref_file='mni.nii', warped_file='warped.nii', fieldcoeff_file='fieldcoeff.nii')#doctest: +SKIP

    We can check the command line and confirm that it's what we expect.

    >>> fnirt_mprage.cmdline  #doctest: +SKIP
    'fnirt --cout=fieldcoeff.nii --in=structural.nii --infwhm=8,4,2,2 --ref=mni.nii --subsamp=4,2,1,1 --warpres=6,6,6 --iout=warped.nii'

    """

    _cmd = "fnirt"
    input_spec = FNIRTInputSpec
    output_spec = FNIRTOutputSpec

    filemap = {
        "warped_file": "warped",
        "field_file": "field",
        "jacobian_file": "field_jacobian",
        "modulatedref_file": "modulated",
        "out_intensitymap_file": "intmap",
        "log_file": "log.txt",
        "fieldcoeff_file": "fieldwarp",
    }

    def _list_outputs(self):
        outputs = self.output_spec().get()
        for key, suffix in list(self.filemap.items()):
            inval = getattr(self.inputs, key)
            change_ext = True
            if key in ["warped_file", "log_file"]:
                if suffix.endswith(".txt"):
                    change_ext = False
                if inval is not attrs.NOTHING:
                    outputs[key] = os.path.abspath(inval)
                else:
                    outputs[key] = self._gen_fname(
                        self.inputs.in_file, suffix="_" + suffix, change_ext=change_ext
                    )
            elif inval is not attrs.NOTHING:
                if isinstance(inval, bool):
                    if inval:
                        outputs[key] = self._gen_fname(
                            self.inputs.in_file,
                            suffix="_" + suffix,
                            change_ext=change_ext,
                        )
                else:
                    outputs[key] = os.path.abspath(inval)

            if key == "out_intensitymap_file" and (outputs[key] is not attrs.NOTHING):
                basename = FNIRT.intensitymap_file_basename(outputs[key])
                outputs[key] = [outputs[key], "%s.txt" % basename]
        return outputs

    def _format_arg(self, name, spec, value):
        if name in ("in_intensitymap_file", "out_intensitymap_file"):
            if name == "out_intensitymap_file":
                value = self._list_outputs()[name]
            value = [FNIRT.intensitymap_file_basename(v) for v in value]
            assert len(set(value)) == 1, "Found different basenames for {}: {}".format(
                name, value
            )
            return spec.argstr % value[0]
        if name in list(self.filemap.keys()):
            return spec.argstr % self._list_outputs()[name]
        return super(FNIRT, self)._format_arg(name, spec, value)

    def _gen_filename(self, name):
        if name in ["warped_file", "log_file"]:
            return self._list_outputs()[name]
        return None

    def write_config(self, configfile):
        """Writes out currently set options to specified config file

        XX TODO : need to figure out how the config file is written

        Parameters
        ----------
        configfile : /path/to/configfile
        """
        try:
            fid = open(configfile, "w+")
        except IOError:
            print("unable to create config_file %s" % (configfile))

        for item in list(self.inputs.get().items()):
            fid.write("%s\n" % (item))
        fid.close()

    @classmethod
    def intensitymap_file_basename(cls, f):
        """Removes valid intensitymap extensions from `f`, returning a basename
        that can refer to both intensitymap files.
        """
        for ext in list(Info.ftypes.values()) + [".txt"]:
            if f.endswith(ext):
                return f[: -len(ext)]
        # TODO consider warning for this case
        return f


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name in ["warped_file", "log_file"]:
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    for key, suffix in list(filemap.items()):
        inval = getattr(inputs, key)
        change_ext = True
        if key in ["warped_file", "log_file"]:
            if suffix.endswith(".txt"):
                change_ext = False
            if inval is not attrs.NOTHING:
                outputs[key] = os.path.abspath(inval)
            else:
                outputs[key] = _gen_fname(
                    inputs.in_file,
                    suffix="_" + suffix,
                    change_ext=change_ext,
                    inputs=inputs,
                    stdout=stdout,
                    stderr=stderr,
                    output_dir=output_dir,
                )
        elif inval is not attrs.NOTHING:
            if isinstance(inval, bool):
                if inval:
                    outputs[key] = _gen_fname(
                        inputs.in_file,
                        suffix="_" + suffix,
                        change_ext=change_ext,
                        inputs=inputs,
                        stdout=stdout,
                        stderr=stderr,
                        output_dir=output_dir,
                    )
            else:
                outputs[key] = os.path.abspath(inval)

        if key == "out_intensitymap_file" and (outputs[key] is not attrs.NOTHING):
            basename = FNIRT.intensitymap_file_basename(outputs[key])
            outputs[key] = [outputs[key], "%s.txt" % basename]
    return outputs
