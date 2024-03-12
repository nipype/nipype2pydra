"""Module to put any functions that are referred to in the "callables" section of FLAMEO.yaml"""

import os
import re
from glob import glob
import attrs


def pes_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["pes"]


def res4d_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["res4d"]


def copes_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["copes"]


def var_copes_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["var_copes"]


def zstats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["zstats"]


def tstats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["tstats"]


def zfstats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["zfstats"]


def fstats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["fstats"]


def mrefvars_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["mrefvars"]


def tdof_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["tdof"]


def weights_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["weights"]


def stats_dir_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["stats_dir"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def human_order_sorted(l):
    """Sorts string in human order (i.e. 'stat10' will go after 'stat2')"""

    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(text):
        if isinstance(text, tuple):
            text = text[0]
        return [atoi(c) for c in re.split(r"(\d+)", text)]

    return sorted(l, key=natural_keys)


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    pth = os.path.join(output_dir, inputs.log_dir)

    pes = human_order_sorted(glob(os.path.join(pth, "pe[0-9]*.*")))
    assert len(pes) >= 1, "No pe volumes generated by FSL Estimate"
    outputs["pes"] = pes

    res4d = human_order_sorted(glob(os.path.join(pth, "res4d.*")))
    assert len(res4d) == 1, "No residual volume generated by FSL Estimate"
    outputs["res4d"] = res4d[0]

    copes = human_order_sorted(glob(os.path.join(pth, "cope[0-9]*.*")))
    assert len(copes) >= 1, "No cope volumes generated by FSL CEstimate"
    outputs["copes"] = copes

    var_copes = human_order_sorted(glob(os.path.join(pth, "varcope[0-9]*.*")))
    assert len(var_copes) >= 1, "No varcope volumes generated by FSL CEstimate"
    outputs["var_copes"] = var_copes

    zstats = human_order_sorted(glob(os.path.join(pth, "zstat[0-9]*.*")))
    assert len(zstats) >= 1, "No zstat volumes generated by FSL CEstimate"
    outputs["zstats"] = zstats

    if inputs.f_con_file is not attrs.NOTHING:
        zfstats = human_order_sorted(glob(os.path.join(pth, "zfstat[0-9]*.*")))
        assert len(zfstats) >= 1, "No zfstat volumes generated by FSL CEstimate"
        outputs["zfstats"] = zfstats

        fstats = human_order_sorted(glob(os.path.join(pth, "fstat[0-9]*.*")))
        assert len(fstats) >= 1, "No fstat volumes generated by FSL CEstimate"
        outputs["fstats"] = fstats

    tstats = human_order_sorted(glob(os.path.join(pth, "tstat[0-9]*.*")))
    assert len(tstats) >= 1, "No tstat volumes generated by FSL CEstimate"
    outputs["tstats"] = tstats

    mrefs = human_order_sorted(
        glob(os.path.join(pth, "mean_random_effects_var[0-9]*.*"))
    )
    assert len(mrefs) >= 1, "No mean random effects volumes generated by FLAMEO"
    outputs["mrefvars"] = mrefs

    tdof = human_order_sorted(glob(os.path.join(pth, "tdof_t[0-9]*.*")))
    assert len(tdof) >= 1, "No T dof volumes generated by FLAMEO"
    outputs["tdof"] = tdof

    weights = human_order_sorted(glob(os.path.join(pth, "weights[0-9]*.*")))
    assert len(weights) >= 1, "No weight volumes generated by FLAMEO"
    outputs["weights"] = weights

    outputs["stats_dir"] = pth

    return outputs
