from pathlib import Path
import typing as ty
import click
import yaml
from nipype2pydra.workflow import WorkflowConverter
from nipype2pydra.package import PackageConverter
from nipype2pydra import task
from nipype2pydra.utils import to_snake_case
from nipype2pydra.cli.base import cli


@cli.command(
    name="convert",
    help="""Port Nipype task interface code to Pydra

SPECS_DIR is a directory pointing to YAML specs for each of the workflows in the package to be imported

PACKAGE_ROOT is the path to the root directory of the packages in which to generate the
converted workflow
""",
)
@click.argument("specs_dir", type=click.Path(path_type=Path, exists=True))
@click.argument("package_root", type=click.Path(path_type=Path, exists=True))
@click.argument("workflow_functions", type=str, nargs=-1)
@click.option(
    "--single-interface", type=str, help="Convert a single interface", default=None
)
def convert(
    specs_dir: Path,
    package_root: Path,
    workflow_functions: ty.List[str],
    single_interface: ty.Optional[str] = None,
) -> None:

    workflow_specs = {}
    for fspath in (specs_dir / "workflows").glob("*.yaml"):
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
            workflow_specs[f"{spec['nipype_module']}.{spec['name']}"] = spec

    interface_specs = {}
    interface_spec_callables = {}
    interfaces_dir = specs_dir / "interfaces"
    for fspath in interfaces_dir.glob("*.yaml"):
        with open(fspath, "r") as f:
            spec = yaml.safe_load(f)
            interface_specs[f"{spec['nipype_module']}.{spec['task_name']}"] = spec
        interface_spec_callables[spec["task_name"]] = fspath.parent / (
            fspath.name[: -len(".yaml")] + "_callables.py"
        )

    with open(specs_dir / "package.yaml", "r") as f:
        spec = yaml.safe_load(f)

    converter = PackageConverter(**spec)

    interfaces_only_pkg = not workflow_specs

    def get_output_module(module: str, task_name: str) -> str:
        output_module = converter.translate_submodule(
            module, sub_pkg="auto" if interfaces_only_pkg else None
        )
        output_module += "." + to_snake_case(task_name)
        return output_module

    if single_interface:
        spec = interface_specs[single_interface]
        output_module = get_output_module(spec["nipype_module"], spec["task_name"])
        output_path = package_root.joinpath(*output_module.split(".")).with_suffix(
            ".py"
        )
        if output_path.exists():
            output_path.unlink()
        task.get_converter(
            output_module=output_module,
            callables_module=interface_spec_callables[spec["task_name"]],
            package=converter,
            **spec,
        ).write(package_root)
        return

    converter.interfaces = {
        n: task.get_converter(
            output_module=get_output_module(c["nipype_module"], c["task_name"]),
            callables_module=interface_spec_callables[c["task_name"]],
            package=converter,
            **c,
        )
        for n, c in interface_specs.items()
    }

    converter.workflows = {
        n: WorkflowConverter(package=converter, **c) for n, c in workflow_specs.items()
    }

    converter.write(package_root, workflow_functions)


if __name__ == "__main__":
    import sys

    convert(sys.argv[1:])
