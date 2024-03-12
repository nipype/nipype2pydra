"""Module to put any functions that are referred to in the "callables" section of ParcellationStats.yaml"""

import os
import attrs


def out_table_default(inputs):
    return _gen_filename("out_table", inputs=inputs)


def out_color_default(inputs):
    return _gen_filename("out_color", inputs=inputs)


def out_table_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_table"]


def out_color_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_color"]


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name in ["out_table", "out_color"]:
        return _list_outputs(
            inputs=inputs, stdout=stdout, stderr=stderr, output_dir=output_dir
        )[name]
    return None


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = {}
    if inputs.out_table is not attrs.NOTHING:
        outputs["out_table"] = os.path.abspath(inputs.out_table)
    else:
        # subject stats directory
        stats_dir = os.path.join(inputs.subjects_dir, inputs.subject_id, "stats")
        if inputs.in_annotation is not attrs.NOTHING:
            # if out_table is not defined just tag .stats on the end
            # instead of .annot
            if inputs.surface == "pial":
                basename = os.path.basename(inputs.in_annotation).replace(
                    ".annot", ".pial.stats"
                )
            else:
                basename = os.path.basename(inputs.in_annotation).replace(
                    ".annot", ".stats"
                )
        elif inputs.in_label is not attrs.NOTHING:
            # if out_table is not defined just tag .stats on the end
            # instead of .label
            if inputs.surface == "pial":
                basename = os.path.basename(inputs.in_label).replace(
                    ".label", ".pial.stats"
                )
            else:
                basename = os.path.basename(inputs.in_label).replace(".label", ".stats")
        else:
            basename = str(inputs.hemisphere) + ".aparc.annot.stats"
        outputs["out_table"] = os.path.join(stats_dir, basename)
    if inputs.out_color is not attrs.NOTHING:
        outputs["out_color"] = os.path.abspath(inputs.out_color)
    else:
        # subject label directory
        out_dir = os.path.join(inputs.subjects_dir, inputs.subject_id, "label")
        if inputs.in_annotation is not attrs.NOTHING:
            # find the annotation name (if it exists)
            basename = os.path.basename(inputs.in_annotation)
            for item in ["lh.", "rh.", "aparc.", "annot"]:
                basename = basename.replace(item, "")
            annot = basename
            # if the out_color table is not defined, one with the annotation
            # name will be created
            if "BA" in annot:
                outputs["out_color"] = os.path.join(out_dir, annot + "ctab")
            else:
                outputs["out_color"] = os.path.join(
                    out_dir, "aparc.annot." + annot + "ctab"
                )
        else:
            outputs["out_color"] = os.path.join(out_dir, "aparc.annot.ctab")
    return outputs
