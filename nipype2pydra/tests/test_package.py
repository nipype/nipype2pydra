import sys
from importlib import import_module
from nipype2pydra.cli import pkg_gen, convert
from nipype2pydra.utils import show_cli_trace
from conftest import EXAMPLE_PKG_GEN_DIR


def test_convert_package(cli_runner, tmp_path):
    repo_output = tmp_path / "repo"
    repo_output.mkdir()
    niworkflows_pkg_spec = EXAMPLE_PKG_GEN_DIR / "niworkflows.yaml"

    result = cli_runner(
        pkg_gen,
        [
            str(niworkflows_pkg_spec),
            str(repo_output),
        ],
    )
    assert result.exit_code == 0, show_cli_trace(result)
    repo_dir = repo_output / "pydra-niworkflows"
    assert repo_dir.exists()

    pkg_root = tmp_path / "package"
    pkg_root.mkdir()

    result = cli_runner(
        convert,
        [
            str(repo_dir / "nipype-auto-conv/specs"),
            str(pkg_root),
        ],
    )
    assert result.exit_code == 0, show_cli_trace(result)

    pkg_dir = pkg_root / "pydra" / "tasks" / "niworkflows"
    assert pkg_dir.exists()

    sys.path.insert(0, str(pkg_root))
    import_module("pydra.tasks.niworkflows")
    sys.path.pop(0)
