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
    help="Print out auto-generated Pydra code defining task interfaces ported from Nipype"
)
@click.argument("spec-file", type=click.File())
@click.argument("out-file", type=click.File(mode="w"))
@click.option(
    "-i",
    "--interface_name",
    multiple=True,
    default=[],
    help=(
        "name of the interfaces (name used in Nipype, e.g. BET) or all (default)"
        "if all is used all interfaces from the spec file will be created"
    ),
)
def task(spec_file, out_file, interface_name):

    spec = yaml.safe_load(spec_file)

    if not interface_name:
        interface_list = list(spec.values())
    else:
        interface_list = [spec[n] for n in interface_name]

    converter = TaskConverter(spec_file)
    converter.pydra_specs(write=True)


@cli.command(help="Print out auto-generated Pydra code to createported from Nipype")
@click.argument("spec-file", type=click.File())
@click.argument("out-file", type=click.File(mode="w"))
def workflow(spec_file, out_file):

    spec = yaml.safe_load(spec_file)

    converter = WorkflowConverter(spec)
    converter.write_pydra(out_file)
