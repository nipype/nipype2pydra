"""Module to put any functions that are referred to in the "callables" section of Contrast.yaml"""

import os


def out_contrast_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_contrast"]


def out_stats_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_stats"]


def out_log_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_log"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    subject_dir = os.path.join(inputs.subjects_dir, inputs.subject_id)
    outputs["out_contrast"] = os.path.join(
        subject_dir, "surf", str(inputs.hemisphere) + ".w-g.pct.mgh"
    )
    outputs["out_stats"] = os.path.join(
        subject_dir, "stats", str(inputs.hemisphere) + ".w-g.pct.stats"
    )
    outputs["out_log"] = os.path.join(subject_dir, "scripts", "pctsurfcon.log")
    return outputs
