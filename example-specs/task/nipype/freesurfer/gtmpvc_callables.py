"""Module to put any functions that are referred to in the "callables" section of GTMPVC.yaml"""

import attrs
import os


def pvc_dir_default(inputs):
    return _gen_filename("pvc_dir", inputs=inputs)


def gtm_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["gtm_file"]


def gtm_stats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["gtm_stats"]


def hb_dat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["hb_dat"]


def hb_nifti_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["hb_nifti"]


def input_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["input_file"]


def mgx_ctxgm_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mgx_ctxgm"]


def mgx_gm_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mgx_gm"]


def mgx_subctxgm_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mgx_subctxgm"]


def nopvc_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["nopvc_file"]


def opt_params_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["opt_params"]


def pvc_dir_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["pvc_dir"]


def rbv_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["rbv"]


def ref_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["ref_file"]


def reg_anat2pet_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reg_anat2pet"]


def reg_anat2rbvpet_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reg_anat2rbvpet"]


def reg_pet2anat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reg_pet2anat"]


def reg_rbvpet2anat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reg_rbvpet2anat"]


def yhat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["yhat"]


def yhat0_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["yhat0"]


def yhat_full_fov_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["yhat_full_fov"]


def yhat_with_noise_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["yhat_with_noise"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L522 of <nipype-install>/interfaces/freesurfer/petsurfer.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    # Get the top-level output directory
    if inputs.pvc_dir is attrs.NOTHING:
        pvcdir = output_dir
    else:
        pvcdir = os.path.abspath(inputs.pvc_dir)
    outputs["pvc_dir"] = pvcdir

    # Assign the output files that always get created
    outputs["ref_file"] = os.path.join(pvcdir, "km.ref.tac.dat")
    outputs["hb_nifti"] = os.path.join(pvcdir, "km.hb.tac.nii.gz")
    outputs["hb_dat"] = os.path.join(pvcdir, "km.hb.tac.dat")
    outputs["nopvc_file"] = os.path.join(pvcdir, "nopvc.nii.gz")
    outputs["gtm_file"] = os.path.join(pvcdir, "gtm.nii.gz")
    outputs["gtm_stats"] = os.path.join(pvcdir, "gtm.stats.dat")
    outputs["reg_pet2anat"] = os.path.join(pvcdir, "aux", "bbpet2anat.lta")
    outputs["reg_anat2pet"] = os.path.join(pvcdir, "aux", "anat2bbpet.lta")

    # Assign the conditional outputs
    if inputs.save_input:
        outputs["input_file"] = os.path.join(pvcdir, "input.nii.gz")
    if inputs.save_yhat0:
        outputs["yhat0"] = os.path.join(pvcdir, "yhat0.nii.gz")
    if inputs.save_yhat:
        outputs["yhat"] = os.path.join(pvcdir, "yhat.nii.gz")
    if inputs.save_yhat_full_fov:
        outputs["yhat_full_fov"] = os.path.join(pvcdir, "yhat.fullfov.nii.gz")
    if inputs.save_yhat_with_noise:
        outputs["yhat_with_noise"] = os.path.join(pvcdir, "yhat.nii.gz")
    if inputs.mgx:
        outputs["mgx_ctxgm"] = os.path.join(pvcdir, "mgx.ctxgm.nii.gz")
        outputs["mgx_subctxgm"] = os.path.join(pvcdir, "mgx.subctxgm.nii.gz")
        outputs["mgx_gm"] = os.path.join(pvcdir, "mgx.gm.nii.gz")
    if inputs.rbv:
        outputs["rbv"] = os.path.join(pvcdir, "rbv.nii.gz")
        outputs["reg_rbvpet2anat"] = os.path.join(pvcdir, "aux", "rbv2anat.lta")
        outputs["reg_anat2rbvpet"] = os.path.join(pvcdir, "aux", "anat2rbv.lta")
    if inputs.opt:
        outputs["opt_params"] = os.path.join(pvcdir, "aux", "opt.params.dat")

    return outputs
