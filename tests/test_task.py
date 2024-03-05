from importlib import import_module
import yaml
import pytest
import logging
from conftest import show_cli_trace
from nipype2pydra.cli import task as task_cli
from nipype2pydra.utils import add_to_sys_path, add_exc_note
from conftest import EXAMPLE_TASKS_DIR


logging.basicConfig(level=logging.INFO)


INBUILT_NIPYPE_TRAIT_NAMES = [
    "__all__",
    "args",
    "trait_added",
    "trait_modified",
    "environ",
    "output_type",
]

XFAIL_PACKAGES = ["camino", "cat12", "cmtk", "dcmsstack", "dipy", "spm"]


@pytest.fixture(
    params=[
        str(p.relative_to(EXAMPLE_TASKS_DIR)).replace("/", "__")[:-5]
        for p in (EXAMPLE_TASKS_DIR).glob("**/*.yaml")
    ]
)
def task_spec_file(request):
    return EXAMPLE_TASKS_DIR.joinpath(*request.param.split("__")).with_suffix(".yaml")


@pytest.mark.xfail(condition="any(str(task_spec_file).startswith(str(EXAMPLE_TASKS_DIR / ('pydra-' + p))) for p in XFAIL_PACKAGES)")
def test_task_conversion(task_spec_file, cli_runner, work_dir, gen_test_conftest):

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
        ],
    )

    assert result.exit_code == 0, show_cli_trace(result)

    with add_to_sys_path(pkg_root):
        try:
            pydra_module = import_module(output_module_path)
        except Exception as e:
            add_exc_note(e, f"Attempting to import {task_spec['task_name']} from '{output_module_path}'")
            raise e
    pydra_task = getattr(pydra_module, task_spec["task_name"])
    nipype_interface = getattr(
        import_module(task_spec["nipype_module"]), task_spec["nipype_name"]
    )

    nipype_input_names = nipype_interface.input_spec().all_trait_names()
    inputs_omit = task_spec["inputs"]["omit"] if task_spec["inputs"]["omit"] else []

    assert sorted(f[0] for f in pydra_task().input_spec.fields if not f[0].startswith("_")) == sorted(
        n
        for n in nipype_input_names
        if not (
            n in INBUILT_NIPYPE_TRAIT_NAMES
            or n in inputs_omit
            or (n.endswith("_items") and n[: -len("_items")] in nipype_input_names)
        )
    )

    nipype_output_names = nipype_interface.output_spec().all_trait_names()
    outputs_omit = task_spec["outputs"]["omit"] if task_spec["outputs"]["omit"] else []

    assert sorted(f[0] for f in pydra_task().output_spec.fields if not f[0].startswith("_")) == sorted(
        n
        for n in nipype_output_names
        if not (
            n in INBUILT_NIPYPE_TRAIT_NAMES
            or n in outputs_omit
            or (n.endswith("_items") and n[: -len("_items")] in nipype_output_names)
        )
    )

    # tests_fspath = pkg_root.joinpath(*output_module_path.split(".")).parent / "tests"

    # # logging.info("Running generated tests for %s", output_module_path)
    # # # Run generated pytests
    # # with add_to_sys_path(pkg_root):
    # #     result = pytest.main([str(tests_fspath)])

    # assert result.value == 0
