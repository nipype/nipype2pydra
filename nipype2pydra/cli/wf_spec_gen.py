import shutil
from pathlib import Path
import click
from .base import cli


@cli.command(
    "wf-spec-gen",
    help="""Generates default specs for all the workflow functions found in the package

PACKAGE_DIR the directory containing the workflows to generate specs for

OUTPUT_DIR the directory to write the default specs to""",
)
@click.argument("package_dir", type=click.Path(path_type=Path))
@click.argument("output_dir", type=click.Path(path_type=Path))
def wf_spec_gen(
    package_dir: Path,
    output_dir: Path,
):
    # Wipe output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    sys.path.insert(0, str(package_dir.parent))

    for py_mod_fspath in package_dir.glob("**/*.py"):
        pass


if __name__ == "__main__":
    import sys

    wf_spec_gen(sys.argv[1:])
