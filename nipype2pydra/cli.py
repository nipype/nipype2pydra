from pathlib import Path
import click
import yaml
from nipype2pydra import __version__
from .task import TaskConverter
from .workflow import WorkflowConverter


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

OUTPUT_BASE_DIR is the path of generated module file
"""
)
@click.argument("yaml-spec", type=click.File())
@click.argument("output-file", type=Path)
@click.option(
    "-c",
    "--callables",
    type=click.File(),
    default=None,
    help="a Python file containing callable functions required in the command interface",
)
def task(yaml_spec, output_file, callables):

    spec = yaml.safe_load(yaml_spec)

    converter = TaskConverter(callables_module=callables, **spec)
    converter.generate(output_file)


@cli.command(help="Port Nipype workflow creation functions to Pydra")
@click.argument("yaml-spec", type=click.File())
@click.argument("output-module-file", type=click.File(mode="w"))
def workflow(yaml_spec, output_module_file):

    spec = yaml.safe_load(yaml_spec)

    converter = WorkflowConverter(spec)
    converter.generate(output_module_file)
