"""Module to put any functions that are referred to in the "callables" section of TOPUP.yaml"""

import attrs
import logging
from glob import glob
import os
import nibabel as nb
import os.path as op


def out_fieldcoef_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_fieldcoef"]


def out_movpar_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_movpar"]


def out_enc_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_enc_file"]


def out_field_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_field"]


def out_warps_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_warps"]


def out_jacs_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_jacs"]


def out_mats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_mats"]


def out_corrected_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_corrected"]


def out_logfile_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_logfile"]


IFLOGGER = logging.getLogger("nipype.interface")


iflogger = logging.getLogger("nipype.interface")


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


def nipype_interfaces_fsl__FSLCommand___overload_extension(
    value, name=None, inputs=None, stdout=None, stderr=None, output_dir=None
):
    return value + Info.output_type_to_ext(inputs.output_type)


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
        msg = "Unable to generate filename for command %s. " % "topup"
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
            retval = nipype_interfaces_fsl__FSLCommand___overload_extension(
                retval,
                name,
                inputs=inputs,
                stdout=stdout,
                stderr=stderr,
                output_dir=output_dir,
            )
    return retval


def nipype_interfaces_fsl__FSLCommand___list_outputs(
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


def _overload_extension(
    value, name=None, inputs=None, stdout=None, stderr=None, output_dir=None
):
    if name == "out_base":
        return value
    return nipype_interfaces_fsl__FSLCommand___overload_extension(value, name)


def _get_encfilename(inputs=None, stdout=None, stderr=None, output_dir=None):
    out_file = os.path.join(
        output_dir, ("%s_encfile.txt" % split_filename(inputs.in_file)[1])
    )
    return out_file


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = nipype_interfaces_fsl__FSLCommand___list_outputs()
    del outputs["out_base"]
    base_path = None
    if inputs.out_base is not attrs.NOTHING:
        base_path, base, _ = split_filename(inputs.out_base)
        if base_path == "":
            base_path = None
    else:
        base = split_filename(inputs.in_file)[1] + "_base"
    outputs["out_fieldcoef"] = _gen_fname(
        base,
        suffix="_fieldcoef",
        cwd=base_path,
        inputs=inputs,
        stdout=stdout,
        stderr=stderr,
        output_dir=output_dir,
    )
    outputs["out_movpar"] = _gen_fname(
        base,
        suffix="_movpar",
        ext=".txt",
        cwd=base_path,
        inputs=inputs,
        stdout=stdout,
        stderr=stderr,
        output_dir=output_dir,
    )

    n_vols = nb.load(inputs.in_file).shape[-1]
    ext = Info.output_type_to_ext(inputs.output_type)
    fmt = os.path.abspath("{prefix}_{i:02d}{ext}").format
    outputs["out_warps"] = [
        fmt(prefix=inputs.out_warp_prefix, i=i, ext=ext) for i in range(1, n_vols + 1)
    ]
    outputs["out_jacs"] = [
        fmt(prefix=inputs.out_jac_prefix, i=i, ext=ext) for i in range(1, n_vols + 1)
    ]
    outputs["out_mats"] = [
        fmt(prefix=inputs.out_mat_prefix, i=i, ext=".mat") for i in range(1, n_vols + 1)
    ]

    if inputs.encoding_direction is not attrs.NOTHING:
        outputs["out_enc_file"] = _get_encfilename(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )
    return outputs
