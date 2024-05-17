"""Module to put any functions that are referred to in the "callables" section of ParseDICOMDir.yaml"""

import attrs
import os


def dicom_info_file_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["dicom_info_file"]


# Original source at L885 of <nipype-install>/interfaces/base/core.py
def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    raise NotImplementedError


# Original source at L83 of <nipype-install>/interfaces/freesurfer/preprocess.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.dicom_info_file is not attrs.NOTHING:
        outputs["dicom_info_file"] = os.path.join(output_dir, inputs.dicom_info_file)
    return outputs
