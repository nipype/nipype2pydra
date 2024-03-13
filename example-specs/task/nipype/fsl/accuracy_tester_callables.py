"""Module to put any functions that are referred to in the "callables" section of AccuracyTester.yaml"""

from fileformats.generic import Directory
from traits.trait_errors import TraitError
from pathlib import Path
from traits.trait_type import TraitType
from traits.trait_base import _Undefined
import attrs


def output_directory_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["output_directory"]


Undefined = _Undefined()


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


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.output_directory is not attrs.NOTHING:
        outputs["output_directory"] = Directory(
            exists=False, value=inputs.output_directory
        )
    else:
        outputs["output_directory"] = Directory(exists=False, value="accuracy_test")
    return outputs
