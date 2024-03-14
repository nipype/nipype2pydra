"""Module to put any functions that are referred to in the "callables" section of FEATModel.yaml"""

import attrs
import os
from glob import glob


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


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L530 of <nipype-install>/utils/filemanip.py
def simplify_list(filelist):
    """Returns a list if filelist is a list of length greater than 1,
    otherwise returns the first element
    """
    if len(filelist) > 1:
        return filelist
    else:
        return filelist[0]


# Original source at L534 of <nipype-install>/interfaces/fsl/model.py
def _get_design_root(infile, inputs=None, stdout=None, stderr=None, output_dir=None):
    _, fname = os.path.split(infile)
    return fname.split(".")[0]


# Original source at L538 of <nipype-install>/interfaces/fsl/model.py
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
