from importlib import import_module
import yaml
import pytest
import logging
from conftest import show_cli_trace
from traceback import format_exc
from nipype2pydra.cli.task import task as task_cli
from nipype2pydra.utils import add_to_sys_path, add_exc_note, INBUILT_NIPYPE_TRAIT_NAMES
from conftest import EXAMPLE_TASKS_DIR


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
        str(p.relative_to(EXAMPLE_TASKS_DIR)).replace("/", "-")[:-5]
        for p in (EXAMPLE_TASKS_DIR).glob("**/*.yaml")
    ]
)
def task_spec_file(request):
    return EXAMPLE_TASKS_DIR.joinpath(*request.param.split("-")).with_suffix(".yaml")


def test_task_conversion(task_spec_file, cli_runner, work_dir, gen_test_conftest):

    try:
        with open(task_spec_file) as f:
            task_spec = yaml.safe_load(f)
        pkg_root = work_dir / "src"
        pkg_root.mkdir()
        # shutil.copyfile(gen_test_conftest, pkg_root / "conftest.py")

        output_module_path = f"nipype2pydratest.{task_spec_file.stem.lower()}"

        result = cli_runner(
            task_cli,
            args=[
                str(task_spec_file),
                str(pkg_root),
                "--output-module",
                output_module_path,
                "--callables",
                str(task_spec_file.parent / (task_spec_file.stem + "_callables.py")),
            ],
        )

        assert result.exit_code == 0, show_cli_trace(result)

        with add_to_sys_path(pkg_root):
            try:
                pydra_module = import_module(output_module_path)
            except Exception as e:
                add_exc_note(
                    e,
                    f"Attempting to import {task_spec['task_name']} from '{output_module_path}'",
                )
                raise e
        pydra_task = getattr(pydra_module, task_spec["task_name"])
        nipype_interface = getattr(
            import_module(task_spec["nipype_module"]), task_spec["nipype_name"]
        )
        assert nipype_interface.__name__ == task_spec["nipype_name"]  # sanity check

        nipype_input_names = nipype_interface.input_spec().all_trait_names()
        inputs_omit = task_spec["inputs"]["omit"] if task_spec["inputs"]["omit"] else []

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
                task_spec["outputs"]["omit"] if task_spec["outputs"]["omit"] else []
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

        # tests_fspath = pkg_root.joinpath(*output_module_path.split(".")).parent / "tests"

        # # logging.info("Running generated tests for %s", output_module_path)
        # # # Run generated pytests
        # # with add_to_sys_path(pkg_root):
        # #     result = pytest.main([str(tests_fspath)])

        # assert result.value == 0
    except Exception:
        task_name = task_spec_file.parent.name + "-" + task_spec_file.stem
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
