import sys
import shutil
import subprocess as sp
import pytest
import toml
from nipype2pydra.cli import pkg_gen, convert
from nipype2pydra.utils import show_cli_trace
from conftest import EXAMPLE_WORKFLOWS_DIR, EXAMPLE_PKG_GEN_DIR


ADDITIONAL_PACKAGES = {
    "niworkflows": [
        "bids",
        "templateflow",
        "pydra-ants",
        "pydra-afni",
    ],
    "mriqc": [
        "pydra-ants",
        "pydra-afni",
        "pydra-fsl",
        "pydra-mrtrix3 >=3.0.3a0",
        "fileformats-medimage-afni-extras",
        "fileformats-medimage-mrtrix3-extras",
        "fileformats-medimage-fsl-extras",
    ],
}


@pytest.fixture(params=[str(p.name) for p in EXAMPLE_WORKFLOWS_DIR.iterdir()])
def package_spec(request):
    return EXAMPLE_PKG_GEN_DIR / f"{request.param}.yaml"


# @pytest.mark.xfail("Don't have time to debug at the moment")
def test_package_complete(package_spec, cli_runner, tmp_path, tasks_template_args):
    pkg_name = package_spec.stem
    repo_output = tmp_path / "repo"
    repo_output.mkdir()

    result = cli_runner(
        pkg_gen,
        [
            str(package_spec),
            str(repo_output),
        ]
        + tasks_template_args,
    )
    assert result.exit_code == 0, show_cli_trace(result)
    pkg_root = repo_output / f"pydra-{pkg_name}"
    assert pkg_root.exists()

    pyproject_fspath = pkg_root / "pyproject.toml"

    pyproject = toml.load(pyproject_fspath)
    pyproject["project"]["dependencies"].extend(ADDITIONAL_PACKAGES.get(pkg_name, []))
    with open(pyproject_fspath, "w") as f:
        toml.dump(pyproject, f)

    specs_dir = pkg_root / "nipype-auto-conv" / "specs"
    shutil.rmtree(specs_dir)
    shutil.copytree(EXAMPLE_WORKFLOWS_DIR / pkg_name, specs_dir)

    result = cli_runner(
        convert,
        [
            str(pkg_root / "nipype-auto-conv/specs"),
            str(pkg_root),
        ],
    )
    assert result.exit_code == 0, show_cli_trace(result)

    pkg_dir = pkg_root / "pydra" / "tasks" / pkg_name
    assert pkg_dir.exists()

    venv_path = tmp_path / "venv"
    venv_python = str(venv_path / "bin" / "python")
    venv_pytest = str(venv_path / "bin" / "pytest")

    sp.check_call([sys.executable, "-m", "venv", str(venv_path)])
    pip_cmd = [venv_python, "-m", "pip", "install", "-e", str(pkg_root) + "[test]"]
    try:
        sp.check_call(pip_cmd)
    except sp.CalledProcessError:
        raise RuntimeError(
            f"Failed to install package {pkg_name} with command:\n{' '.join(pip_cmd)}"
        )
    pytest_cmd = [venv_pytest, str(pkg_root)]
    try:
        pytest_output = sp.check_output(pytest_cmd).decode("utf-8")
    except sp.CalledProcessError:
        raise RuntimeError(
            f"Tests of generated package '{pkg_name}' failed when running, "
            f"'\n{' '.join(pytest_cmd)}':\n\n{pytest_output}"
        )

    assert "fail" not in pytest_output
    assert "error" not in pytest_output
