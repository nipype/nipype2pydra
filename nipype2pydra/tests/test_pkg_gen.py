from nipype2pydra.cli.pkg_gen import pkg_gen
from conftest import show_cli_trace


def test_pkg_gen(cli_runner, tmp_path):
    outputs_dir = tmp_path / "output-dir"
    outputs_dir.mkdir()

    result = cli_runner(
        pkg_gen,
        [
            str(outputs_dir),
            "--work-dir",
            str(tmp_path / "work-dir"),
        ],
    )
    assert result.exit_code == 0, show_cli_trace(result)
