from pathlib import Path
import click
import yaml
import nipype2pydra.task
from .base import cli


@cli.command(
    name="task",
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
    type=click.Path(path_type=Path, exists=True, dir_okay=False, resolve_path=True),
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

    if callables is None:
        callables_default = yaml_spec.parent / (yaml_spec.stem + "_callables.py")
        if callables_default.exists():
            callables = callables_default

    converter = nipype2pydra.task.get_converter(
        output_module=output_module, callables_module=callables, **spec
    )
    converter.generate(package_root)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    import nipype2pydra.utils

    outputs_path = Path(__file__).parent.parent / "outputs" / "testing"

    outputs_path.mkdir(parents=True, exist_ok=True)

    spec_file = sys.argv[1]
    with open(spec_file) as f:
        spec = yaml.load(f, Loader=yaml.SafeLoader)

    converter = nipype2pydra.task.get_converter(
        output_module=spec["nipype_module"].split("interfaces.")[-1]
        + ".auto."
        + nipype2pydra.utils.to_snake_case(spec["task_name"]),
        **spec,
    )
    converter.generate(outputs_path)
