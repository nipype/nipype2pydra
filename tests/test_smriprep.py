from nipype2pydra.cli import cli
from nipype2pydra.utils import show_cli_trace


def test_smriprep(pkg_dir, cli_runner):

    result = cli_runner(
        cli,
        [
            f"{pkg_dir}/example-specs/smriprep.yaml",
            f"${pkg_dir}/outputs/smriprep_new.py"
        ]
    )

    assert result.exit_code == 0, show_cli_trace(result)
