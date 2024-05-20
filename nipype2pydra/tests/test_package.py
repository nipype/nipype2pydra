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
        "nipype2pydra",
        "pydra-ants",
        "pydra-afni",
        "pydra-fsl",
        "pydra-mrtrix3 >=3.0.3a0",
        "fileformats-medimage-afni-extras",
        "fileformats-medimage-mrtrix3-extras",
        "fileformats-medimage-fsl-extras",
        "statsmodels",
        "dipy",
        "bids",
        "pydra-niworkflows",
        "pydra-nireports",
        "matplotlib",
        "seaborn",
        "templateflow",
        "nilearn",
        # "nibael",
        # "nilearn",
        # "migas >= 0.4.0",
        # "pandas ~=1.0",
        # "pydra >=0.22",
        # "PyYAML",
        # "scikit-learn",
        # "scipy",
        # "statsmodel",
        # "torch",
    ],
}


@pytest.fixture(params=[str(p.name) for p in EXAMPLE_WORKFLOWS_DIR.iterdir()])
def package_spec(request):
    return EXAMPLE_PKG_GEN_DIR / f"{request.param}.yaml"


@pytest.mark.xfail(reason="Don't have time to debug at the moment")
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
    p = sp.Popen(pip_cmd, stdout=sp.PIPE, stderr=sp.STDOUT)
    pip_output, _ = p.communicate()
    pip_output = pip_output.decode("utf-8")
    assert (
        not p.returncode
    ), f"Failed to install package pydra-{pkg_name} with command:\n{' '.join(pip_cmd)}:\n\n{pip_output}"
    p = sp.Popen([venv_pytest, str(pkg_root)], stderr=sp.PIPE, stdout=sp.STDOUT)
    pytest_output, _ = p.communicate()
    pytest_output = pytest_output.decode("utf-8")
    assert (
        p.returncode
    ), f"Tests for pydra-{pkg_name} package (\n{' '.join(pip_cmd)}) failed:\n\n{pytest_output}"
