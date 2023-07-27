import os
import typing as ty
import tempfile
import re
from importlib import import_module
import subprocess as sp
from copy import copy
import shutil
import tarfile
from pathlib import Path
import attrs
from warnings import warn
import requests
import click
import yaml
import fileformats.core.utils
import fileformats.core.mixin
from fileformats.generic import File
from fileformats.medimage import Nifti1, NiftiGz, Bval, Bvec
from fileformats.misc import Dicom
from fileformats.text import Txt
from fileformats.datascience import MatFile, DatFile
from fileformats.serialization import Xml
import nipype.interfaces.base.core
from nipype2pydra.task import (
    InputsConverter,
    OutputsConverter,
    TestsGenerator,
    DocTestGenerator,
)


RESOURCES_DIR = Path(__file__).parent / "resources"

EXPECTED_FORMATS = [Nifti1, NiftiGz, Txt, MatFile, DatFile, Xml]


def download_tasks_template(output_path: Path):
    """Downloads the latest pydra-tasks-template to the output path"""

    release_url = (
        "https://api.github.com/repos/nipype/pydra-tasks-template/releases/latest"
    )
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "nipype2pydra"}

    response = requests.get(release_url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Did not find release at '{release_url}'")
    data = response.json()
    tarball_url = data["tarball_url"]

    response = requests.get(tarball_url)

    if response.status_code == 200:
        # Save the response content to a file
        with open(output_path, "wb") as f:
            f.write(response.content)
    else:
        raise RuntimeError(
            f"Could not download the pydra-tasks template at {release_url}"
        )


@click.command(help="Generates stub pydra packages for all nipype interfaces to import")
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--work-dir", type=click.Path(path_type=Path), default=None)
@click.option("--task-template", type=click.Path(path_type=Path), default=None)
def generate_packages(
    output_dir: Path, work_dir: ty.Optional[Path], task_template: ty.Optional[Path]
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

    with open(
        Path(__file__).parent.parent.parent / "nipype-interfaces-to-import.yaml"
    ) as f:
        to_import = yaml.load(f, Loader=yaml.SafeLoader)

    # Wipe output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    not_interfaces = []
    unmatched_formats = []
    ambiguous_formats = []

    for pkg in to_import["packages"]:
        pkg_dir = output_dir / f"pydra-{pkg}"

        def copy_ignore(_, names):
            return [n for n in names if n in (".git", "__pycache__", ".pytest_cache")]

        shutil.copytree(task_template, pkg_dir, ignore=copy_ignore)

        # Setup script to auto-convert nipype interfaces
        auto_conv_dir = pkg_dir / "nipype-auto-conv"
        specs_dir = auto_conv_dir / "specs"
        specs_dir.mkdir(parents=True)
        shutil.copy(
            RESOURCES_DIR / "nipype-auto-convert.py", auto_conv_dir / "generate"
        )
        os.chmod(auto_conv_dir / "generate", 0o755)  # make executable

        # Setup GitHub workflows
        gh_workflows_dir = pkg_dir / ".github" / "workflows"
        gh_workflows_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(
            RESOURCES_DIR / "pythonpackage.yaml",
            gh_workflows_dir / "pythonpackage.yaml",
        )

        # Add in conftest.py
        shutil.copy(RESOURCES_DIR / "conftest.py", pkg_dir / "conftest.py")

        # Add "pydra.tasks.<pkg>.auto to gitignore"
        with open(pkg_dir / ".gitignore", "a") as f:
            f.write("\npydra/tasks/{pkg}/auto")

        # rename tasks directory
        (pkg_dir / "pydra" / "tasks" / "CHANGEME").rename(
            pkg_dir / "pydra" / "tasks" / pkg
        )

        # Replace "CHANGEME" string with pkg name
        for fspath in pkg_dir.glob("**/*"):
            if fspath.is_dir():
                continue
            with open(fspath) as f:
                contents = f.read()
            contents = re.sub(r"(?<![0-9a-zA-Z])CHANGEME(?![0-9a-zA-Z])", pkg, contents)
            with open(fspath, "w") as f:
                f.write(contents)

        for module, interfaces in to_import["interfaces"].items():
            if module.split("/")[0] != pkg:
                continue
            module_spec_dir = specs_dir.joinpath(*module.split("/"))
            module_spec_dir.mkdir(parents=True)
            for interface in interfaces:
                callables_fspath = module_spec_dir / f"{interface}_callables.py"
                spec_stub = {}

                nipype_module_str = "nipype.interfaces." + ".".join(module.split("/"))
                nipype_module = import_module(nipype_module_str)
                nipype_interface = getattr(nipype_module, interface)
                if not issubclass(
                    nipype_interface, nipype.interfaces.base.core.Interface
                ):
                    not_interfaces.append(f"{module}.{interface}")
                    continue
                # Generate preamble comments for file
                inputs_desc = ""
                file_inputs = []
                genfile_outputs = []
                if nipype_interface.input_spec:
                    for inpt_name, inpt in (
                        nipype_interface.input_spec().traits().items()
                    ):
                        if inpt_name in ("trait_added", "trait_modified"):
                            continue
                        inpt_desc = inpt.desc.replace("\n", " ") if inpt.desc else ""
                        inputs_desc += f"# {inpt_name} : {type(inpt.trait_type).__name__.lower()}\n#    {inpt_desc}\n"
                        if inpt.genfile:
                            genfile_outputs.append(inpt_name)
                        elif type(inpt.trait_type).__name__ in (
                            "File",
                            "InputMultiObject",
                        ):
                            file_inputs.append(inpt_name)
                file_outputs = []
                outputs_desc = ""
                if nipype_interface.output_spec:
                    for outpt_name, outpt in (
                        nipype_interface.output_spec().traits().items()
                    ):
                        if outpt_name in ("trait_added", "trait_modified"):
                            continue
                        outpt_desc = outpt.desc.replace("\n", " ") if outpt.desc else ""
                        outputs_desc += f"# {outpt_name} : {type(outpt.trait_type).__name__.lower()}\n#    {outpt_desc}\n"
                        if type(outpt.trait_type).__name__ == "File":
                            file_outputs.append(outpt_name)
                doc_string = (
                    nipype_interface.__doc__ if nipype_interface.__doc__ else ""
                )
                doc_string = doc_string.replace("\n", "\n# ")
                # Create a preamble at the top of the specificaiton explaining what to do
                preamble = (
                    f"""# This file is used to manually specify the semi-automatic conversion of
                    # '{module.replace('/', '.')}.{interface}' from Nipype to Pydra.
                    #
                    # Please fill-in/edit the fields below where appropriate
                    #
                    # Inputs
                    # ------
                    {inputs_desc}#
                    # Outputs
                    # -------
                    {outputs_desc}#
                    # Docs
                    # ----
                    # {doc_string}\n"""
                ).replace("                    #", "#")

                # Create "stubs" for each of the available fields
                def fields_stub(name, category_class, values=None):
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

                input_types = {i: "generic/file" for i in file_inputs}
                output_types = {o: "generic/file" for o in file_outputs}

                # Attempt to parse doctest to pull out sensible defaults for input/output
                # values
                if nipype_interface.__doc__ and ">>>" in nipype_interface.__doc__:
                    match = re.search(
                        r"""^\s+>>> (?:\w+)\.cmdline(\s*# doctest: .*)?\n\s*(?:'|")?(.*)(?:'|")?\s*$""",
                        nipype_interface.__doc__,
                        flags=re.MULTILINE,
                    )
                    if match:
                        cmdline = match.group(2)
                        cmdline = cmdline.replace("'", '"')
                        directive = match.group(1)
                    else:
                        cmdline = directive = None
                    doctest_inpts = {
                        n: v.replace("'", '"')
                        for n, v in re.findall(
                            r"""\s+>>> (?:\w+)\.inputs\.(\w+) ?= ?(.*)\n""",
                            nipype_interface.__doc__,
                        )
                    }
                    if not doctest_inpts:
                        doctest_inpts = {
                            n: v.replace("'", '"')
                            for n, v in re.findall(
                                r"""\.\.\.\s+(\w+)=(.*) *\n""",
                                nipype_interface.__doc__,
                            )
                        }
                        if doctest_inpts:
                            match = re.search(
                                interface + r"""\((?<!\w)(\w+) *= *([^\=\n]+) *, *""",
                                nipype_interface.__doc__,
                            )
                            if match:
                                doctest_inpts[match.group(1)] = match.group(2).replace(
                                    "'", '"'
                                )
                    if not doctest_inpts:
                        match = re.search(
                            interface
                            + r"""\(((?<!\w)\w+ *= *[^\=\n]+(?:, )?)+\)(\n| #)""",
                            nipype_interface.__doc__,
                        )
                        if match is not None:
                            arg_str = match.group(1) + ", "
                            doctest_inpts = {
                                n: v.replace("'", '"')
                                for n, v in re.findall(r"(\w+) *= *([^=]+), ", arg_str)
                            }
                    if doctest_inpts:

                        def guess_format_from_doctest(field):
                            try:
                                fspath = doctest_inpts[field]
                            except KeyError:
                                return File
                            try:
                                fspath = re.search(
                                    r"""['"]([^'"]*)['"]""", fspath
                                ).group(1)
                            except AttributeError:
                                return File
                            possible_formats = []
                            for frmt in fileformats.core.FileSet.all_formats:
                                if not frmt.ext or None in frmt.alternate_exts:
                                    continue
                                if frmt.matching_exts(fspath):
                                    possible_formats.append(frmt)
                            if not possible_formats:
                                if fspath.endswith(".dcm"):
                                    return Dicom
                                if fspath == "bvals":
                                    return Bval
                                if fspath == "bvecs":
                                    return Bvec
                                unmatched_formats.append(
                                    f"{module}.{interface}: {fspath}"
                                )
                                return File
                            for expected in EXPECTED_FORMATS:
                                if expected in possible_formats:
                                    return expected
                            if len(possible_formats) > 1:
                                non_adjacent = [
                                    f
                                    for f in possible_formats
                                    if not issubclass(
                                        f, fileformats.core.mixin.WithAdjacentFiles
                                    )
                                ]
                                if non_adjacent:
                                    possible_formats = non_adjacent
                            if len(possible_formats) > 1:
                                possible_formats = sorted(
                                    possible_formats, key=lambda f: f.__name__
                                )
                                ambiguous_formats.append(possible_formats)
                            return possible_formats[0]

                        input_types = {
                            n: guess_format_from_doctest(n).mime_like
                            for n in input_types
                        }
                        output_types = {
                            n: guess_format_from_doctest(n).mime_like
                            for n in output_types
                        }

                        test_inpts = {
                            n: v
                            for n, v in doctest_inpts.items()
                            if n not in file_inputs
                        }
                        doctest_inpts = {
                            n: (None if n in file_inputs else v)
                            for n, v in doctest_inpts.items()
                        }
                    else:
                        intf_name = f"{module.replace('/', '.')}.{interface}"
                        warn(
                            f"Could not parse doctest for {intf_name}:\n{nipype_interface.__doc__}"
                        )
                        test_inpts = {}
                        doctest_inpts = {}
                    doctest_stub = fields_stub(
                        "doctest",
                        DocTestGenerator,
                        {
                            "cmdline": cmdline,
                            "inputs": doctest_inpts,
                            "directive": directive,
                        },
                    )
                else:
                    if hasattr(nipype_interface, "_cmd"):
                        doctest_stub = fields_stub(
                            "doctest",
                            DocTestGenerator,
                            {"cmdline": f"{nipype_interface._cmd} <expected-args>"},
                        )
                    else:
                        doctest_stub = None
                    test_inpts = {}

                output_templates = {}
                for outpt in genfile_outputs:
                    try:
                        template = test_inpts[outpt]
                    except KeyError:
                        try:
                            frmt = output_types[outpt]
                        except KeyError:
                            ext = ""
                        else:
                            ext = fileformats.core.utils.from_mime(frmt).ext
                            if not ext:
                                ext = ""
                        template = outpt + ext
                    output_templates[outpt] = template

                spec_stub = {
                    "name": interface,
                    "nipype_module": nipype_module_str,
                    "new_name": None,
                    "inputs": fields_stub(
                        "inputs",
                        InputsConverter,
                        {"types": input_types},
                    ),
                    "outputs": fields_stub(
                        "outputs",
                        OutputsConverter,
                        {
                            "types": output_types,
                            "templates": output_templates,
                        },
                    ),
                    "test": fields_stub(
                        "test", TestsGenerator, {"inputs": copy(test_inpts)}
                    ),
                    "doctest": doctest_stub,
                }
                yaml_str = yaml.dump(spec_stub, indent=4, sort_keys=False, width=4096)
                # Strip explicit nulls from dumped YAML
                yaml_str = yaml_str.replace(" null", "")
                # Inject comments into dumped YAML
                for category_name, category_class in [
                    ("inputs", InputsConverter),
                    ("outputs", OutputsConverter),
                    ("test", TestsGenerator),
                    ("doctest", DocTestGenerator),
                ]:
                    for field in attrs.fields(category_class):
                        tp = field.type
                        if tp.__module__ == "builtins":
                            tp_name = tp.__name__
                        else:
                            tp_name = str(tp).lower().replace("typing.", "")
                        comment = f"    # {tp_name} - " + field.metadata[
                            "help"
                        ].replace("\n                ", "\n    # ")
                        yaml_str = re.sub(
                            f" {category_name}.{field.name}:" + r"(.*)",
                            f" {field.name}:" + r"\1" + f"\n{comment}",
                            yaml_str,
                        )

                with open(module_spec_dir / (interface + ".yaml"), "w") as f:
                    f.write(preamble + yaml_str)
                with open(callables_fspath, "w") as f:
                    f.write(
                        f'"""Module to put any functions that are referred to in {interface}.yaml"""\n'
                    )

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


if __name__ == "__main__":
    import sys

    generate_packages(sys.argv[1:])
