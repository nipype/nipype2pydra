from pathlib import Path
import click
import yaml
from nipype2pydra import __version__
from .task import TaskConverter


# Define the base CLI entrypoint
@click.group()
@click.version_option(version=__version__)
def cli():
    pass


@cli.command(
    help="""Port Nipype task interface code to Pydra

YAML_SPEC is a YAML file which defines interfaces to be imported along with an
manually specified aspects of the conversion see
https://github.com/nipype/nipype2pydra/tree/main/example-specs for examples

PACKAGE_ROOT is the path to the root directory of the package in which to generate the
converted module file
"""
)
@click.argument("yaml-spec", type=click.File())
@click.argument("package-root", type=Path)
@click.option(
    "-c",
    "--callables",
    type=click.File(),
    default=None,
    help="a Python file containing callable functions required in the command interface",
)
@click.option(
    "--output-module",
    "-m",
    type=str,
    default=None,
    help=(
        "the output module to store the converted task into relative to the `pydra.tasks` "
        "package. If not provided, then the path relative to `nipype.interfaces` in the "
        "source interface will be used instead"
    ),
)
def task(yaml_spec, package_root, callables, output_module):

    spec = yaml.safe_load(yaml_spec)

    converter = TaskConverter(
        output_module=output_module, callables_module=callables, **spec
    )
    converter.generate(package_root)
