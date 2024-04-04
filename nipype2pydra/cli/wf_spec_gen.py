import shutil
import os.path
import re
import typing as ty
import inspect
from importlib import import_module
from pathlib import Path
import click
import attrs
import yaml
from nipype2pydra.cli.base import cli
from nipype2pydra.workflow import WorkflowConverter


@cli.command(
    "wf-spec-gen",
    help="""Generates default specs for all the workflow functions found in the package

PACKAGE_DIR the directory containing the workflows to generate specs for

OUTPUT_DIR the directory to write the default specs to""",
)
@click.argument("package_dir", type=click.Path(path_type=Path))
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--glob", type=str, help="package glob", default="**/*.py")
@click.option(
    "--default",
    type=str,
    nargs=2,
    multiple=True,
    metavar="<name> <value>",
    help="name-value pairs of default values to set in the converter specs",
)
def wf_spec_gen(
    package_dir: Path,
    output_dir: Path,
    glob: str,
    default: ty.List[ty.Tuple[str, str]],
):
    # Wipe output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    sys.path.insert(0, str(package_dir.parent))

    def matches_criteria(func):
        src = inspect.getsource(func)
        return bool(re.findall(r"^\s+(\w+)\s*=.*\bWorkflow\(", src, flags=re.MULTILINE))

    for py_mod_fspath in package_dir.glob(glob):
        mod_path = (
            package_dir.name
            + "."
            + str(py_mod_fspath.relative_to(package_dir))[: -len(".py")].replace(
                os.path.sep, "."
            )
        )
        if mod_path.endswith(".__init__"):
            mod_path = mod_path[: -len(".__init__")]
        mod = import_module(mod_path)
        for func_name in dir(mod):
            func = getattr(mod, func_name)
            if (
                inspect.isfunction(func)
                and matches_criteria(func)
                and func.__module__ == mod_path
            ):
                conv = WorkflowConverter(
                    name=func_name,
                    nipype_name=func_name,
                    nipype_module=mod_path,
                    **{n: eval(v) for n, v in default},
                )
                dct = attrs.asdict(conv)
                dct["input_struct"] = list(dct["input_struct"])
                dct["nipype_module"] = dct["nipype_module"].__name__
                del dct["workflow_specs"]
                del dct["output_module"]
                for k in dct:
                    if not dct[k]:
                        dct[k] = None
                yaml_str = yaml.dump(dct, sort_keys=False)
                for k in dct:
                    fld = getattr(attrs.fields(WorkflowConverter), k)
                    hlp = fld.metadata.get("help")
                    if hlp:
                        yaml_str = re.sub(
                            r"^(" + k + r"):",
                            "# " + hlp + r"\n\1:",
                            yaml_str,
                            flags=re.MULTILINE,
                        )
                yaml_str = yaml_str.replace(": null", ":")
                with open(
                    output_dir / (mod_path + "." + func_name + ".yaml"), "w"
                ) as f:
                    f.write(yaml_str)


if __name__ == "__main__":
    import sys

    wf_spec_gen(sys.argv[1:])


# Create "stubs" for each of the available fields
@classmethod
def _fields_stub(cls, name, category_class, values=None):
    """Used, in conjunction with some find/replaces after dumping, to
    insert comments into the YAML file"""
    dct = {}
    for field in attrs.fields(category_class):
        field_name = f"{name}.{field.name}"
        try:
            val = values[field.name]
        except (KeyError, TypeError):
            val = (
                field.default
                if (
                    field.default != attrs.NOTHING
                    and not isinstance(field.default, attrs.Factory)
                )
                else None
            )
        else:
            if isinstance(val, ty.Iterable) and not val:
                val = None
        dct[field_name] = val
    return dct
