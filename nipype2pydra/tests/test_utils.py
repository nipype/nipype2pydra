from nipype2pydra.utils import (
    extract_args,
    get_source_code,
    split_source_into_statements,
)
from nipype2pydra.testing import test_line_number_of_function


def test_split_parens_contents1():
    assert extract_args(
        "def foo(a, b, c):\n    return a",
    ) == ("def foo(", ["a", "b", "c"], "):\n    return a")


def test_split_parens_contents2():
    assert extract_args(
        "foo(a, 'b, c')",
    ) == ("foo(", ["a", "'b, c'"], ")")


def test_split_parens_contents2a():
    assert extract_args(
        'foo(a, "b, c")',
    ) == ("foo(", ["a", '"b, c"'], ")")


def test_split_parens_contents2b():
    assert extract_args("foo(a, 'b, \"c')") == ("foo(", ["a", "'b, \"c'"], ")")


def test_split_parens_contents3():
    assert extract_args(
        "foo(a, bar(b, c))",
    ) == ("foo(", ["a", "bar(b, c)"], ")")


def test_split_parens_contents3a():
    assert extract_args(
        "foo(a, bar[b, c])",
    ) == ("foo(", ["a", "bar[b, c]"], ")")


def test_split_parens_contents3b():
    assert extract_args(
        "foo(a, bar([b, c]))",
    ) == ("foo(", ["a", "bar([b, c])"], ")")


def test_split_parens_contents5():
    assert extract_args(
        "foo(a, '\"b\"', c)",
    ) == ("foo(", ["a", "'\"b\"'", "c"], ")")


def test_split_parens_contents6():
    assert extract_args(
        r"foo(a, '\'b\'', c)",
    ) == ("foo(", ["a", r"'\'b\''", "c"], ")")


def test_split_parens_contents6a():
    assert extract_args(
        r"foo(a, '\'b\', c')",
    ) == ("foo(", ["a", r"'\'b\', c'"], ")")


def test_split_parens_contents7():
    assert extract_args(
        '"""Module explanation"""\ndef foo(a, b, c)',
    ) == ('"""Module explanation"""\ndef foo(', ["a", "b", "c"], ")")


def test_split_parens_contents8():
    assert extract_args(
        """related_filetype_sets = [(".hdr", ".img", ".mat"), (".nii", ".mat"), (".BRIK", ".HEAD")]""",
    ) == (
        "related_filetype_sets = [",
        ['(".hdr", ".img", ".mat")', '(".nii", ".mat")', '(".BRIK", ".HEAD")'],
        "]",
    )


def test_split_parens_contents9():
    assert extract_args('foo(cwd=bar("tmpdir"), basename="maskexf")') == (
        "foo(",
        ['cwd=bar("tmpdir")', 'basename="maskexf"'],
        ")",
    )


def test_source_code():
    assert get_source_code(test_line_number_of_function).splitlines()[:2] == [
        "# Original source at L1 of <nipype2pydra-install>/testing.py",
        "def test_line_number_of_function():",
    ]

    # \"\"\"
    # One-subject-one-session-one-run pipeline to extract the NR-IQMs from
    # anatomical images

    # .. workflow::

    #     import os.path as op
    #     from mriqc.workflows.anatomical.base import anat_qc_workflow
    #     from mriqc.testing import mock_config
    #     with mock_config():
    #         wf = anat_qc_workflow()

    # \"\"\"


