import typing as ty
import tempfile
from importlib import import_module
import subprocess as sp
import shutil
import tarfile
from pathlib import Path
import click
import yaml
import toml
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
    gen_fileformats_extras_tests,
)
from nipype2pydra.cli.base import cli
from nipype2pydra.package import PackageConverter
from nipype2pydra.workflow import WorkflowConverter
from nipype2pydra.helpers import FunctionConverter, ClassConverter


@cli.command(
    "pkg-gen",
    help="""Generates stub pydra packages for all nipype interfaces to import

SPEC_FILE is the YAML file containing the list of interfaces/workflows to import

OUTPUT_DIR is the directory to write the generated packages to
""",
)
@click.argument("spec_file", type=click.Path(path_type=Path))
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--work-dir", type=click.Path(path_type=Path), default=None)
@click.option("--task-template", type=click.Path(path_type=Path), default=None)
@click.option("--single-interface", type=str, default=None)
@click.option(
    "--example-packages",
    type=click.Path(path_type=Path),
    default=None,
    help="Packages to save into the example-spec directory",
)
@click.option(
    "--pkg-prefix",
    type=str,
    default="",
    help="The prefix to add to the package name",
)
@click.option(
    "--pkg-default",
    type=str,
    nargs=2,
    multiple=True,
    metavar="<name> <value>",
    help="name-value pairs of default values to set in the converter specs",
)
@click.option(
    "--wf-default",
    type=str,
    nargs=2,
    multiple=True,
    metavar="<name> <value>",
    help="name-value pairs of default values to set in the converter specs",
)
def pkg_gen(
    spec_file: Path,
    output_dir: Path,
    work_dir: ty.Optional[Path],
    task_template: ty.Optional[Path],
    single_interface: ty.Optional[str],
    example_packages: ty.Optional[Path],
    pkg_prefix: str,
    pkg_default: ty.List[ty.Tuple[str, str]],
    wf_default: ty.List[ty.Tuple[str, str]],
):

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp())

    pkg_defaults = dict(pkg_default)
    wf_defaults = dict(wf_default)

    with open(spec_file) as f:
        to_import = yaml.load(f, Loader=yaml.SafeLoader)

    if task_template is None:
        task_template_tar = work_dir / "task-template.tar.gz"
        download_tasks_template(task_template_tar)
        extract_dir = work_dir / "task_template"
        with tarfile.open(task_template_tar, "r:gz") as tar:
            tar.extractall(path=extract_dir)
        task_template = extract_dir / next(extract_dir.iterdir())

    # Wipe output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    not_interfaces = []
    unmatched_formats = []
    ambiguous_formats = []
    has_doctests = set()

    for pkg, spec in to_import.items():

        with_fileformats = spec.get("with_fileformats")
        interface_only_pkg = "workflows" not in spec
        pkg_dir = initialise_task_repo(
            output_dir, task_template, pkg, interface_only=interface_only_pkg
        )
        pkg_formats = set()

        spec_dir = pkg_dir / "nipype-auto-conv" / "specs"
        spec_dir.mkdir(parents=True, exist_ok=True)

        with open(spec_dir / "package.yaml", "w") as f:
            f.write(
                PackageConverter.default_spec(
                    "pydra.tasks." + pkg, pkg_prefix + pkg, defaults=pkg_defaults
                )
            )

        if not interface_only_pkg and not single_interface:
            workflows_spec_dir = spec_dir / "workflows"
            workflows_spec_dir.mkdir(parents=True, exist_ok=True)
            for wf_path in spec["workflows"]:
                parts = wf_path.split(".")
                wf_name = parts[-1]
                nipype_module_str = ".".join(parts[:-1])
                nipype_module = import_module(nipype_module_str)
                try:
                    getattr(nipype_module, wf_name)
                except AttributeError:
                    raise RuntimeError(
                        f"Did not find workflow function {wf_name} in module {nipype_module_str}"
                    )
                with open(workflows_spec_dir / (wf_path + ".yaml"), "w") as f:
                    f.write(
                        WorkflowConverter.default_spec(
                            wf_name, nipype_module_str, defaults=wf_defaults
                        )
                    )

        if "interfaces" in spec:
            interfaces_spec_dir = spec_dir / "interfaces"
            interfaces_spec_dir.mkdir(parents=True, exist_ok=True)
            # Loop through all nipype modules and create specs for their auto-conversion
            if single_interface:
                interfaces = [single_interface]
            else:
                interfaces = spec["interfaces"]
            for interface_path in interfaces:
                # Import interface from module
                parts = interface_path.split(".")
                nipype_module_str = ".".join(parts[:-1])
                interface = parts[-1]
                nipype_module = import_module(nipype_module_str)
                nipype_interface = getattr(nipype_module, interface)
                if not issubclass(
                    nipype_interface, nipype.interfaces.base.core.Interface
                ):
                    not_interfaces.append(interface_path)
                    continue

                parsed = NipypeInterface.parse(
                    nipype_interface=nipype_interface,
                    pkg=pkg,
                    base_package=pkg_prefix,
                )

                spec_name = to_snake_case(interface)
                yaml_spec = parsed.generate_yaml_spec()
                unmatched_formats.extend(parsed.unmatched_formats)
                ambiguous_formats.extend(parsed.ambiguous_formats)
                pkg_formats.update(parsed.pkg_formats)
                if parsed.has_doctests:
                    has_doctests.add(interface_path)
                with open(interfaces_spec_dir / (spec_name + ".yaml"), "w") as f:
                    f.write(yaml_spec)

                callables_fspath = interfaces_spec_dir / f"{spec_name}_callables.py"

                with open(callables_fspath, "w") as f:
                    f.write(parsed.generate_callables(nipype_interface))

        if "functions" in spec:
            functions_spec_dir = spec_dir / "functions"
            functions_spec_dir.mkdir(parents=True, exist_ok=True)
            for function_path in spec["functions"]:
                parts = function_path.split(".")
                factory_name = parts[-1]
                nipype_module_str = ".".join(parts[:-1])
                nipype_module = import_module(nipype_module_str)
                try:
                    getattr(nipype_module, factory_name)
                except AttributeError:
                    raise RuntimeError(
                        f"Did not find factory function {factory_name} in module {nipype_module_str}"
                    )

                with open(functions_spec_dir / (function_path + ".yaml"), "w") as f:
                    f.write(
                        FunctionConverter.default_spec(
                            factory_name, nipype_module_str, defaults=wf_defaults
                        )
                    )

        if "classes" in spec:
            classes_spec_dir = spec_dir / "classes"
            classes_spec_dir.mkdir(parents=True, exist_ok=True)
            for class_path in spec["classes"]:
                parts = class_path.split(".")
                factory_name = parts[-1]
                nipype_module_str = ".".join(parts[:-1])
                nipype_module = import_module(nipype_module_str)
                try:
                    getattr(nipype_module, factory_name)
                except AttributeError:
                    raise RuntimeError(
                        f"Did not find factory function {factory_name} in module {nipype_module_str}"
                    )

                with open(classes_spec_dir / (class_path + ".yaml"), "w") as f:
                    f.write(
                        ClassConverter.default_spec(
                            factory_name, nipype_module_str, defaults=wf_defaults
                        )
                    )
        if with_fileformats is None:
            with_fileformats = interface_only_pkg

        if with_fileformats:
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

            tests_dir = (
                pkg_dir
                / "related-packages"
                / "fileformats-extras"
                / "fileformats"
                / "extras"
                / f"medimage_{pkg}"
                / "tests"
            )
            tests_dir.mkdir()

            with open(tests_dir / "test_generate_sample_data.py", "w") as f:
                f.write(gen_fileformats_extras_tests(pkg, pkg_formats))

        # Remove fileformats lines from pyproject.toml
        pyproject_fspath = pkg_dir / "pyproject.toml"

        pyproject = toml.load(pyproject_fspath)

        if not with_fileformats:
            deps = pyproject["project"]["dependencies"]
            deps = [d for d in deps if d != f"fileformats-medimage-{pkg}"]
            pyproject["project"]["dependencies"] = deps
            test_deps = pyproject["project"]["optional-dependencies"]["test"]
            test_deps = [
                d for d in test_deps if d != f"fileformats-medimage-{pkg}-extras"
            ]
            pyproject["project"]["optional-dependencies"]["test"] = test_deps
        with open(pyproject_fspath, "w") as f:
            toml.dump(pyproject, f)

        if example_packages and not single_interface:
            with open(example_packages) as f:
                example_pkg_names = yaml.load(f, Loader=yaml.SafeLoader)

            examples_dir = (
                Path(__file__).parent.parent.parent / "example-specs" / "task" / pkg
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

        sp.check_call("git init", shell=True, cwd=pkg_dir)
        sp.check_call("git add --all", shell=True, cwd=pkg_dir)
        sp.check_call(
            'git commit -m"initial commit of generated stubs"', shell=True, cwd=pkg_dir
        )
        sp.check_call("git tag 0.1.0", shell=True, cwd=pkg_dir)

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
