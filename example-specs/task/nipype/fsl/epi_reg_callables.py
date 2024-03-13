"""Module to put any functions that are referred to in the "callables" section of EpiReg.yaml"""

import attrs
import os


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


def out_1vol_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_1vol"]


def fmap2str_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fmap2str_mat"]


def fmap2epi_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fmap2epi_mat"]


def fmap_epi_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fmap_epi"]


def fmap_str_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fmap_str"]


def fmapmag_str_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fmapmag_str"]


def epi2str_inv_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi2str_inv"]


def epi2str_mat_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["epi2str_mat"]


def shiftmap_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["shiftmap"]


def fullwarp_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fullwarp"]


def wmseg_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["wmseg"]


def seg_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["seg"]


def wmedge_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["wmedge"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outputs["out_file"] = os.path.join(output_dir, inputs.out_base + ".nii.gz")
    if not ((inputs.no_fmapreg is not attrs.NOTHING) and inputs.no_fmapreg) and (
        inputs.fmap is not attrs.NOTHING
    ):
        outputs["out_1vol"] = os.path.join(output_dir, inputs.out_base + "_1vol.nii.gz")
        outputs["fmap2str_mat"] = os.path.join(
            output_dir, inputs.out_base + "_fieldmap2str.mat"
        )
        outputs["fmap2epi_mat"] = os.path.join(
            output_dir, inputs.out_base + "_fieldmaprads2epi.mat"
        )
        outputs["fmap_epi"] = os.path.join(
            output_dir, inputs.out_base + "_fieldmaprads2epi.nii.gz"
        )
        outputs["fmap_str"] = os.path.join(
            output_dir, inputs.out_base + "_fieldmaprads2str.nii.gz"
        )
        outputs["fmapmag_str"] = os.path.join(
            output_dir, inputs.out_base + "_fieldmap2str.nii.gz"
        )
        outputs["shiftmap"] = os.path.join(
            output_dir, inputs.out_base + "_fieldmaprads2epi_shift.nii.gz"
        )
        outputs["fullwarp"] = os.path.join(output_dir, inputs.out_base + "_warp.nii.gz")
        outputs["epi2str_inv"] = os.path.join(output_dir, inputs.out_base + "_inv.mat")
    if inputs.wmseg is attrs.NOTHING:
        outputs["wmedge"] = os.path.join(
            output_dir, inputs.out_base + "_fast_wmedge.nii.gz"
        )
        outputs["wmseg"] = os.path.join(
            output_dir, inputs.out_base + "_fast_wmseg.nii.gz"
        )
        outputs["seg"] = os.path.join(output_dir, inputs.out_base + "_fast_seg.nii.gz")
    outputs["epi2str_mat"] = os.path.join(output_dir, inputs.out_base + ".mat")
    return outputs