EXAMPLE_SOURCE_CODE = """
    from mriqc.workflows.shared import synthstrip_wf

    dataset = config.workflow.inputs.get('t1w', []) + config.workflow.inputs.get('t2w', [])

    message = BUILDING_WORKFLOW.format(
        modality='anatomical',
        detail=(
            f'for {len(dataset)} NIfTI files.'
            if len(dataset) > 2
            else f"({' and '.join('<%s>' % v for v in dataset)})."
        ),
    )
    config.loggers.workflow.info(message)

    # Initialize workflow
    workflow = pe.Workflow(name=name)

    # Define workflow, inputs and outputs
    # 0. Get data
    inputnode = pe.Node(niu.IdentityInterface(fields=['in_file']), name='inputnode')
    inputnode.iterables = [('in_file', dataset)]

    datalad_get = pe.Node(
        DataladIdentityInterface(fields=['in_file'], dataset_path=config.execution.bids_dir),
        name='datalad_get',
    )

    outputnode = pe.Node(niu.IdentityInterface(fields=['out_json']), name='outputnode')

    # 1. Reorient anatomical image
    to_ras = pe.Node(ConformImage(check_dtype=False), name='conform')
    # 2. species specific skull-stripping
    if config.workflow.species.lower() == 'human':
        skull_stripping = synthstrip_wf(omp_nthreads=config.nipype.omp_nthreads)
        ss_bias_field = 'outputnode.bias_image'
    else:
        from nirodents.workflows.brainextraction import init_rodent_brain_extraction_wf

        skull_stripping = init_rodent_brain_extraction_wf(template_id=config.workflow.template_id)
        ss_bias_field = 'final_n4.bias_image'
    # 3. Head mask
    hmsk = headmsk_wf(omp_nthreads=config.nipype.omp_nthreads)
    # 4. Spatial Normalization, using ANTs
    norm = spatial_normalization()
    # 5. Air mask (with and without artifacts)
    amw = airmsk_wf()
    # 6. Brain tissue segmentation
    bts = init_brain_tissue_segmentation()
    # 7. Compute IQMs
    iqmswf = compute_iqms()
    # Reports
    anat_report_wf = init_anat_report_wf()

    # Connect all nodes
    # fmt: off
    workflow.connect([
        (inputnode, datalad_get, [('in_file', 'in_file')]),
        (inputnode, anat_report_wf, [
            ('in_file', 'inputnode.name_source'),
        ]),
        (datalad_get, to_ras, [('in_file', 'in_file')]),
        (datalad_get, iqmswf, [('in_file', 'inputnode.in_file')]),
        (datalad_get, norm, [(('in_file', _get_mod), 'inputnode.modality')]),
        (to_ras, skull_stripping, [('out_file', 'inputnode.in_files')]),
        (skull_stripping, hmsk, [
            ('outputnode.out_corrected', 'inputnode.in_file'),
            ('outputnode.out_mask', 'inputnode.brainmask'),
        ]),
        (skull_stripping, bts, [('outputnode.out_mask', 'inputnode.brainmask')]),
        (skull_stripping, norm, [
            ('outputnode.out_corrected', 'inputnode.moving_image'),
            ('outputnode.out_mask', 'inputnode.moving_mask')]),
        (norm, bts, [('outputnode.out_tpms', 'inputnode.std_tpms')]),
        (norm, amw, [
            ('outputnode.ind2std_xfm', 'inputnode.ind2std_xfm')]),
        (norm, iqmswf, [
            ('outputnode.out_tpms', 'inputnode.std_tpms')]),
        (norm, anat_report_wf, ([
            ('outputnode.out_report', 'inputnode.mni_report')])),
        (norm, hmsk, [('outputnode.out_tpms', 'inputnode.in_tpms')]),
        (to_ras, amw, [('out_file', 'inputnode.in_file')]),
        (skull_stripping, amw, [('outputnode.out_mask', 'inputnode.in_mask')]),
        (hmsk, amw, [('outputnode.out_file', 'inputnode.head_mask')]),
        (to_ras, iqmswf, [('out_file', 'inputnode.in_ras')]),
        (skull_stripping, iqmswf, [('outputnode.out_corrected', 'inputnode.inu_corrected'),
                                   (ss_bias_field, 'inputnode.in_inu'),
                                   ('outputnode.out_mask', 'inputnode.brainmask')]),
        (amw, iqmswf, [('outputnode.air_mask', 'inputnode.airmask'),
                       ('outputnode.hat_mask', 'inputnode.hatmask'),
                       ('outputnode.art_mask', 'inputnode.artmask'),
                       ('outputnode.rot_mask', 'inputnode.rotmask')]),
        (hmsk, bts, [('outputnode.out_denoised', 'inputnode.in_file')]),
        (bts, iqmswf, [('outputnode.out_segm', 'inputnode.segmentation'),
                       ('outputnode.out_pvms', 'inputnode.pvms')]),
        (hmsk, iqmswf, [('outputnode.out_file', 'inputnode.headmask')]),
        (to_ras, anat_report_wf, [('out_file', 'inputnode.in_ras')]),
        (skull_stripping, anat_report_wf, [
            ('outputnode.out_corrected', 'inputnode.inu_corrected'),
            ('outputnode.out_mask', 'inputnode.brainmask')]),
        (hmsk, anat_report_wf, [('outputnode.out_file', 'inputnode.headmask')]),
        (amw, anat_report_wf, [
            ('outputnode.air_mask', 'inputnode.airmask'),
            ('outputnode.art_mask', 'inputnode.artmask'),
            ('outputnode.rot_mask', 'inputnode.rotmask'),
        ]),
        (bts, anat_report_wf, [('outputnode.out_segm', 'inputnode.segmentation')]),
        (iqmswf, anat_report_wf, [('outputnode.noisefit', 'inputnode.noisefit')]),
        (iqmswf, anat_report_wf, [('outputnode.out_file', 'inputnode.in_iqms')]),
        (iqmswf, outputnode, [('outputnode.out_file', 'out_json')]),
    ])
    # fmt: on

    # Upload metrics
    if not config.execution.no_sub:
        from mriqc.interfaces.webapi import UploadIQMs

        upldwf = pe.Node(
            UploadIQMs(
                endpoint=config.execution.webapi_url,
                auth_token=config.execution.webapi_token,
                strict=config.execution.upload_strict,
            ),
            name='UploadMetrics',
        )

        # fmt: off
        workflow.connect([
            (iqmswf, upldwf, [('outputnode.out_file', 'in_iqms')]),
            (upldwf, anat_report_wf, [('api_id', 'inputnode.api_id')]),
        ])

    # fmt: on

    return workflow
"""


