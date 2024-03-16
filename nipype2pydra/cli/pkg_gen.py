import typing as ty
import tempfile
from importlib import import_module
import subprocess as sp
import shutil
import tarfile
from pathlib import Path
import click
import yaml
from fileformats.generic import File
import nipype.interfaces.base.core
from nipype2pydra.utils import (
    to_snake_case,
)
from nipype2pydra.pkg_gen import (
    download_tasks_template,
    initialise_task_repo,
    NipypeInterface,
    gen_fileformats_module,
    gen_fileformats_extras_module,
)
from nipype2pydra.cli.base import cli


DEFAULT_INTERFACE_SPEC = (
    Path(__file__).parent.parent / "pkg_gen" / "resources" / "specs" / "nipype-interfaces-to-import.yaml"
)


@cli.command(
    "pkg-gen", help="Generates stub pydra packages for all nipype interfaces to import"
)
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--work-dir", type=click.Path(path_type=Path), default=None)
@click.option("--task-template", type=click.Path(path_type=Path), default=None)
@click.option("--packages-to-import", type=click.Path(path_type=Path), default=DEFAULT_INTERFACE_SPEC)
@click.option("--single-interface", type=str, nargs=2, default=None)
@click.option(
    "--example-packages",
    type=click.Path(path_type=Path),
    default=None,
    help="Packages to save into the example-spec directory",
)
@click.option(
    "--base-package",
    type=str,
    default="nipype.interfaces",
    help=("the base package which the sub-packages are relative to"),
)
def pkg_gen(
    output_dir: Path,
    work_dir: ty.Optional[Path],
    task_template: ty.Optional[Path],
    packages_to_import: ty.Optional[Path],
    single_interface: ty.Optional[ty.Tuple[str]],
    base_package: str,
    example_packages: ty.Optional[Path],
):

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp())

    if task_template is None:
        task_template_tar = work_dir / "task-template.tar.gz"
        download_tasks_template(task_template_tar)
        extract_dir = work_dir / "task_template"
        with tarfile.open(task_template_tar, "r:gz") as tar:
            tar.extractall(path=extract_dir)
        task_template = extract_dir / next(extract_dir.iterdir())

    if single_interface:
        to_import = {
            "packages": [single_interface[0]],
            "interfaces": {
                single_interface[0]: [single_interface[1]],
            },
        }
    else:
        with open(packages_to_import) as f:
            to_import = yaml.load(f, Loader=yaml.SafeLoader)

    # Wipe output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    not_interfaces = []
    unmatched_formats = []
    ambiguous_formats = []
    has_doctests = set()

    for pkg in to_import["packages"]:
        pkg_dir = initialise_task_repo(output_dir, task_template, pkg)
        pkg_formats = set()

        spec_dir = pkg_dir / "nipype-auto-conv" / "specs"
        spec_dir.mkdir(parents=True, exist_ok=True)

        # Loop through all nipype modules and create specs for their auto-conversion
        for module, interfaces in to_import["interfaces"].items():
            if module.split("/")[0] != pkg:
                continue

            # Loop through all interfaces in module
            for interface in interfaces:

                # Import interface from module
                module_str = ".".join(module.split("/"))
                nipype_module_str = base_package + "." + module_str
                nipype_module = import_module(nipype_module_str)
                nipype_interface = getattr(nipype_module, interface)
                if not issubclass(
                    nipype_interface, nipype.interfaces.base.core.Interface
                ):
                    not_interfaces.append(f"{module}.{interface}")
                    continue

                parsed = NipypeInterface.parse(nipype_interface, pkg, base_package)

                spec_name = to_snake_case(interface)
                yaml_spec = (
                    parsed.generate_yaml_spec()
                )
                unmatched_formats.extend(parsed.unmatched_formats)
                ambiguous_formats.extend(parsed.ambiguous_formats)
                pkg_formats.update(parsed.pkg_formats)
                if parsed.has_doctests:
                    has_doctests.add(f"{module_str}.{interface}")
                with open(spec_dir / (spec_name + ".yaml"), "w") as f:
                    f.write(yaml_spec)

                callables_fspath = spec_dir / f"{spec_name}_callables.py"

                with open(callables_fspath, "w") as f:
                    f.write(parsed.generate_callables(nipype_interface))

        with open(
            pkg_dir
            / "related-packages"
            / "fileformats"
            / "fileformats"
            / f"medimage_{pkg}"
            / "__init__.py",
            "w",
        ) as f:
            f.write(gen_fileformats_module(pkg_formats))

        with open(
            pkg_dir
            / "related-packages"
            / "fileformats-extras"
            / "fileformats"
            / "extras"
            / f"medimage_{pkg}"
            / "__init__.py",
            "w",
        ) as f:
            f.write(gen_fileformats_extras_module(pkg, pkg_formats))

        sp.check_call("git init", shell=True, cwd=pkg_dir)
        sp.check_call("git add --all", shell=True, cwd=pkg_dir)
        sp.check_call(
            'git commit -m"initial commit of generated stubs"', shell=True, cwd=pkg_dir
        )
        sp.check_call("git tag 0.1.0", shell=True, cwd=pkg_dir)

    if example_packages and not single_interface:
        with open(example_packages) as f:
            example_pkg_names = yaml.load(f, Loader=yaml.SafeLoader)

        basepkg = base_package
        if base_package.endswith(".interfaces"):
            basepkg = basepkg[: -len(".interfaces")]

        examples_dir = (
            Path(__file__).parent.parent.parent / "example-specs" / "task" / basepkg
        )
        if examples_dir.exists():
            shutil.rmtree(examples_dir)
        examples_dir.mkdir()
        for example_pkg_name in example_pkg_names:
            specs_dir = (
                output_dir
                / ("pydra-" + example_pkg_name)
                / "nipype-auto-conv"
                / "specs"
            )
            dest_dir = examples_dir / example_pkg_name
            shutil.copytree(specs_dir, dest_dir)

    unmatched_extensions = set(
        File.decompose_fspath(
            f.split(":")[1].strip(), mode=File.ExtensionDecomposition.single
        )[2]
        for f in unmatched_formats
    )

    print("Unmatched test input formats")
    print("\n".join(unmatched_formats))
    print("Unmatched format extensions")
    print("\n".join(sorted(unmatched_extensions)))
    print("\nAmbiguous formats")
    print("\n".join(str(p) for p in ambiguous_formats))
    print("\nWith doctests")
    print("\n".join(sorted(has_doctests)))


if __name__ == "__main__":
    import sys

    pkg_gen(sys.argv[1:])
