from conftest import show_cli_trace
from nipype2pydra.cli import task as task_cli


def test_task_conversion(example_specs_dir, cli_runner, work_dir):

    result = cli_runner(
        task_cli,
        args=[
            str(example_specs_dir / "ants_registration.yml"),
            str(work_dir / "ants" / "registration.py"),
        ],
    )

    assert result.exit_code == 0, show_cli_trace(result)
