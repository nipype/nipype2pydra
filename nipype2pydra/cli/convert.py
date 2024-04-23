from pathlib import Path
import typing as ty
import shutil
import logging
import click
import yaml
from nipype2pydra.package import PackageConverter
from nipype2pydra.cli.base import cli

logger = logging.getLogger(__name__)


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

    # Load package converter from spec
    with open(specs_dir / "package.yaml", "r") as f:
        package_spec = yaml.safe_load(f)

    # Get default value for 'to_include' if not provided in the spec
    if len(to_include) == 1:
        if Path(to_include[0]).exists():
            with open(to_include[0], "r") as f:
                to_include = f.read().splitlines()
    spec_to_include = package_spec.pop("to_include", None)
    if spec_to_include:
        if not to_include:
            to_include = spec_to_include
        else:
            logger.info(
                "Overriding the following 'to_include' value in the spec: %s",
                spec_to_include,
            )

    # Load interface and workflow specs
    workflow_yamls = list((specs_dir / "workflows").glob("*.yaml"))
    interface_yamls = list((specs_dir / "interfaces").glob("*.yaml"))

    # Initialise PackageConverter
    if package_spec.get("interface_only", None) is None:
        package_spec["interface_only"] = not workflow_yamls
    converter = PackageConverter(**package_spec)

    # Clean previous version of output dir
    package_dir = converter.package_dir(package_root)
    output_dir = package_dir / "auto" if converter.interface_only else package_dir
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # Load interface specs
    for fspath in interface_yamls:
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
        converter.add_interface_from_spec(
            spec=spec,
            callables_file=(
                fspath.parent / (fspath.name[: -len(".yaml")] + "_callables.py")
            ),
        )

    # Load workflow specs
    for fspath in workflow_yamls:
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
        converter.add_workflow_from_spec(spec)

    # Write out converted package
    converter.write(package_root, to_include)


if __name__ == "__main__":
    import sys

    convert(sys.argv[1:])
