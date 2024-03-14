"""Module to put any functions that are referred to in the "callables" section of MRISPreprocReconAll.yaml"""

import attrs
import os


def out_file_default(inputs):
    return _gen_filename("out_file", inputs=inputs)


def out_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_file"]


# Original source at L144 of <nipype-install>/interfaces/freesurfer/model.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


# Original source at L134 of <nipype-install>/interfaces/freesurfer/model.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    outfile = inputs.out_file
    outputs["out_file"] = outfile
    if outfile is attrs.NOTHING:
        outputs["out_file"] = os.path.join(
            output_dir, "concat_%s_%s.mgz" % (inputs.hemi, inputs.target)
        )
    return outputs
