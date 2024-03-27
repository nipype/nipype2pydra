from pathlib import Path
import click
import yaml
import nipype2pydra.workflow
from .base import cli


@cli.command(
    name="workflow",
    help="""Port Nipype task interface code to Pydra

YAML_SPEC is a YAML file which defines the workflow function to be imported

PACKAGE_ROOT is the path to the root directory of the packages in which to generate the
converted workflow
""",
)
@click.argument("yaml-spec", type=click.File())
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
def workflow(yaml_spec, package_root, callables, output_module):

    spec = yaml.safe_load(yaml_spec)

    converter = nipype2pydra.workflow.WorkflowConverter(
        output_module=output_module, **spec
    )
    converter.generate(package_root)


if __name__ == "__main__":
    import sys

    workflow(sys.argv[1:])
