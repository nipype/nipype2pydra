"""Module to put any functions that are referred to in SphericalAverage.yaml"""

import os
import attrs


def in_average_callable(output_dir, inputs, stdout, stderr):
    return _gen_filename(
        "in_average", output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "in_average":
        avg_subject = str(inputs.hemisphere) + ".EC_average"
        avg_directory = os.path.join(inputs.subjects_dir, avg_subject)
        if not os.path.isdir(avg_directory):
            fs_home = os.path.abspath(os.environ.get("FREESURFER_HOME"))
        return avg_subject
    elif name == "out_file":
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    else:
        return None


class SphericalAverageOutputSpec(
    inputs=None, stdout=None, stderr=None, output_dir=None
):
    out_file = File(exists=False, desc="Output label")


def _outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    """Returns a bunch containing output fields for the class"""
    outputs = None
    if output_spec:
        outputs = output_spec(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )

    return outputs


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = _outputs(
        inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
    ).get()
    if inputs.out_file is not attrs.NOTHING:
        outputs["out_file"] = os.path.abspath(inputs.out_file)
    else:
        out_dir = os.path.join(inputs.subjects_dir, inputs.subject_id, "label")
        if inputs.in_average is not attrs.NOTHING:
            basename = os.path.basename(inputs.in_average)
            basename = basename.replace("_", "_exvivo_") + ".label"
        else:
            basename = str(inputs.hemisphere) + ".EC_exvivo_average.label"
        outputs["out_file"] = os.path.join(out_dir, basename)
    return outputs
