from pathlib import Path
import typing as ty
import shutil
import click
import yaml
from nipype2pydra.workflow import WorkflowConverter
from nipype2pydra.package import PackageConverter
from nipype2pydra import task
from nipype2pydra.utils import to_snake_case
from nipype2pydra.cli.base import cli


@cli.command(
    name="convert",
    help="""Port Nipype task interface code to Pydra

SPECS_DIR is a directory pointing to YAML specs for each of the workflows in the package to be imported

PACKAGE_ROOT is the path to the root directory of the packages in which to generate the
converted workflow

TO_INCLUDE is the list of interfaces/workflows/functions to explicitly include in the
conversion. If not provided, all workflows and interfaces will be included. Can also
be the path to a file containing a list of interfaces/workflows/functions to include
""",
)
@click.argument("specs_dir", type=click.Path(path_type=Path, exists=True))
@click.argument("package_root", type=click.Path(path_type=Path, exists=True))
@click.argument("to_include", type=str, nargs=-1)
def convert(
    specs_dir: Path,
    package_root: Path,
    to_include: ty.List[str],
) -> None:

    if len(to_include) == 1:
        if Path(to_include[0]).exists():
            with open(to_include[0], "r") as f:
                to_include = f.read().splitlines()

    with open(specs_dir / "package.yaml", "r") as f:
        package_spec = yaml.safe_load(f)

    if not to_include and "to_include" in package_spec:
        to_include = package_spec.pop("to_include")

    # Load workflow specs

    workflow_specs = {}
    for fspath in (specs_dir / "workflows").glob("*.yaml"):
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
            workflow_specs[f"{spec['nipype_module']}.{spec['name']}"] = spec

    if "interface_only" not in package_spec:
        package_spec["interface_only"] = not workflow_specs

    converter = PackageConverter(**package_spec)
    package_dir = converter.package_dir(package_root)

    if package_dir.exists():
        shutil.rmtree(package_dir)

    def get_output_module(module: str, task_name: str) -> str:
        output_module = converter.translate_submodule(
            module, sub_pkg="auto" if converter.interface_only else None
        )
        output_module += "." + to_snake_case(task_name)
        return output_module

    # Load interface specs

    interface_specs = {}
    interface_spec_callables = {}
    interfaces_dir = specs_dir / "interfaces"
    for fspath in interfaces_dir.glob("*.yaml"):
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
            interface_specs[f"{spec['nipype_module']}.{spec['task_name']}"] = spec
        interface_spec_callables[spec["task_name"]] = fspath.parent / (
            fspath.name[: -len(".yaml")] + "_callables.py"
        )

    converter.interfaces = {
        n: task.get_converter(
            output_module=get_output_module(c["nipype_module"], c["task_name"]),
            callables_module=interface_spec_callables[c["task_name"]],
            package=converter,
            **c,
        )
        for n, c in interface_specs.items()
    }

    converter.workflows = {
        n: WorkflowConverter(package=converter, **c) for n, c in workflow_specs.items()
    }

    converter.write(package_root, to_include)


if __name__ == "__main__":
    import sys

    convert(sys.argv[1:])
