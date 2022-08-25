
    wf.add(smriprep.interfaces.reports.AboutSummary(
        name="about",
        version="0.9.2",
        command="/Users/tclose/git/workflows/nipype2pydra/port_smriprep.py /Users/tclose/git/workflows/nipype2pydra/outputs/smriprep.py /Users/tclose/data/bids-data/ds000113"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_fsnative_t1w",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=[],
        suffix="xfm",
        mode="image",
        from="fsnative",
        to="T1w",
        extension="txt"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_std2t1w_xfm",
        base_directory=".",
        check_hdr=true,
        mode="image",
        suffix="xfm",
        to="T1w"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_surfs",
        base_directory=".",
        check_hdr=true,
        extension=".surf.gii"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w2std_xfm",
        base_directory=".",
        check_hdr=true,
        from="T1w",
        mode="image",
        suffix="xfm"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_dseg",
        base_directory=".",
        check_hdr=true,
        compress=[true],
        dismiss_entities=[],
        suffix="dseg"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_fsaseg",
        base_directory=".",
        check_hdr=true,
        compress=[true],
        dismiss_entities=[],
        desc="aseg",
        suffix="dseg"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_fsnative",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=[],
        suffix="xfm",
        mode="image",
        from="T1w",
        to="fsnative",
        extension="txt"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_fsparc",
        base_directory=".",
        check_hdr=true,
        compress=[true],
        dismiss_entities=[],
        desc="aparcaseg",
        suffix="dseg"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_mask",
        base_directory=".",
        check_hdr=true,
        compress=[true],
        dismiss_entities=[],
        desc="brain",
        suffix="mask",
        Type="Brain"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_preproc",
        base_directory=".",
        check_hdr=true,
        compress=[true],
        dismiss_entities=[],
        desc="preproc",
        SkullStripped=false
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_tpms",
        base_directory=".",
        check_hdr=true,
        compress=[true],
        dismiss_entities=[],
        suffix="probseg",
        label=["GM", "WM", "CSF"]
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(niworkflows.interfaces.nitransforms.ConcatenateXFMs(
        name="lta2itk_fwd",
        inverse=false,
        out_fmt="itk"
    )
    wf.add(niworkflows.interfaces.nitransforms.ConcatenateXFMs(
        name="lta2itk_inv",
        inverse=false,
        out_fmt="itk"
    )
    wf.add(niworkflows.interfaces.surf.Path2BIDS(
        name="name_surfs"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="raw_sources",
        function_str="def _bids_relative(in_files, bids_root):\n    from pathlib import Path\n\n    if not isinstance(in_files, (list, tuple)):\n        in_files = [in_files]\n    in_files = [str(Path(p).relative_to(bids_root)) for p in in_files]\n    return in_files\n",
        bids_root="/Users/tclose/data/bids-data/ds000113"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="poutputnode"
    )
    wf.add(niworkflows.interfaces.norm.SpatialNormalization(
        name="registration",
        num_threads=1,
        flavor="precise",
        orientation="RAS",
        reference="T1w",
        moving="T1w",
        template="MNI152NLin2009cAsym",
        explicit_masking=true,
        float=true
    )
    wf.add(smriprep.interfaces.templateflow.TemplateDesc(
        name="split_desc"
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderApplyTransforms(
        name="std_dseg",
        out_postfix="_trans",
        interpolation="MultiLabel",
        default_value=0.0,
        float=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderApplyTransforms(
        name="std_mask",
        out_postfix="_trans",
        interpolation="MultiLabel",
        default_value=0.0,
        float=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderApplyTransforms(
        name="std_tpms",
        default_value=0.0,
        dimension=3,
        environ={"NSLOTS": "1"},
        float=true,
        interpolation="Gaussian",
        num_threads=1,
        out_postfix="_trans"
    )
    wf.add(smriprep.interfaces.templateflow.TemplateFlowSelect(
        name="tf_select",
        resolution=[1],
        template_spec={"atlas": null, "cohort": null}
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderApplyTransforms(
        name="tpl_moving",
        dimension=3,
        out_postfix="_trans",
        interpolation="LanczosWindowedSinc",
        default_value=0.0,
        float=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="trunc_mov",
        dimension=3,
        operation="TruncateImageIntensity",
        op2="0.01 0.999 256",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_recon_report",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=[],
        desc="reconall",
        datatype="figures"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_std_t1w_report",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=[],
        suffix="T1w",
        datatype="figures"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_conform_report",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=[],
        desc="conform",
        datatype="figures"
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_t1w_dseg_mask_report",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=[],
        suffix="dseg",
        datatype="figures"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="norm_msk",
        function_str="def _rpt_masks(mask_file, before, after, after_mask=None):\n    from os.path import abspath\n    import nibabel as nb\n\n    msk = nb.load(mask_file).get_fdata() > 0\n    bnii = nb.load(before)\n    nb.Nifti1Image(bnii.get_fdata() * msk, bnii.affine, bnii.header).to_filename(\n        \"before.nii.gz\"\n    )\n    if after_mask is not None:\n        msk = nb.load(after_mask).get_fdata() > 0\n\n    anii = nb.load(after)\n    nb.Nifti1Image(anii.get_fdata() * msk, anii.affine, anii.header).to_filename(\n        \"after.nii.gz\"\n    )\n    return abspath(\"before.nii.gz\"), abspath(\"after.nii.gz\")\n"
    )
    wf.add(niworkflows.interfaces.reportlets.registration.SimpleBeforeAfterRPT(
        name="norm_rpt",
        before_label="before",
        after_label="Participant",
        dismiss_affine=false,
        out_report="report.svg",
        compress_report="auto"
    )
    wf.add(smriprep.interfaces.reports.FSSurfaceReport(
        name="recon_report",
        out_report="report.svg",
        compress_report="auto",
        hemi="both"
    )
    wf.add(niworkflows.interfaces.reportlets.masks.ROIsPlot(
        name="seg_rpt",
        masked=false,
        colors=["b", "magenta"],
        levels=[1.5, 2.5],
        mask_color="r",
        out_report="report.svg",
        compress_report="auto"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="t1w_conform_check",
        function_str="def _empty_report(in_file=None):\n    from pathlib import Path\n    from nipype.interfaces.base import isdefined\n\n    if in_file is not None and isdefined(in_file):\n        return in_file\n\n    out_file = Path(\"tmp-report.html\").absolute()\n    out_file.write_text(\n        \"\"\"\\\n                <h4 class=\"elem-title\">A previously computed T1w template was provided.</h4>\n\"\"\"\n    )\n    return str(out_file)\n"
    )
    wf.add(smriprep.interfaces.templateflow.TemplateFlowSelect(
        name="tf_select",
        resolution=[1],
        template_spec={"atlas": null, "cohort": null}
    )
    wf.add(nipype.interfaces.utility.base.Select(
        name="get1st",
        index=[0]
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode",
        t1w_realign_xfm=["/Users/tclose/git/workflows/nipype2pydra/.venv/lib/python3.8/site-packages/smriprep/data/itkIdentityTransform.txt"]
    )
    wf.add(niworkflows.interfaces.images.Conform(
        name="t1w_conform"
    )
    wf.add(niworkflows.interfaces.images.TemplateDimensions(
        name="t1w_ref_dimensions",
        max_scale=3.0
    )
    wf.add(niworkflows.interfaces.header.ValidateImage(
        name="anat_validate"
    )
    wf.add(nipype.interfaces.fsl.maths.ApplyMask(
        name="applyrefined",
        output_type="NIFTI_GZ",
        environ={"FSLOUTPUTTYPE": "NIFTI_GZ"}
    )
    wf.add(niworkflows.interfaces.nibabel.ApplyMask(
        name="apply_mask",
        threshold=0.5
    )
    wf.add(nipype.interfaces.ants.segmentation.Atropos(
        name="01_atropos",
        dimension=3,
        initialization="KMeans",
        number_of_tissue_classes=3,
        likelihood_model="Gaussian",
        mrf_smoothing_factor=0.1,
        mrf_radius=[1, 1, 1],
        n_iterations=3,
        convergence_threshold=0.0,
        use_random_seed=true,
        save_posteriors=true,
        output_posteriors_name_template="POSTERIOR_%02d.nii.gz",
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="02_pad_segm",
        dimension=3,
        operation="PadImage",
        op2="10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="03_pad_mask",
        dimension=3,
        operation="PadImage",
        op2="10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="04_sel_labels",
        function_str="def _select_labels(in_segm, labels):\n    from os import getcwd\n    import numpy as np\n    import nibabel as nb\n    from nipype.utils.filemanip import fname_presuffix\n\n    out_files = []\n\n    cwd = getcwd()\n    nii = nb.load(in_segm)\n    label_data = np.asanyarray(nii.dataobj).astype(\"uint8\")\n    for label in labels:\n        newnii = nii.__class__(np.uint8(label_data == label), nii.affine, nii.header)\n        newnii.set_data_dtype(\"uint8\")\n        out_file = fname_presuffix(in_segm, suffix=\"_class-%02d\" % label, newpath=cwd)\n        newnii.to_filename(out_file)\n        out_files.append(out_file)\n    return out_files\n",
        labels=[3, 2, 1]
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="05_get_wm",
        dimension=3,
        operation="GetLargestComponent",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="06_get_gm",
        dimension=3,
        operation="GetLargestComponent",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="07_fill_gm",
        dimension=3,
        operation="FillHoles",
        op2="2",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.MultiplyImages(
        name="08_mult_gm",
        dimension=3,
        output_product_image="08_mult_gm.nii.gz",
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.MultiplyImages(
        name="09_relabel_wm",
        dimension=3,
        second_input=3.0,
        output_product_image="09_relabel_wm.nii.gz",
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="10_me_csf",
        dimension=3,
        operation="ME",
        op2="10",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="11_add_gm",
        dimension=3,
        operation="addtozero",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.MultiplyImages(
        name="12_relabel_gm",
        dimension=3,
        second_input=2.0,
        output_product_image="12_relabel_gm.nii.gz",
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="13_add_gm_wm",
        dimension=3,
        operation="addtozero",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="14_sel_labels2",
        function_str="def _select_labels(in_segm, labels):\n    from os import getcwd\n    import numpy as np\n    import nibabel as nb\n    from nipype.utils.filemanip import fname_presuffix\n\n    out_files = []\n\n    cwd = getcwd()\n    nii = nb.load(in_segm)\n    label_data = np.asanyarray(nii.dataobj).astype(\"uint8\")\n    for label in labels:\n        newnii = nii.__class__(np.uint8(label_data == label), nii.affine, nii.header)\n        newnii.set_data_dtype(\"uint8\")\n        out_file = fname_presuffix(in_segm, suffix=\"_class-%02d\" % label, newpath=cwd)\n        newnii.to_filename(out_file)\n        out_files.append(out_file)\n    return out_files\n",
        labels=[2, 3]
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="15_add_7",
        dimension=3,
        operation="addtozero",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="16_me_7",
        dimension=3,
        operation="ME",
        op2="2",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="17_comp_7",
        dimension=3,
        operation="GetLargestComponent",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="18_md_7",
        dimension=3,
        operation="MD",
        op2="4",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="19_fill_7",
        dimension=3,
        operation="FillHoles",
        op2="2",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="20_add_7_2",
        dimension=3,
        operation="addtozero",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="21_md_7_2",
        dimension=3,
        operation="MD",
        op2="5",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="22_me_7_2",
        dimension=3,
        operation="ME",
        op2="5",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="23_depad_mask",
        dimension=3,
        operation="PadImage",
        op2="-10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="24_depad_segm",
        dimension=3,
        operation="PadImage",
        op2="-10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="25_depad_gm",
        dimension=3,
        operation="PadImage",
        op2="-10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="26_depad_wm",
        dimension=3,
        operation="PadImage",
        op2="-10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="27_depad_csf",
        dimension=3,
        operation="PadImage",
        op2="-10",
        copy_header=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(niworkflows.interfaces.nibabel.ApplyMask(
        name="apply_mask",
        threshold=0.5
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="apply_wm_prior",
        function_str="def _improd(op1, op2, in_mask, out_file=None):\n    import nibabel as nb\n\n    im1 = nb.load(op1)\n\n    data = im1.get_fdata(dtype=\"float32\") * nb.load(op2).get_fdata(dtype=\"float32\")\n    mskdata = nb.load(in_mask).get_fdata() > 0\n    data[~mskdata] = 0\n    data[data < 0] = 0\n    data /= data.max()\n    data = 0.5 * (data + mskdata)\n    nii = nb.Nifti1Image(data, im1.affine, im1.header)\n\n    if out_file is None:\n        from pathlib import Path\n\n        out_file = str((Path() / \"prodmap.nii.gz\").absolute())\n\n    nii.to_filename(out_file)\n    return out_file\n"
    )
    wf.add(niworkflows.interfaces.header.CopyXForm(
        name="copy_xform"
    )
    wf.add(niworkflows.interfaces.header.CopyXForm(
        name="copy_xform_wm"
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="dil_brainmask",
        dimension=3,
        operation="MD",
        op2="2",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="get_brainmask",
        dimension=3,
        operation="GetLargestComponent",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.ants.segmentation.N4BiasFieldCorrection(
        name="inu_n4_final",
        bspline_fitting_distance=200.0,
        convergence_threshold=1e-07,
        copy_header=true,
        dimension=3,
        environ={"NSLOTS": "1"},
        n_iterations=[50, 50, 50, 50, 50],
        num_threads=1,
        rescale_intensities=true,
        save_bias=true,
        shrink_factor=4
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="match_wm",
        function_str="def _matchlen(value, reference):\n    return [value] * len(reference)\n"
    )
    wf.add(nipype.interfaces.utility.base.Merge(
        name="merge_tpms",
        axis="vstack",
        no_flatten=false,
        ravel_inputs=false
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="msk_conform",
        function_str="def _conform_mask(in_mask, in_reference):\n    \"\"\"Ensures the mask headers make sense and match those of the T1w\"\"\"\n    from pathlib import Path\n    import numpy as np\n    import nibabel as nb\n    from nipype.utils.filemanip import fname_presuffix\n\n    ref = nb.load(in_reference)\n    nii = nb.load(in_mask)\n    hdr = nii.header.copy()\n    hdr.set_data_dtype(\"int16\")\n    hdr.set_slope_inter(1, 0)\n\n    qform, qcode = ref.header.get_qform(coded=True)\n    if qcode is not None:\n        hdr.set_qform(qform, int(qcode))\n\n    sform, scode = ref.header.get_sform(coded=True)\n    if scode is not None:\n        hdr.set_sform(sform, int(scode))\n\n    if \"_maths\" in in_mask:  # Cut the name at first _maths occurrence\n        ext = \"\".join(Path(in_mask).suffixes)\n        basename = Path(in_mask).name\n        in_mask = basename.split(\"_maths\")[0] + ext\n\n    out_file = fname_presuffix(in_mask, suffix=\"_mask\", newpath=str(Path()))\n    nii.__class__(\n        np.asanyarray(nii.dataobj).astype(\"int16\"), ref.affine, hdr\n    ).to_filename(out_file)\n    return out_file\n"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(nipype.algorithms.metrics.FuzzyOverlap(
        name="overlap",
        weighting="none",
        out_file="diff.nii"
    )
    wf.add(nipype.interfaces.utility.base.Select(
        name="sel_wm"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="full_wm",
        function_str="def _imsum(op1, op2, out_file=None):\n    import nibabel as nb\n\n    im1 = nb.load(op1)\n\n    data = im1.get_fdata(dtype=\"float32\") + nb.load(op2).get_fdata(dtype=\"float32\")\n    data /= data.max()\n    nii = nb.Nifti1Image(data, im1.affine, im1.header)\n\n    if out_file is None:\n        from pathlib import Path\n\n        out_file = str((Path() / \"summap.nii.gz\").absolute())\n\n    nii.to_filename(out_file)\n    return out_file\n",
        op1="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_label-WM_probseg.nii.gz",
        op2="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_label-BS_probseg.nii.gz"
    )
    wf.add(nipype.interfaces.ants.utils.AI(
        name="init_aff",
        dimension=3,
        verbose=true,
        metric=["Mattes", 32, "Regular", 0.25],
        transform=["Affine", 0.1],
        principal_axes=false,
        search_factor=[15.0, 0.1],
        search_grid=[40.0, [0.0, 40.0, 40.0]],
        convergence=[10, 1e-06, 10],
        output_transform="initialization.mat",
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode",
        in_mask="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_desc-BrainCerebellumExtraction_mask.nii.gz"
    )
    wf.add(nipype.interfaces.ants.segmentation.N4BiasFieldCorrection(
        name="inu_n4",
        bspline_fitting_distance=200.0,
        convergence_threshold=1e-07,
        copy_header=true,
        dimension=3,
        environ={"NSLOTS": "1"},
        n_iterations=[50, 50, 50, 50],
        num_threads=1,
        rescale_intensities=false,
        save_bias=false,
        shrink_factor=4
    )
    wf.add(nipype.interfaces.ants.segmentation.N4BiasFieldCorrection(
        name="inu_n4_final",
        bspline_fitting_distance=200.0,
        convergence_threshold=1e-07,
        copy_header=true,
        dimension=3,
        environ={"NSLOTS": "1"},
        n_iterations=[50, 50, 50, 50, 50],
        num_threads=1,
        rescale_intensities=true,
        save_bias=true,
        shrink_factor=4
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="lap_target",
        dimension=3,
        operation="Laplacian",
        op2="1.5 1",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="lap_tmpl",
        dimension=3,
        operation="Laplacian",
        op1="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_T1w.nii.gz",
        op2="1.5 1",
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderApplyTransforms(
        name="map_brainmask",
        input_image="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_label-brain_probseg.nii.gz",
        out_postfix="_trans",
        interpolation="Gaussian",
        default_value=0.0,
        float=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderApplyTransforms(
        name="map_wmmask",
        out_postfix="_trans",
        interpolation="Gaussian",
        default_value=0.0,
        float=false,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.utility.base.Merge(
        name="mrg_target",
        axis="vstack",
        no_flatten=false,
        ravel_inputs=false
    )
    wf.add(nipype.interfaces.utility.base.Merge(
        name="mrg_tmpl",
        axis="vstack",
        no_flatten=false,
        ravel_inputs=false,
        in1="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_T1w.nii.gz"
    )
    wf.add(niworkflows.interfaces.fixes.FixHeaderRegistration(
        name="norm",
        dimension=3,
        metric=["MI", "MI", ["CC", "CC"]],
        metric_weight_item_trait=1.0,
        metric_weight=[1.0, 1.0, [0.5, 0.5]],
        radius_bins_item_trait=5,
        radius_or_number_of_bins=[32, 32, [4, 4]],
        sampling_strategy=["Regular", "Regular", ["None", "None"]],
        sampling_percentage=[0.25, 0.25, [1.0, 1.0]],
        use_histogram_matching=true,
        interpolation="LanczosWindowedSinc",
        write_composite_transform=false,
        collapse_output_transforms=true,
        initialize_transforms_per_stage=false,
        float=true,
        transforms=["Rigid", "Affine", "SyN"],
        transform_parameters=[[0.1], [0.1], [0.1, 3.0, 0.0]],
        number_of_iterations=[[1000, 500, 250, 100], [1000, 500, 250, 100], [50, 10, 0]],
        smoothing_sigmas=[[4.0, 2.0, 1.0, 0.0], [4.0, 2.0, 1.0, 0.0], [2.0, 1.0, 0.0]],
        sigma_units=["vox", "vox", "vox"],
        shrink_factors=[[8, 4, 2, 1], [8, 4, 2, 1], [4, 2, 1]],
        convergence_threshold=[1e-08, 1e-08, 1e-09],
        convergence_window_size=[10, 10, 15],
        output_transform_prefix="anat_to_template",
        output_warped_image=true,
        winsorize_upper_quantile=0.975,
        winsorize_lower_quantile=0.025,
        verbose=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(niworkflows.interfaces.nibabel.RegridToZooms(
        name="res_target",
        zooms=[4.0, 4.0, 4.0],
        order=3,
        clip=true,
        smooth=true
    )
    wf.add(niworkflows.interfaces.nibabel.RegridToZooms(
        name="res_tmpl",
        in_file="/Users/tclose/.cache/templateflow/tpl-OASIS30ANTs/tpl-OASIS30ANTs_res-01_T1w.nii.gz",
        zooms=[4.0, 4.0, 4.0],
        order=3,
        clip=true,
        smooth=true
    )
    wf.add(nipype.interfaces.ants.utils.ThresholdImage(
        name="thr_brainmask",
        dimension=3,
        th_low=0.5,
        th_high=1.0,
        inside_value=1.0,
        outside_value=0.0,
        copy_header=true,
        num_threads=1,
        environ={"NSLOTS": "1"}
    )
    wf.add(nipype.interfaces.ants.utils.ImageMath(
        name="truncate_images",
        copy_header=true,
        dimension=3,
        environ={"NSLOTS": "1"},
        num_threads=1,
        op2="0.01 0.999 256",
        operation="TruncateImageIntensity"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="buffernode"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="fast2bids",
        function_str="def _probseg_fast2bids(inlist):\n    \"\"\"Reorder a list of probseg maps from FAST (CSF, WM, GM) to BIDS (GM, WM, CSF).\"\"\"\n    return (inlist[1], inlist[2], inlist[0])\n"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="fs_isrunning",
        function_str="def fs_isRunning(subjects_dir, subject_id, mtime_tol=86400, logger=None):\n    \"\"\"\n    Checks FreeSurfer subjects dir for presence of recon-all blocking ``IsRunning`` files,\n    and optionally removes any based on the modification time.\n\n    Parameters\n    ----------\n    subjects_dir : os.PathLike or None\n        Existing FreeSurfer subjects directory\n    subject_id : str\n        Subject label\n    mtime_tol : int\n        Tolerance time (in seconds) between current time and last modification of ``recon-all.log``\n\n    Returns\n    -------\n    subjects_dir : os.PathLike or None\n\n    \"\"\"\n    from pathlib import Path\n    import time\n\n    if subjects_dir is None:\n        return subjects_dir\n    subj_dir = Path(subjects_dir) / subject_id\n    if not subj_dir.exists():\n        return subjects_dir\n\n    isrunning = tuple(subj_dir.glob(\"scripts/IsRunning*\"))\n    if not isrunning:\n        return subjects_dir\n    reconlog = subj_dir / \"scripts\" / \"recon-all.log\"\n    # if recon log doesn't exist, just clear IsRunning\n    mtime = reconlog.stat().st_mtime if reconlog.exists() else 0\n    if (time.time() - mtime) < mtime_tol:\n        raise RuntimeError(\n            f\"\"\"\\\nThe FreeSurfer's subject folder <{subj_dir}> contains IsRunning files that \\\nmay pertain to a current or past execution: {isrunning}.\nFreeSurfer cannot run if these are present, to avoid interfering with a running \\\nprocess. Please, make sure no other process is running ``recon-all`` on this subject \\\nand proceed to delete the files listed above.\"\"\"\n        )\n    for fl in isrunning:\n        fl.unlink()\n    if logger:\n        logger.warn(f'Removed \"IsRunning*\" files found under {subj_dir}')\n    return subjects_dir\n",
        logger=<Logger nipype.workflow (INFO)>
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="lut_t1w_dseg",
        function_str="def apply_lut(in_dseg, lut, newpath=None):\n    \"\"\"Map the input discrete segmentation to a new label set (lookup table, LUT).\"\"\"\n    import numpy as np\n    import nibabel as nb\n    from nipype.utils.filemanip import fname_presuffix\n\n    if newpath is None:\n        from os import getcwd\n\n        newpath = getcwd()\n\n    out_file = fname_presuffix(in_dseg, suffix=\"_dseg\", newpath=newpath)\n    lut = np.array(lut, dtype=\"int16\")\n\n    segm = nb.load(in_dseg)\n    hdr = segm.header.copy()\n    hdr.set_data_dtype(\"int16\")\n    segm.__class__(\n        lut[np.asanyarray(segm.dataobj, dtype=int)].astype(\"int16\"), segm.affine, hdr\n    ).to_filename(out_file)\n\n    return out_file\n",
        lut=[0, 3, 1, 2]
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(smriprep.interfaces.freesurfer.ReconAll(
        name="autorecon1",
        directive="autorecon1",
        subject_id="recon_all",
        openmp=1,
        environ={}
    )
    wf.add(smriprep.interfaces.freesurfer.ReconAll(
        name="autorecon2_vol",
        directive="autorecon2-volonly",
        subject_id="recon_all",
        openmp=1,
        environ={}
    )
    wf.add(smriprep.interfaces.freesurfer.ReconAll(
        name="autorecon3",
        directive="autorecon3",
        subject_id="recon_all",
        openmp=1,
        environ={}
    )
    wf.add(smriprep.interfaces.freesurfer.ReconAll(
        name="autorecon_surfs",
        directive="autorecon-hemi",
        environ={},
        flags=["-noparcstats", "-noparcstats2", "-noparcstats3", "-nohyporelabel", "-nobalabels"],
        hemi=["lh", "rh"],
        openmp=1,
        subject_id="recon_all"
    )
    wf.add(smriprep.interfaces.freesurfer.ReconAll(
        name="cortribbon",
        steps=["cortribbon"],
        subject_id="recon_all",
        parallel=true,
        environ={}
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(smriprep.interfaces.freesurfer.ReconAll(
        name="parcstats",
        directive="autorecon-hemi",
        environ={},
        flags=["-nohyporelabel"],
        hemi=["lh", "rh"],
        openmp=1,
        subject_id="recon_all"
    )
    wf.add(nipype.interfaces.utility.wrappers.Function(
        name="fov_check",
        function_str="def _check_cw256(in_files, default_flags):\n    import numpy as np\n    from nibabel.funcs import concat_images\n\n    if isinstance(in_files, str):\n        in_files = [in_files]\n    summary_img = concat_images(in_files)\n    fov = np.array(summary_img.shape[:3]) * summary_img.header.get_zooms()[:3]\n    flags = list(default_flags)\n    if np.any(fov > 256):\n        flags.append(\"-cw256\")\n    return flags\n",
        default_flags=["-noskullstrip", "-noT2pial", "-noFLAIRpial"]
    )
    wf.add(niworkflows.interfaces.freesurfer.PatchedRobustRegister(
        name="fsnative2t1w_xfm",
        out_reg_file=true,
        est_int_scale=true,
        auto_sens=true,
        environ={}
    )
    wf.add(smriprep.interfaces.surf.NormalizeSurf(
        name="fix_surfs"
    )
    wf.add(nipype.interfaces.freesurfer.utils.MRIsConvert(
        name="fs2gii",
        environ={},
        out_datatype="gii",
        to_scanner=true
    )
    wf.add(nipype.interfaces.io.FreeSurferSource(
        name="get_surfaces",
        hemi="both"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(niworkflows.interfaces.freesurfer.MakeMidthickness(
        name="midthickness",
        distance=0.5,
        environ={},
        out_name="midthickness",
        sphere="sphere",
        thickness=true
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(nipype.interfaces.io.DataSink(
        name="save_midthickness",
        parameterization=false,
        _outputs={},
        remove_dest_dir=false
    )
    wf.add(nipype.interfaces.utility.base.Merge(
        name="surface_list",
        axis="vstack",
        no_flatten=false,
        ravel_inputs=true
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(niworkflows.interfaces.freesurfer.FSDetectInputs(
        name="recon_config",
        hires_enabled=true
    )
    wf.add(niworkflows.interfaces.freesurfer.RefineBrainMask(
        name="refine"
    )
    wf.add(nipype.interfaces.io.FreeSurferSource(
        name="fs_datasource",
        hemi="both"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(nipype.interfaces.freesurfer.preprocess.ApplyVolTransform(
        name="resample",
        transformed_file="seg.nii.gz",
        interp="nearest",
        environ={}
    )
    wf.add(nipype.interfaces.io.FreeSurferSource(
        name="fs_datasource",
        hemi="both"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="outputnode"
    )
    wf.add(nipype.interfaces.freesurfer.preprocess.ApplyVolTransform(
        name="resample",
        transformed_file="seg.nii.gz",
        interp="nearest",
        environ={}
    )
    wf.add(niworkflows.interfaces.freesurfer.FSInjectBrainExtracted(
        name="skull_strip_extern"
    )
    wf.add(niworkflows.interfaces.freesurfer.PatchedLTAConvert(
        name="t1w2fsnative_xfm",
        out_lta=true,
        invert=true,
        environ={}
    )
    wf.add(nipype.interfaces.fsl.preprocess.FAST(
        name="t1w_dseg",
        segments=true,
        no_bias=true,
        probability_maps=true,
        output_type="NIFTI_GZ",
        environ={"FSLOUTPUTTYPE": "NIFTI_GZ"}
    )
    wf.add(niworkflows.interfaces.bids.BIDSInfo(
        name="bids_info",
        bids_dir="/Users/tclose/data/bids-data/ds000113",
        bids_validate=true,
        ('t1w', 'def fix_multi_T1w_source_name(in_files):\n    """\n    Make up a generic source name when there are multiple T1s\n\n    >>> fix_multi_T1w_source_name([\n    ...     \'/path/to/sub-045_ses-test_T1w.nii.gz\',\n    ...     \'/path/to/sub-045_ses-retest_T1w.nii.gz\'])\n    \'/path/to/sub-045_T1w.nii.gz\'\n\n\n    >>> fix_multi_T1w_source_name([\n    ...    (\'/path/to/sub-045-echo-1_T1w.nii.gz\', \'path/to/sub-045-echo-2_T1w.nii.gz\')])\n    \'/path/to/sub-045_T1w.nii.gz\'\n\n    """\n    import os\n    from nipype.utils.filemanip import filename_to_list\n\n    in_file = filename_to_list(in_files)[0]\n    if isinstance(in_file, (list, tuple)):\n        in_file = in_file[0]\n\n    base, in_file = os.path.split(in_file)\n    subject_label = in_file.split("_", 1)[0].split("-")[1]\n    return os.path.join(base, "sub-%s_T1w.nii.gz" % subject_label)\n', ())=bidssrc.lzout.in_file
    )
    wf.add(niworkflows.interfaces.bids.BIDSDataGrabber(
        name="bidssrc",
        subject_data={"t1w": ["/completely/made/up/path/sub-01_T1w.nii.gz"]}
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_report_about",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=["session"],
        desc="about",
        datatype="figures",
        ('t1w', 'def fix_multi_T1w_source_name(in_files):\n    """\n    Make up a generic source name when there are multiple T1s\n\n    >>> fix_multi_T1w_source_name([\n    ...     \'/path/to/sub-045_ses-test_T1w.nii.gz\',\n    ...     \'/path/to/sub-045_ses-retest_T1w.nii.gz\'])\n    \'/path/to/sub-045_T1w.nii.gz\'\n\n\n    >>> fix_multi_T1w_source_name([\n    ...    (\'/path/to/sub-045-echo-1_T1w.nii.gz\', \'path/to/sub-045-echo-2_T1w.nii.gz\')])\n    \'/path/to/sub-045_T1w.nii.gz\'\n\n    """\n    import os\n    from nipype.utils.filemanip import filename_to_list\n\n    in_file = filename_to_list(in_files)[0]\n    if isinstance(in_file, (list, tuple)):\n        in_file = in_file[0]\n\n    base, in_file = os.path.split(in_file)\n    subject_label = in_file.split("_", 1)[0].split("-")[1]\n    return os.path.join(base, "sub-%s_T1w.nii.gz" % subject_label)\n', ())=bidssrc.lzout.source_file,
        out_report=about.lzout.in_file
    )
    wf.add(smriprep.interfaces.DerivativesDataSink(
        name="ds_report_summary",
        base_directory=".",
        check_hdr=true,
        compress=[],
        dismiss_entities=["session"],
        desc="summary",
        datatype="figures",
        ('t1w', 'def fix_multi_T1w_source_name(in_files):\n    """\n    Make up a generic source name when there are multiple T1s\n\n    >>> fix_multi_T1w_source_name([\n    ...     \'/path/to/sub-045_ses-test_T1w.nii.gz\',\n    ...     \'/path/to/sub-045_ses-retest_T1w.nii.gz\'])\n    \'/path/to/sub-045_T1w.nii.gz\'\n\n\n    >>> fix_multi_T1w_source_name([\n    ...    (\'/path/to/sub-045-echo-1_T1w.nii.gz\', \'path/to/sub-045-echo-2_T1w.nii.gz\')])\n    \'/path/to/sub-045_T1w.nii.gz\'\n\n    """\n    import os\n    from nipype.utils.filemanip import filename_to_list\n\n    in_file = filename_to_list(in_files)[0]\n    if isinstance(in_file, (list, tuple)):\n        in_file = in_file[0]\n\n    base, in_file = os.path.split(in_file)\n    subject_label = in_file.split("_", 1)[0].split("-")[1]\n    return os.path.join(base, "sub-%s_T1w.nii.gz" % subject_label)\n', ())=bidssrc.lzout.source_file,
        out_report=summary.lzout.in_file
    )
    wf.add(nipype.interfaces.utility.base.IdentityInterface(
        name="inputnode"
    )
    wf.add(smriprep.interfaces.reports.SubjectSummary(
        name="summary",
        output_spaces=["MNI152NLin2009cAsym", "fsaverage"],
        subjects_dir=inputnode.lzout.subjects_dir,
        t1w=bidssrc.lzout.t1w,
        t2w=bidssrc.lzout.t2w,
        subject=bids_info.lzout.subject_id
    )