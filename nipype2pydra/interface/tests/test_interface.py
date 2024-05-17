from importlib import import_module
import yaml
import pytest
import logging
from traceback import format_exc
from nipype2pydra.utils import (
    add_to_sys_path,
    add_exc_note,
    INBUILT_NIPYPE_TRAIT_NAMES,
)
from nipype2pydra.package import PackageConverter
from conftest import EXAMPLE_INTERFACES_DIR


logging.basicConfig(level=logging.INFO)


XFAIL_INTERFACES = [
    "fsl-prob_track_x2",
    "fsl-flameo",
    "fsl-make_dyadic_vectors",
    "fsl-dual_regression",
    "fsl-epi_de_warp",
]

XFAIL_INTERFACES_IN_COMBINED = [
    "freesurfer-smooth",
    "freesurfer-apply_mask",
    "afni-merge",
    "afni-resample",
    "fsl-level_1_design",
    "fsl-apply_mask",
    "fsl-smooth",
    "fsl-merge",
]


@pytest.fixture(
    params=[
        str(p.relative_to(EXAMPLE_INTERFACES_DIR)).replace("/", "-")[:-5]
        for p in (EXAMPLE_INTERFACES_DIR).glob("**/*.yaml")
    ]
)
def interface_spec_file(request):
    return EXAMPLE_INTERFACES_DIR.joinpath(*request.param.split("-")).with_suffix(
        ".yaml"
    )


def test_interface_convert(
    interface_spec_file, cli_runner, work_dir, gen_test_conftest
):

    try:
        with open(interface_spec_file) as f:
            interface_spec = yaml.safe_load(f)
        pkg_root = work_dir / "src"
        pkg_root.mkdir()
        # shutil.copyfile(gen_test_conftest, pkg_root / "conftest.py")

        pkg_converter = PackageConverter(
            name="nipype2pydratest."
            + "_".join(
                interface_spec["nipype_module"].split(".")
                + [interface_spec["task_name"]]
            ),
            nipype_name=interface_spec["nipype_module"].split(".")[0],
            interface_only=True,
        )

        converter = pkg_converter.add_interface_from_spec(
            spec=interface_spec,
            callables_file=interface_spec_file.parent
            / (interface_spec_file.stem + "_callables.py"),
        )

        converter.write(pkg_root)

        with add_to_sys_path(pkg_root):
            try:
                pydra_module = import_module(converter.output_module)
            except Exception as e:
                add_exc_note(
                    e,
                    f"Attempting to import {interface_spec['task_name']} from '{converter.output_module}'",
                )
                raise e
        pydra_task = getattr(pydra_module, interface_spec["task_name"])
        nipype_interface = getattr(
            import_module(interface_spec["nipype_module"]),
            interface_spec["nipype_name"],
        )
        assert (
            nipype_interface.__name__ == interface_spec["nipype_name"]
        )  # sanity check

        nipype_input_names = nipype_interface.input_spec().all_trait_names()
        inputs_omit = (
            interface_spec["inputs"]["omit"] if interface_spec["inputs"]["omit"] else []
        )

        assert sorted(
            f[0] for f in pydra_task().input_spec.fields if not f[0].startswith("_")
        ) == sorted(
            n
            for n in nipype_input_names
            if not (
                n in INBUILT_NIPYPE_TRAIT_NAMES
                or n in inputs_omit
                or (n.endswith("_items") and n[: -len("_items")] in nipype_input_names)
            )
        )

        if nipype_interface.output_spec:
            nipype_output_names = nipype_interface.output_spec().all_trait_names()
            outputs_omit = (
                interface_spec["outputs"]["omit"]
                if interface_spec["outputs"]["omit"]
                else []
            )

            assert sorted(
                f[0]
                for f in pydra_task().output_spec.fields
                if not f[0].startswith("_")
            ) == sorted(
                n
                for n in nipype_output_names
                if not (
                    n in INBUILT_NIPYPE_TRAIT_NAMES
                    or n in outputs_omit
                    or (
                        n.endswith("_items")
                        and n[: -len("_items")] in nipype_output_names
                    )
                )
            )

        # Run doctests
        # logging.info("Running doctests for %s", output_module_path)
        # with add_to_sys_path(pkg_root):
        #     with contextlib.redirect_stdout(io.StringIO()) as f:
        #         exit_code = pytest.main(
        #             [
        #                 str(
        #                     pkg_root.joinpath(
        #                         *output_module_path.split(".")
        #                     ).with_suffix(".py")
        #                 ),
        #                 "--doctest-modules",
        #                 "--ignore-glob=test_*.py",
        #             ]
        #         )

        # assert not exit_code, f.getvalue()
        # tests_fspath = pkg_root.joinpath(*output_module_path.split(".")).parent / "tests"

        # # logging.info("Running generated tests for %s", output_module_path)
        # # # Run generated pytests
        # # with add_to_sys_path(pkg_root):
        # #     result = pytest.main([str(tests_fspath)])

        # assert result.value == 0
    except Exception:
        task_name = interface_spec_file.parent.name + "-" + interface_spec_file.stem
        if task_name in XFAIL_INTERFACES or task_name in XFAIL_INTERFACES_IN_COMBINED:
            msg = f"Test for '{task_name}' is expected to fail:\n{format_exc()}"
            if task_name in XFAIL_INTERFACES_IN_COMBINED:
                msg += (
                    "\nNote that it isn't expected to fail when you run it separately, "
                    "not sure why the interfaces are getting mixed up between tests but "
                    "looks like it comes from another interface"
                )
            pytest.xfail(msg)
        else:
            raise
