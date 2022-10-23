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
    "Print out auto-generated Pydra code defining task interfaces ported from Nipype"
)
@click.argument("spec-file", type=click.File(exists=True))
@click.argument("out-file", type=click.File())
@click.option(
    "-i",
    "--interface_name",
    required=True,
    default=(),
    help="name of the interface (name used in Nipype, e.g. BET) or all (default)"
    "if all is used all interfaces from the spec file will be created",
)
def task(spec_file, interface_name, out_file):

    spec = yaml.safe_load(spec_file)

    if interface_name == "all":
        interface_list = list(spec.values())
    else:
        interface_list = [spec[interface_name]]

    converter = TaskConverter(spec_file)
    converter.pydra_specs(write=True)


@cli.command("Print out auto-generated Pydra code to createported from Nipype")
@click.argument("spec-file")
@click.argument("out-file")
def workflow(spec_file, out_file):

    spec = yaml.safe_load(spec_file)

    converter = WorkflowConverter(spec)
    converter.write_pydra(out_file)
