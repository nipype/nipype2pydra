from pathlib import Path
from copy import copy
import click
import yaml
import nipype2pydra.workflow
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
@click.argument("base_function", type=str)
@click.argument("yaml-specs-dir", type=click.Path(path_type=Path, exists=True))
@click.argument("package-root", type=click.Path(path_type=Path))
@click.option(
    "--output-module",
    "-m",
    type=str,
    default=None,
    help=(
        "the output module to store the converted task into relative to the `pydra.tasks` "
        "package. If not provided, then the path relative to base package in the "
        "source function will be used instead"
    ),
)
@click.option(
    "--interfaces-dir",
    "-i",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help=(
        "the path to the YAML file containing the interface specs for the tasks in the workflow. "
        "If not provided, then the interface specs are assumed to be defined in the "
        "workflow YAML specs"
    ),
)
def workflow(
    base_function: str,
    yaml_specs_dir: Path,
    package_root: Path,
    output_module: str,
    interfaces_dir: Path,
) -> None:

    workflow_specs = {}
    for fspath in yaml_specs_dir.glob("*.yaml"):
        with open(fspath, "r") as yaml_spec:
            spec = yaml.safe_load(yaml_spec)
            workflow_specs[spec["name"]] = spec

    interface_specs = {}
    if interfaces_dir:
        for fspath in interfaces_dir.glob("*.yaml"):
            with open(fspath, "r") as yaml_spec:
                spec = yaml.safe_load(yaml_spec)
                interface_specs[spec["name"]] = spec

    kwargs = copy(workflow_specs[base_function])
    if output_module:
        kwargs["output_module"] = output_module

    converter = nipype2pydra.workflow.WorkflowConverter(
        workflow_specs=workflow_specs,
        interface_specs=interface_specs,
        **kwargs,
    )
    converter.write(package_root)


if __name__ == "__main__":
    import sys

    workflow(sys.argv[1:])
