"""Module to put any functions that are referred to in the "callables" section of SpatialNormalizationRPT.yaml"""


def composite_transform_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["composite_transform"]


def elapsed_time_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["elapsed_time"]


def forward_invert_flags_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["forward_invert_flags"]


def forward_transforms_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["forward_transforms"]


def inverse_composite_transform_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["inverse_composite_transform"]


def inverse_warped_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["inverse_warped_image"]


def metric_value_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["metric_value"]


def out_report_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_report"]


def reference_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reference_image"]


def reverse_forward_invert_flags_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reverse_forward_invert_flags"]


def reverse_forward_transforms_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reverse_forward_transforms"]


def reverse_invert_flags_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reverse_invert_flags"]


def reverse_transforms_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["reverse_transforms"]


def save_state_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["save_state"]


def warped_image_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["warped_image"]


# Original source at L419 of <nipype-install>/interfaces/base/core.py
def BaseInterface___list_outputs(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    """List the expected outputs"""
    if True:
        raise NotImplementedError
    else:
        return None


# Original source at L54 of <nipype-install>/interfaces/mixins/reporting.py
def ReportCapableInterface___list_outputs(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    try:
        outputs = BaseInterface___list_outputs()
    except NotImplementedError:
        outputs = {}
    if _out_report is not None:
        outputs["out_report"] = _out_report
    return outputs


# Original source at L54 of <nipype-install>/interfaces/mixins/reporting.py
def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    try:
        outputs = BaseInterface___list_outputs()
    except NotImplementedError:
        outputs = {}
    if _out_report is not None:
        outputs["out_report"] = _out_report
    return outputs


# Original source at L54 of <nipype-install>/interfaces/mixins/reporting.py
def niworkflows_interfaces_reportlets__RegistrationRC___list_outputs(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    try:
        outputs = BaseInterface___list_outputs()
    except NotImplementedError:
        outputs = {}
    if _out_report is not None:
        outputs["out_report"] = _out_report
    return outputs
