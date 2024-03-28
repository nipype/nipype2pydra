from pathlib import Path
import click
import yaml
import nipype2pydra.workflow
from .base import cli


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
@click.argument("yaml-specs-dir", type=click.Directory())
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
def workflow(base_function, yaml_specs_dir, package_root, output_module):

    workflow_specs = {}
    for fspath in yaml_specs_dir.glob("*.yaml"):
        with open(fspath, "r") as yaml_spec:
            spec = yaml.safe_load(yaml_spec)
            workflow_specs[spec["name"]] = spec

    converter = nipype2pydra.workflow.WorkflowConverter(
        output_module=output_module,
        workflow_specs=workflow_specs,
        **workflow_specs[base_function],
    )
    converter.generate(package_root)


if __name__ == "__main__":
    import sys

    workflow(sys.argv[1:])
