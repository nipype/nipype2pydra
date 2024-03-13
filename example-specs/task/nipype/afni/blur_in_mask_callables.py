"""Module to put any functions that are referred to in the "callables" section of BlurInMask.yaml"""

from looseversion import LooseVersion
import logging
import os.path as op
import attrs
import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


iflogger = logging.getLogger("nipype.interface")


class NipypeInterfaceError(Exception):
    """Custom error for interfaces"""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "{}".format(self.value)


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


def _filename_from_source(
    name, chain=None, inputs=None, stdout=None, stderr=None, output_dir=None
):
    if chain is None:
        chain = []

    trait_spec = inputs.trait(name)
    retval = getattr(inputs, name)
    source_ext = None
    if (retval is attrs.NOTHING) or "%s" in retval:
        if not trait_spec.name_source:
            return retval

        # Do not generate filename when excluded by other inputs
        if any(
            (getattr(inputs, field) is not attrs.NOTHING)
            for field in trait_spec.xor or ()
        ):
            return retval

        # Do not generate filename when required fields are missing
        if not all(
            (getattr(inputs, field) is not attrs.NOTHING)
            for field in trait_spec.requires or ()
        ):
            return retval

        if (retval is not attrs.NOTHING) and "%s" in retval:
            name_template = retval
        else:
            name_template = trait_spec.name_template
        if not name_template:
            name_template = "%s_generated"

        ns = trait_spec.name_source
        while isinstance(ns, (list, tuple)):
            if len(ns) > 1:
                iflogger.warning("Only one name_source per trait is allowed")
            ns = ns[0]

        if not isinstance(ns, (str, bytes)):
            raise ValueError(
                "name_source of '{}' trait should be an input trait "
                "name, but a type {} object was found".format(name, type(ns))
            )

        if getattr(inputs, ns) is not attrs.NOTHING:
            name_source = ns
            source = getattr(inputs, name_source)
            while isinstance(source, list):
                source = source[0]

            # special treatment for files
            try:
                _, base, source_ext = split_filename(source)
            except (AttributeError, TypeError):
                base = source
        else:
            if name in chain:
                raise NipypeInterfaceError("Mutually pointing name_sources")

            chain.append(name)
            base = _filename_from_source(
                ns,
                chain,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
            if base is not attrs.NOTHING:
                _, _, source_ext = split_filename(base)
            else:
                # Do not generate filename when required fields are missing
                return retval

        chain = None
        retval = name_template % base
        _, _, ext = split_filename(retval)
        if trait_spec.keep_extension and (ext or source_ext):
            if (ext is None or not ext) and source_ext:
                retval = retval + source_ext
        else:
            retval = _overload_extension(
                retval,
                name,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
    return retval


def nipype_interfaces_afni__AFNICommandBase___list_outputs(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    metadata = dict(name_source=lambda t: t is not None)
    traits = inputs.traits(**metadata)
    if traits:
        outputs = {}
        for name, trait_spec in list(traits.items()):
            out_name = name
            if trait_spec.output_name is not None:
                out_name = trait_spec.output_name
            fname = _filename_from_source(
                name, inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
            )
            if fname is not attrs.NOTHING:
                outputs[out_name] = os.path.abspath(fname)
        return outputs


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


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


def _overload_extension(
    value, name=None, inputs=None, stdout=None, stderr=None, output_dir=None
):
    path, base, _ = split_filename(value)
    return os.path.join(path, base + Info.output_type_to_ext(inputs.outputtype))


def nipype_interfaces_afni__AFNICommand___list_outputs(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    outputs = nipype_interfaces_afni__AFNICommandBase___list_outputs()
    metadata = dict(name_source=lambda t: t is not None)
    out_names = list(inputs.traits(**metadata).keys())
    if out_names:
        for name in out_names:
            if outputs[name]:
                _, _, ext = split_filename(outputs[name])
                if ext == "":
                    outputs[name] = outputs[name] + "+orig.BRIK"
    return outputs


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = nipype_interfaces_afni__AFNICommandBase___list_outputs()
    metadata = dict(name_source=lambda t: t is not None)
    out_names = list(inputs.traits(**metadata).keys())
    if out_names:
        for name in out_names:
            if outputs[name]:
                _, _, ext = split_filename(outputs[name])
                if ext == "":
                    outputs[name] = outputs[name] + "+orig.BRIK"
    return outputs
