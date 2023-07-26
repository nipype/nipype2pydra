import os
import typing as ty
import tempfile
import re
from importlib import import_module
import subprocess as sp
import shutil
import tarfile
from pathlib import Path
import attrs
import requests
import click
import yaml
import nipype.interfaces.base.core
from nipype2pydra.task import InputsConverter, OutputsConverter, TestsGenerator, DocTestGenerator


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

    not_interfaces = []

    for pkg in to_import["packages"]:

        pkg_dir = output_dir / f"pydra-{pkg}"

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
        gh_workflows_dir.mkdir(parents=True, exist_ok=True)
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
                spec_stub = {}

                def fields_stub(type_):
                    """Used, in conjunction with some find/replaces after dumping, to
                    insert comments into the YAML file"""
                    dct = {}
                    for field in attrs.fields(type_):
                        tp = field.type
                        if tp.__module__ == "builtins":
                            tp_name = tp.__name__
                        else:
                            tp_name = str(tp).lower()
                        dct[field.name] = f"# {tp_name} - " + field.metadata['help'].replace("\n                ", "\n    # ") + "#"
                    return dct
                nipype_module_str = "nipype.interfaces." + ".".join(module.split("/"))
                nipype_module = import_module(nipype_module_str)
                nipype_interface = getattr(nipype_module, interface)
                if not issubclass(nipype_interface, nipype.interfaces.base.core.Interface):
                    not_interfaces.append(f"{module}.{interface}")
                    continue
                spec_stub = {
                    "task_name": interface,
                    "nipype_module": nipype_module_str,
                    "nipype_name": None,
                    "inputs": fields_stub(InputsConverter),
                    "outputs": fields_stub(OutputsConverter),
                    "test": fields_stub(TestsGenerator),
                    "doctest": fields_stub(DocTestGenerator),
                }
                yaml_str = yaml.dump(spec_stub, indent=4, sort_keys=False, width=4096)
                yaml_str = re.sub(r"""("|')#""", "\n    #", yaml_str)
                yaml_str = re.sub(r"""#("|')""", "", yaml_str)
                yaml_str = yaml_str.replace("typing.", "")
                yaml_str = yaml_str.replace(r"\n", "\n")
                yaml_str = yaml_str.replace(" null", "")
                inputs_desc = ""
                if nipype_interface.input_spec:
                    for inpt_name, inpt in nipype_interface.input_spec().traits().items():
                        if inpt_name in ("trait_added", "trait_modified"):
                            continue
                        inpt_desc = inpt.desc.replace('\n', ' ') if inpt.desc else ""
                        inputs_desc += f"# {inpt_name} ({type(inpt.trait_type).__name__.lower()}): {inpt_desc}\n"
                outputs_desc = ""
                if nipype_interface.output_spec:
                    for outpt_name, outpt in nipype_interface.output_spec().traits().items():
                        if inpt_name in ("trait_added", "trait_modified"):
                            continue
                        outpt_desc = outpt.desc.replace('\n', ' ') if outpt.desc else ""
                        outputs_desc += f"# {outpt_name} ({type(outpt.trait_type).__name__.lower()}): {outpt_desc}\n"
                # Create a preamble at the top of the specificaiton explaining what to do
                preamble = (
                    f"""# This file is used to manually specify the semi-automatic conversion
                    # of '{module}.{interface}' from Nipype to Pydra. Please fill in the empty fields
                    # below where appropriate
                    #
                    # Nipype Inputs Ref.
                    # ------------------
                    {inputs_desc}#
                    # Nipype Outputs Ref.
                    # -------------------
                    {outputs_desc}\n"""
                ).replace("                    #", "#")
                with open(module_spec_dir / (interface + ".yaml"), "w") as f:
                    f.write(preamble + yaml_str)
                print(preamble + yaml_str)
                with open(callables_fspath, "w") as f:
                    f.write(
                        f'"""Module to put any functions that are referred to in {interface}.yaml"""\n'
                    )

        sp.check_call("git init", shell=True, cwd=pkg_dir)
        sp.check_call("git add --all", shell=True, cwd=pkg_dir)
        sp.check_call('git commit -m"initial commit of generated stubs"', shell=True, cwd=pkg_dir)
        sp.check_call("git tag 0.1.0", shell=True, cwd=pkg_dir)

    print("\n".join(not_interfaces))


if __name__ == "__main__":
    import sys

    generate_packages(sys.argv[1:])
