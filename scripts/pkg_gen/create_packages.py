import os
import typing as ty
import tempfile
import re
import subprocess as sp
import shutil
import tarfile
from pathlib import Path
import requests
import click
import yaml

RESOURCES_DIR = Path(__file__).parent / "resources"


def download_tasks_template(output_path: Path):
    """Downloads the latest pydra-tasks-template to the output path"""

    release_url = (
        "https://api.github.com/repos/nipype/pydra-tasks-template/releases/latest"
    )
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "nipype2pydra"}

    response = requests.get(release_url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(
            f"Did not find release at '{release_url}'"
        )
    data = response.json()
    tarball_url = data["tarball_url"]

    response = requests.get(tarball_url)

    if response.status_code == 200:
        # Save the response content to a file
        with open(output_path, "wb") as f:
            f.write(response.content)
    else:
        raise RuntimeError(
            f"Could not download the pydra-tasks template at {release_url}"
        )


@click.command(help="Generates stub pydra packages for all nipype interfaces to import")
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--work-dir", type=click.Path(path_type=Path), default=None)
@click.option("--task-template", type=click.Path(path_type=Path), default=None)
def generate_packages(
    output_dir: Path, work_dir: ty.Optional[Path], task_template: ty.Optional[Path]
):

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp())

    if task_template is None:
        task_template_tar = work_dir / "task-template.tar.gz"
        download_tasks_template(task_template_tar)
        extract_dir = work_dir / "task_template"
        with tarfile.open(task_template_tar, 'r:gz') as tar:
            tar.extractall(path=extract_dir)
        task_template = extract_dir / next(extract_dir.iterdir())

    with open(Path(__file__).parent.parent.parent / "nipype-interfaces-to-import.yaml") as f:
        to_import = yaml.load(f, Loader=yaml.SafeLoader)

    # Wipe output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    for pkg in to_import["packages"]:

        pkg_dir = output_dir / f"pydra-{pkg}"
        pkg_dir.mkdir()

        def copy_ignore(_, names):
            return [n for n in names if n in (".git", "__pycache__", ".pytest_cache")]

        shutil.copytree(task_template, pkg_dir, ignore=copy_ignore)

        # Setup script to auto-convert nipype interfaces
        auto_conv_dir = pkg_dir / "nipype-auto-conv"
        specs_dir = auto_conv_dir / "specs"
        specs_dir.mkdir(parents=True)
        shutil.copy(RESOURCES_DIR / "nipype-auto-convert.py", auto_conv_dir / "generate")
        os.chmod(auto_conv_dir / "generate", 0o755)  # make executable

        # Setup GitHub workflows
        gh_workflows_dir = pkg_dir / ".github" / "workflows"
        gh_workflows_dir.mkdir(parents=True)
        shutil.copy(RESOURCES_DIR / "pythonpackage.yaml", gh_workflows_dir / "pythonpackage.yaml")

        # Add in conftest.py
        shutil.copy(RESOURCES_DIR / "conftest.py", pkg_dir / "conftest.py")

        # Add "pydra.tasks.<pkg>.auto to gitignore"
        with open(pkg_dir / ".gitignore", "a") as f:
            f.write("\npydra/tasks/{pkg}/auto")

        # rename tasks directory
        (pkg_dir / "pydra" / "tasks" / "CHANGEME").rename(pkg_dir / "pydra" / "tasks" / pkg)

        # Replace "CHANGEME" string with pkg name
        for fspath in pkg_dir.glob("**/*"):
            if fspath.is_dir():
                continue
            with open(fspath) as f:
                contents = f.read()
            contents = re.sub(r"(?<![0-9a-zA-Z])CHANGEME(?![0-9a-zA-Z])", pkg, contents)
            with open(fspath, "w") as f:
                f.write(contents)

        for module, interfaces in to_import["interfaces"].items():
            if module.split("/")[0] != pkg:
                continue
            module_spec_dir = specs_dir.joinpath(*module.split("/"))
            module_spec_dir.mkdir(parents=True)
            for interface in interfaces:
                callables_fspath = module_spec_dir / f"{interface}_callables.py"
                spec_stub = {
                    "task_name": interface,
                    "nipype_module": "nipype.interfaces." + ".".join(module.split("/")),
                    "output_requirements": "# dict[output-field, list[input-field]] : the required input fields for output-field",
                    "inputs_metadata": "# dict[input-field, dict[str, Any]] : additional metadata to be inserted into input field",
                    "inputs_drop": "# list[input-field] : input fields to drop from the spec",
                    "output_templates": "# dict[input-field, str] : \"output_file_template\" to provide to input field",
                    "output_callables": f"# dict[output-field, str] : name of function defined in {callables_fspath.name} that retrieves value for output",
                    "doctest": "# dict[str, Any]: key-value pairs to provide as inputs to the doctest + the expected value of \"cmdline\" as special key-value pair",
                    "tests_inputs": "# List of inputs to pass to tests",
                    "tests_outputs": "# list of outputs expected from tests",
                }
                yaml_str = yaml.dump(spec_stub, indent=2, sort_keys=False)
                # strip inserted line-breaks in long strings (so they can be converted to in-line comments)
                yaml_str = re.sub(r"\n  ", " ", yaml_str)
                # extract comments after they have been dumped as strings
                yaml_str = re.sub(r"'#(.*)'", r" # \1", yaml_str)
                with open(module_spec_dir / (interface + ".yaml"), "w") as f:
                    f.write(yaml_str)
                with open(callables_fspath, "w") as f:
                    f.write(
                        f'"""Module to put any functions that are referred to in {interface}.yaml"""\n'
                    )

        sp.check_call("git init", shell=True, cwd=pkg_dir)
        sp.check_call("git add --all", shell=True, cwd=pkg_dir)
        sp.check_call('git commit -m"initial commit of generated stubs"', shell=True, cwd=pkg_dir)
        sp.check_call("git tag 0.1.0", shell=True, cwd=pkg_dir)


if __name__ == "__main__":
    import sys

    generate_packages(sys.argv[1:])
