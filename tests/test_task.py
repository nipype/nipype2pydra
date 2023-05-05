from importlib import import_module
import yaml
from conftest import show_cli_trace
from nipype2pydra.cli import task as task_cli
from nipype2pydra.utils import import_module_from_path


def test_task_conversion(task_spec_file, cli_runner, work_dir):

    with open(task_spec_file) as f:
        task_spec = yaml.safe_load(f)
    output_file = work_dir / "pydra_module.py"

    result = cli_runner(
        task_cli,
        args=[
            str(task_spec_file),
            str(output_file),
        ],
    )

    assert result.exit_code == 0, show_cli_trace(result)

    pydra_module = import_module_from_path(output_file)
    pydra_task = getattr(pydra_module, task_spec["task_name"])
    nipype_interface = getattr(
        import_module(task_spec["nipype_module"]), task_spec["task_name"]
    )

    assert sorted(f[0] for f in pydra_task.input_spec.fields) == sorted(nipype_interface.input_spec().all_trait_names())
