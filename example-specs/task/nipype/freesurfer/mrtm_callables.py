"""Module to put any functions that are referred to in the "callables" section of MRTM.yaml"""

import os.path as op
import attrs
import os


def glm_dir_default(inputs):
    return _gen_filename("glm_dir", inputs=inputs)


def glm_dir_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["glm_dir"]


def beta_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["beta_file"]


def error_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["error_file"]


def error_var_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["error_var_file"]


def error_stddev_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["error_stddev_file"]


def estimate_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["estimate_file"]


def mask_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mask_file"]


def fwhm_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fwhm_file"]


def dof_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["dof_file"]


def gamma_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["gamma_file"]


def gamma_var_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["gamma_var_file"]


def sig_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["sig_file"]


def ftest_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["ftest_file"]


def spatial_eigenvectors_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["spatial_eigenvectors"]


def frame_eigenvectors_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["frame_eigenvectors"]


def singular_values_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["singular_values"]


def svd_stats_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["svd_stats_file"]


def k2p_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["k2p_file"]


def bp_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["bp_file"]


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


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "glm_dir":
        return output_dir
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    # Get the top-level output directory
    if inputs.glm_dir is attrs.NOTHING:
        glmdir = output_dir
    else:
        glmdir = os.path.abspath(inputs.glm_dir)
    outputs["glm_dir"] = glmdir

    if inputs.nii_gz is not attrs.NOTHING:
        ext = "nii.gz"
    elif inputs.nii is not attrs.NOTHING:
        ext = "nii"
    else:
        ext = "mgh"

    # Assign the output files that always get created
    outputs["beta_file"] = os.path.join(glmdir, f"beta.{ext}")
    outputs["error_var_file"] = os.path.join(glmdir, f"rvar.{ext}")
    outputs["error_stddev_file"] = os.path.join(glmdir, f"rstd.{ext}")
    outputs["mask_file"] = os.path.join(glmdir, f"mask.{ext}")
    outputs["fwhm_file"] = os.path.join(glmdir, "fwhm.dat")
    outputs["dof_file"] = os.path.join(glmdir, "dof.dat")
    # Assign the conditional outputs
    if inputs.save_residual:
        outputs["error_file"] = os.path.join(glmdir, f"eres.{ext}")
    if inputs.save_estimate:
        outputs["estimate_file"] = os.path.join(glmdir, f"yhat.{ext}")
    if any((inputs.mrtm1, inputs.mrtm2, inputs.logan)):
        outputs["bp_file"] = os.path.join(glmdir, f"bp.{ext}")
    if inputs.mrtm1:
        outputs["k2p_file"] = os.path.join(glmdir, "k2prime.dat")

    # Get the contrast directory name(s)
    contrasts = []
    if inputs.contrast is not attrs.NOTHING:
        for c in inputs.contrast:
            if split_filename(c)[2] in [".mat", ".dat", ".mtx", ".con"]:
                contrasts.append(split_filename(c)[1])
            else:
                contrasts.append(os.path.split(c)[1])
    elif (inputs.one_sample is not attrs.NOTHING) and inputs.one_sample:
        contrasts = ["osgm"]

    # Add in the contrast images
    outputs["sig_file"] = [os.path.join(glmdir, c, f"sig.{ext}") for c in contrasts]
    outputs["ftest_file"] = [os.path.join(glmdir, c, f"F.{ext}") for c in contrasts]
    outputs["gamma_file"] = [os.path.join(glmdir, c, f"gamma.{ext}") for c in contrasts]
    outputs["gamma_var_file"] = [
        os.path.join(glmdir, c, f"gammavar.{ext}") for c in contrasts
    ]

    # Add in the PCA results, if relevant
    if (inputs.pca is not attrs.NOTHING) and inputs.pca:
        pcadir = os.path.join(glmdir, "pca-eres")
        outputs["spatial_eigenvectors"] = os.path.join(pcadir, f"v.{ext}")
        outputs["frame_eigenvectors"] = os.path.join(pcadir, "u.mtx")
        outputs["singluar_values"] = os.path.join(pcadir, "sdiag.mat")
        outputs["svd_stats_file"] = os.path.join(pcadir, "stats.dat")

    return outputs
