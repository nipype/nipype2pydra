from importlib import import_module
import yaml
from conftest import show_cli_trace
import pytest
import shutil
import logging
from nipype2pydra.cli import task as task_cli
from nipype2pydra.utils import add_to_sys_path


logging.basicConfig(level=logging.INFO)


INBUILT_NIPYPE_TRAIT_NAMES = [
    "__all__",
    "args",
    "trait_added",
    "trait_modified",
    "environ",
    "output_type",
    "crop_list",
]


def test_task_conversion(task_spec_file, cli_runner, work_dir, gen_test_conftest):

    with open(task_spec_file) as f:
        task_spec = yaml.safe_load(f)
    pkg_root = work_dir / "src"
    pkg_root.mkdir()
    shutil.copyfile(gen_test_conftest, pkg_root / "conftest.py")

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
        pydra_module = import_module(output_module_path)
    pydra_task = getattr(pydra_module, task_spec["task_name"])
    nipype_interface = getattr(
        import_module(task_spec["nipype_module"]), task_spec["task_name"]
    )

    nipype_trait_names = nipype_interface.input_spec().all_trait_names()

    assert sorted(f[0] for f in pydra_task.input_spec.fields) == sorted(
        n
        for n in nipype_trait_names
        if not (
            n in INBUILT_NIPYPE_TRAIT_NAMES
            or (n.endswith("_items") and n[: -len("_items")] in nipype_trait_names)
        )
    )

    tests_fspath = pkg_root.joinpath(*output_module_path.split(".")).parent / "tests"

    logging.info("Running generated tests for %s", output_module_path)
    # Run generated pytests
    with add_to_sys_path(pkg_root):
        result = pytest.main([str(tests_fspath)])

    assert result.value == 0
