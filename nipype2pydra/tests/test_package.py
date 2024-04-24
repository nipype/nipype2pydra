import sys
import subprocess as sp
from nipype2pydra.cli import pkg_gen, convert
from nipype2pydra.utils import show_cli_trace
from conftest import EXAMPLE_PKG_GEN_DIR


def test_complete(cli_runner, tmp_path):
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

    venv_path = tmp_path / "venv"
    venv_python = str(venv_path / "bin" / "python")
    venv_pytest = str(venv_path / "bin" / "pytest")

    sp.check_call([sys.executable, "-m", "venv", str(venv_path)])
    sp.check_call([venv_python, "-m", "pip", "install", "-e", str(pkg_root) + "[test]"])
    pytest_output = sp.check_output([venv_pytest, str(pkg_root)])

    assert "fail" not in pytest_output
    assert "error" not in pytest_output