EXAMPLE_SOURCE_CODE_SPLIT = [
    # """    \"\"\"
    # One-subject-one-session-one-run pipeline to extract the NR-IQMs from
    # anatomical images
    # .. workflow::
    #     import os.path as op
    #     from mriqc.workflows.anatomical.base import anat_qc_workflow
    #     from mriqc.testing import mock_config
    #     with mock_config():
    #         wf = anat_qc_workflow()
    # \"\"\"""",
    "",
    "    from mriqc.workflows.shared import synthstrip_wf",
    "",
    "    dataset = config.workflow.inputs.get('t1w', []) + config.workflow.inputs.get('t2w', [])",
    "",
    """    message = BUILDING_WORKFLOW.format(modality='anatomical', detail=(
            f'for {len(dataset)} NIfTI files.'
            if len(dataset) > 2
            else f"({' and '.join('<%s>' % v for v in dataset)})."
        ))""",
    "    config.loggers.workflow.info(message)",
    "",
    "    # Initialize workflow",
    "    workflow = pe.Workflow(name=name)",
    "",
    "    # Define workflow, inputs and outputs",
    "    # 0. Get data",
    "    inputnode = pe.Node(niu.IdentityInterface(fields=['in_file']), name='inputnode')",
    "    inputnode.iterables = [('in_file', dataset)]",
    "",
    """    datalad_get = pe.Node(DataladIdentityInterface(fields=['in_file'], dataset_path=config.execution.bids_dir), name='datalad_get')""",
    "",
    "    outputnode = pe.Node(niu.IdentityInterface(fields=['out_json']), name='outputnode')",
    "",
    "    # 1. Reorient anatomical image",
    "    to_ras = pe.Node(ConformImage(check_dtype=False), name='conform')",
    "    # 2. species specific skull-stripping",
    "    if config.workflow.species.lower() == 'human':",
    "        skull_stripping = synthstrip_wf(omp_nthreads=config.nipype.omp_nthreads)",
    "        ss_bias_field = 'outputnode.bias_image'",
    "    else:",
    "        from nirodents.workflows.brainextraction import init_rodent_brain_extraction_wf",
    "",
    "        skull_stripping = init_rodent_brain_extraction_wf(template_id=config.workflow.template_id)",
    "        ss_bias_field = 'final_n4.bias_image'",
    "    # 3. Head mask",
    "    hmsk = headmsk_wf(omp_nthreads=config.nipype.omp_nthreads)",
    "    # 4. Spatial Normalization, using ANTs",
    "    norm = spatial_normalization()",
    "    # 5. Air mask (with and without artifacts)",
    "    amw = airmsk_wf()",
    "    # 6. Brain tissue segmentation",
    "    bts = init_brain_tissue_segmentation()",
    "    # 7. Compute IQMs",
    "    iqmswf = compute_iqms()",
    "    # Reports",
    "    anat_report_wf = init_anat_report_wf()",
    "",
    "    # Connect all nodes",
    "    # fmt: off",
    """    workflow.connect([
        (inputnode, datalad_get, [('in_file', 'in_file')]),
        (inputnode, anat_report_wf, [
            ('in_file', 'inputnode.name_source'),
        ]),
        (datalad_get, to_ras, [('in_file', 'in_file')]),
        (datalad_get, iqmswf, [('in_file', 'inputnode.in_file')]),
        (datalad_get, norm, [(('in_file', _get_mod), 'inputnode.modality')]),
        (to_ras, skull_stripping, [('out_file', 'inputnode.in_files')]),
        (skull_stripping, hmsk, [
            ('outputnode.out_corrected', 'inputnode.in_file'),
            ('outputnode.out_mask', 'inputnode.brainmask'),
        ]),
        (skull_stripping, bts, [('outputnode.out_mask', 'inputnode.brainmask')]),
        (skull_stripping, norm, [
            ('outputnode.out_corrected', 'inputnode.moving_image'),
            ('outputnode.out_mask', 'inputnode.moving_mask')]),
        (norm, bts, [('outputnode.out_tpms', 'inputnode.std_tpms')]),
        (norm, amw, [
            ('outputnode.ind2std_xfm', 'inputnode.ind2std_xfm')]),
        (norm, iqmswf, [
            ('outputnode.out_tpms', 'inputnode.std_tpms')]),
        (norm, anat_report_wf, ([
            ('outputnode.out_report', 'inputnode.mni_report')])),
        (norm, hmsk, [('outputnode.out_tpms', 'inputnode.in_tpms')]),
        (to_ras, amw, [('out_file', 'inputnode.in_file')]),
        (skull_stripping, amw, [('outputnode.out_mask', 'inputnode.in_mask')]),
        (hmsk, amw, [('outputnode.out_file', 'inputnode.head_mask')]),
        (to_ras, iqmswf, [('out_file', 'inputnode.in_ras')]),
        (skull_stripping, iqmswf, [('outputnode.out_corrected', 'inputnode.inu_corrected'),
                                   (ss_bias_field, 'inputnode.in_inu'),
                                   ('outputnode.out_mask', 'inputnode.brainmask')]),
        (amw, iqmswf, [('outputnode.air_mask', 'inputnode.airmask'),
                       ('outputnode.hat_mask', 'inputnode.hatmask'),
                       ('outputnode.art_mask', 'inputnode.artmask'),
                       ('outputnode.rot_mask', 'inputnode.rotmask')]),
        (hmsk, bts, [('outputnode.out_denoised', 'inputnode.in_file')]),
        (bts, iqmswf, [('outputnode.out_segm', 'inputnode.segmentation'),
                       ('outputnode.out_pvms', 'inputnode.pvms')]),
        (hmsk, iqmswf, [('outputnode.out_file', 'inputnode.headmask')]),
        (to_ras, anat_report_wf, [('out_file', 'inputnode.in_ras')]),
        (skull_stripping, anat_report_wf, [
            ('outputnode.out_corrected', 'inputnode.inu_corrected'),
            ('outputnode.out_mask', 'inputnode.brainmask')]),
        (hmsk, anat_report_wf, [('outputnode.out_file', 'inputnode.headmask')]),
        (amw, anat_report_wf, [
            ('outputnode.air_mask', 'inputnode.airmask'),
            ('outputnode.art_mask', 'inputnode.artmask'),
            ('outputnode.rot_mask', 'inputnode.rotmask'),
        ]),
        (bts, anat_report_wf, [('outputnode.out_segm', 'inputnode.segmentation')]),
        (iqmswf, anat_report_wf, [('outputnode.noisefit', 'inputnode.noisefit')]),
        (iqmswf, anat_report_wf, [('outputnode.out_file', 'inputnode.in_iqms')]),
        (iqmswf, outputnode, [('outputnode.out_file', 'out_json')]),
    ])""",
    "    # fmt: on",
    "",
    "    # Upload metrics",
    "    if not config.execution.no_sub:",
    "        from mriqc.interfaces.webapi import UploadIQMs",
    "",
    """        upldwf = pe.Node(UploadIQMs(
                endpoint=config.execution.webapi_url,
                auth_token=config.execution.webapi_token,
                strict=config.execution.upload_strict,
            ), name='UploadMetrics')""",
    "",
    "        # fmt: off",
    """        workflow.connect([
            (iqmswf, upldwf, [('outputnode.out_file', 'in_iqms')]),
            (upldwf, anat_report_wf, [('api_id', 'inputnode.api_id')]),
        ])""",
    "",
    "    # fmt: on",
    "",
    "    return workflow",
]


def test_split_into_statements():
    stmts = split_source_into_statements(EXAMPLE_SOURCE_CODE)
    assert stmts == EXAMPLE_SOURCE_CODE_SPLIT
