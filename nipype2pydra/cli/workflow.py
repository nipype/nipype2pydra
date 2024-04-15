from pathlib import Path
import typing as ty
import click
import yaml
from nipype2pydra.workflow import WorkflowConverter, PackageConverter
from nipype2pydra import task
from nipype2pydra.utils import to_snake_case
from nipype2pydra.cli.base import cli


@cli.command(
    name="workflow",
    help="""Port Nipype task interface code to Pydra

BASE_FUNCTION is the name of the function that constructs the workflow, which is to be imported

YAML_SPECS_DIR is a directory pointing to YAML specs for each of the workflows in the package to be imported

PACKAGE_ROOT is the path to the root directory of the packages in which to generate the
converted workflow
""",
)
@click.argument("specs_dir", type=click.Path(path_type=Path, exists=True))
@click.argument("package_root", type=click.Path(path_type=Path, exists=True))
@click.argument("workflow_functions", type=str, nargs=-1)
def workflow(
    specs_dir: Path,
    package_root: Path,
    workflow_functions: ty.List[str],
) -> None:

    workflow_specs = {}
    for fspath in (specs_dir / "workflows").glob("*.yaml"):
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
            workflow_specs[spec["name"]] = spec

    interface_specs = {}
    interface_spec_callables = {}
    interfaces_dir = specs_dir / "interfaces"
    for fspath in interfaces_dir.glob("*.yaml"):
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
            interface_specs[spec["task_name"]] = spec
        interface_spec_callables[spec["task_name"]] = fspath.parent / (
            fspath.name[: -len(".yaml")] + "_callables.py"
        )

    with open(specs_dir / "package.yaml", "r") as f:
        spec = yaml.safe_load(f)

    converter = PackageConverter(
        workflows=workflow_specs,
        interfaces=interface_specs,
        **spec,
    )

    converter.interfaces = {
        n: task.get_converter(
            output_module=(
                converter.translate_submodule(c["nipype_module"])
                + "."
                + to_snake_case(c["task_name"])
            ),
            callables_module=interface_spec_callables[n],
            **c,
        )
        for n, c in interface_specs.items()
    }

    converter.workflows = {
        n: WorkflowConverter(package=converter, **c) for n, c in workflow_specs.items()
    }

    converter.write(package_root, workflow_functions)


if __name__ == "__main__":
    import sys

    workflow(sys.argv[1:])
