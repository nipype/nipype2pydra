"""Module to put any functions that are referred to in the "callables" section of FEATModel.yaml"""

from fileformats.generic import Directory
from traits.trait_errors import TraitError
from pathlib import Path
from fileformats.generic import File
from glob import glob
from traits.trait_type import TraitType
from traits.trait_base import _Undefined
import os


def design_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["design_file"]


def design_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["design_image"]


def design_cov_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["design_cov"]


def con_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["con_file"]


def fcon_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fcon_file"]


Undefined = _Undefined()


IMG_ZIP_FMT = set([".nii.gz", "tar.gz", ".gii.gz", ".mgz", ".mgh.gz", "img.gz"])


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


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


class Directory(BasePath):
    """
    Defines a trait whose value must be a directory path.

    >>> from nipype.interfaces.base import Directory, TraitedSpec, TraitError
    >>> class A(TraitedSpec):
    ...     foo = Directory(exists=False)
    >>> a = A()
    >>> a.foo
    <undefined>

    >>> a.foo = '/some/made/out/path'
    >>> a.foo
    '/some/made/out/path'

    >>> class A(TraitedSpec):
    ...     foo = Directory(exists=False, resolve=True)
    >>> a = A(foo='relative_dir')
    >>> a.foo  # doctest: +ELLIPSIS
    '.../relative_dir'

    >>> class A(TraitedSpec):
    ...     foo = Directory(exists=True, resolve=True)
    >>> a = A()
    >>> a.foo = 'relative_dir'  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    TraitError:

    >>> from os import mkdir
    >>> mkdir('relative_dir')
    >>> a.foo = 'relative_dir'
    >>> a.foo  # doctest: +ELLIPSIS
    '.../relative_dir'

    >>> class A(TraitedSpec):
    ...     foo = Directory(exists=True, resolve=False)
    >>> a = A(foo='relative_dir')
    >>> a.foo
    'relative_dir'

    >>> class A(TraitedSpec):
    ...     foo = Directory('tmpdir')
    >>> a = A()
    >>> a.foo  # doctest: +ELLIPSIS
    <undefined>

    >>> class A(TraitedSpec):
    ...     foo = Directory('tmpdir', usedefault=True)
    >>> a = A()
    >>> a.foo  # doctest: +ELLIPSIS
    'tmpdir'

    """

    _is_dir = True


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


def _resolve_with_filenotfound(path, **kwargs):
    """Raise FileNotFoundError instead of OSError"""
    try:
        return path.resolve(**kwargs)
    except OSError as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise FileNotFoundError(str(path))


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


def simplify_list(filelist):
    """Returns a list if filelist is a list of length greater than 1,
    otherwise returns the first element
    """
    if len(filelist) > 1:
        return filelist
    else:
        return filelist[0]


class FEATOutputSpec(TraitedSpec):
    feat_dir = Directory(exists=True)


class FEATInputSpec(FSLCommandInputSpec):
    fsf_file = File(
        exists=True,
        mandatory=True,
        argstr="%s",
        position=0,
        desc="File specifying the feat design spec file",
    )


class FEAT(FSLCommand):
    """Uses FSL feat to calculate first level stats"""

    _cmd = "feat"
    input_spec = FEATInputSpec
    output_spec = FEATOutputSpec

    def _list_outputs(self):
        outputs = self._outputs().get()
        is_ica = False
        outputs["feat_dir"] = None
        with open(self.inputs.fsf_file, "rt") as fp:
            text = fp.read()
            if "set fmri(inmelodic) 1" in text:
                is_ica = True
            for line in text.split("\n"):
                if line.find("set fmri(outputdir)") > -1:
                    try:
                        outputdir_spec = line.split('"')[-2]
                        if os.path.exists(outputdir_spec):
                            outputs["feat_dir"] = outputdir_spec

                    except:
                        pass
        if not outputs["feat_dir"]:
            if is_ica:
                outputs["feat_dir"] = glob(os.path.join(os.getcwd(), "*ica"))[0]
            else:
                outputs["feat_dir"] = glob(os.path.join(os.getcwd(), "*feat"))[0]
        return outputs


def _get_design_root(infile, inputs=None, stdout=None, stderr=None, output_dir=None):
    _, fname = os.path.split(infile)
    return fname.split(".")[0]


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    # TODO: figure out file names and get rid off the globs
    outputs = {}
    root = _get_design_root(
        simplify_list(inputs.fsf_file),
        inputs=inputs,
        stdout=stdout,
        stderr=stderr,
        output_dir=output_dir,
    )
    design_file = glob(os.path.join(output_dir, "%s*.mat" % root))
    assert len(design_file) == 1, "No mat file generated by FEAT Model"
    outputs["design_file"] = design_file[0]
    design_image = glob(os.path.join(output_dir, "%s.png" % root))
    assert len(design_image) == 1, "No design image generated by FEAT Model"
    outputs["design_image"] = design_image[0]
    design_cov = glob(os.path.join(output_dir, "%s_cov.png" % root))
    assert len(design_cov) == 1, "No covariance image generated by FEAT Model"
    outputs["design_cov"] = design_cov[0]
    con_file = glob(os.path.join(output_dir, "%s*.con" % root))
    assert len(con_file) == 1, "No con file generated by FEAT Model"
    outputs["con_file"] = con_file[0]
    fcon_file = glob(os.path.join(output_dir, "%s*.fts" % root))
    if fcon_file:
        assert len(fcon_file) == 1, "No fts file generated by FEAT Model"
        outputs["fcon_file"] = fcon_file[0]
    return outputs
