import os
import typing as ty
import tempfile
import re
from importlib import import_module
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
from fileformats.text import TextFile
from fileformats.datascience import MatFile, DatFile
from fileformats.serialization import Xml
import nipype.interfaces.base.core
from nipype2pydra.task import (
    InputsConverter,
    OutputsConverter,
    TestGenerator,
    DocTestGenerator,
)


RESOURCES_DIR = Path(__file__).parent / "resources"

EXPECTED_FORMATS = [Nifti1, NiftiGz, TextFile, MatFile, DatFile, Xml]


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
    has_doctests = set()

    for pkg in to_import["packages"]:
        pkg_dir = initialise_task_repo(output_dir, task_template, pkg)

        # Loop through all nipype modules and create specs for their auto-conversion
        for module, interfaces in to_import["interfaces"].items():
            if module.split("/")[0] != pkg:
                continue

            module_spec_dir = (pkg_dir / "nipype-auto-conv" / "specs").joinpath(
                *module.split("/")[1:]
            )
            module_spec_dir.mkdir(parents=True, exist_ok=True)

            # Loop through all interfaces in module
            for interface in interfaces:
                callables_fspath = module_spec_dir / f"{interface}_callables.py"
                spec_stub = {}

                # Import interface from module
                nipype_module_str = "nipype.interfaces." + ".".join(module.split("/"))
                nipype_module = import_module(nipype_module_str)
                nipype_interface = getattr(nipype_module, interface)
                if not issubclass(
                    nipype_interface, nipype.interfaces.base.core.Interface
                ):
                    not_interfaces.append(f"{module}.{interface}")
                    continue

                (
                    preamble,
                    file_inputs,
                    file_outputs,
                    genfile_outputs,
                    multi_inputs,
                ) = generate_spec_preamble(nipype_interface)

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

                input_types = {i: File for i in file_inputs}
                output_types = {o: File for o in file_outputs}
                output_templates = {}

                # Attempt to parse doctest to pull out sensible defaults for input/output
                # values
                doc_str = nipype_interface.__doc__ if nipype_interface.__doc__ else ""
                doc_str = re.sub(r"\n\s+\.\.\.\s+", "", doc_str)
                prev_block = ""
                doctest_blocks = []
                for para in doc_str.split("\n\n"):
                    if "cmdline" in para:
                        doctest_blocks.append(prev_block + para)
                        prev_block = ""
                    else:
                        prev_block += para

                doctests: ty.List[DocTestGenerator] = []
                tests: ty.List[TestGenerator] = []

                for doctest_str in doctest_blocks:
                    if ">>>" in doctest_str:
                        try:
                            cmdline, inpts, directive, imports = extract_doctest_inputs(
                                doctest_str, interface
                            )
                        except ValueError:
                            intf_name = f"{module.replace('/', '.')}.{interface}"
                            warn(
                                f"Could not parse doctest for {intf_name}:\n{doctest_str}"
                            )
                            continue

                        def guess_type(fspath):
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

                        def combine_types(type_, prev_type):
                            if type_ is File:
                                return prev_type
                            if prev_type is not File:
                                if ty.get_origin(prev_type) is ty.Union:
                                    prev_types = ty.get_args(prev_type)
                                else:
                                    prev_types = [prev_type]
                                return ty.Union.__getitem__(
                                    (type_,) + tuple(prev_types)
                                )
                            return type_

                        test_inpts = {}
                        doctest_inpts = {}
                        for name, val in inpts.items():
                            if name in file_inputs:
                                guessed_type = guess_type(val)
                                input_types[name] = combine_types(
                                    guessed_type, input_types[name]
                                )
                            else:
                                test_inpts[name] = val
                            if name in file_outputs:
                                guessed_type = guess_type(val)
                                output_types[name] = combine_types(
                                    guessed_type, output_types[name]
                                )
                            if name in genfile_outputs:
                                output_templates[name] = val
                            doctest_inpts[name] = None if name in file_inputs else val

                        tests.append(
                            fields_stub(
                                "test",
                                TestGenerator,
                                {"inputs": copy(test_inpts), "imports": imports},
                            )
                        )
                        doctests.append(
                            fields_stub(
                                "doctest",
                                DocTestGenerator,
                                {
                                    "cmdline": cmdline,
                                    "inputs": doctest_inpts,
                                    "imports": imports,
                                    "directive": directive,
                                },
                            )
                        )
                        has_doctests.add(f"{module.replace('/', '.')}.{interface}")

                # Add default template names for fields not explicitly listed in doctests
                for outpt in genfile_outputs:
                    if outpt not in output_templates:
                        try:
                            frmt = output_types[outpt]
                        except KeyError:
                            ext = ""
                        else:
                            if getattr(frmt, "_name", None) == "Union":
                                ext = ty.get_args(frmt)[0].strext
                            else:
                                ext = frmt.strext
                        output_templates[outpt] = outpt + ext

                # convert to multi-input types to lists
                input_types = {
                    n: ty.List[t] if n in multi_inputs else t
                    for n, t in input_types.items()
                }

                spec_stub = {
                    "name": interface,
                    "nipype_module": nipype_module_str,
                    "new_name": None,
                    "inputs": fields_stub(
                        "inputs",
                        InputsConverter,
                        {
                            "types": {
                                n: fileformats.core.utils.to_mime(t)
                                for n, t in input_types.items()
                            }
                        },
                    ),
                    "outputs": fields_stub(
                        "outputs",
                        OutputsConverter,
                        {
                            "types": {
                                n: fileformats.core.utils.to_mime(t)
                                for n, t in output_types.items()
                            },
                            "templates": output_templates,
                        },
                    ),
                    "tests": tests,
                    "doctests": doctests,
                }
                yaml_str = yaml.dump(spec_stub, indent=2, sort_keys=False, width=4096)
                # Strip explicit nulls from dumped YAML
                yaml_str = yaml_str.replace(" null", "")
                # Inject comments into dumped YAML
                for category_name, category_class in [
                    ("inputs", InputsConverter),
                    ("outputs", OutputsConverter),
                    ("test", TestGenerator),
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

        # sp.check_call("git init", shell=True, cwd=pkg_dir)
        # sp.check_call("git add --all", shell=True, cwd=pkg_dir)
        # sp.check_call(
        #     'git commit -m"initial commit of generated stubs"', shell=True, cwd=pkg_dir
        # )
        # sp.check_call("git tag 0.1.0", shell=True, cwd=pkg_dir)

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


def initialise_task_repo(output_dir, task_template: Path, pkg: str) -> Path:
    """Copy the task template to the output directory and customise it for the given
    package name and return the created package directory"""

    pkg_dir = output_dir / f"pydra-{pkg}"

    def copy_ignore(_, names):
        return [n for n in names if n in (".git", "__pycache__", ".pytest_cache")]

    shutil.copytree(task_template, pkg_dir, ignore=copy_ignore)

    # Setup script to auto-convert nipype interfaces
    auto_conv_dir = pkg_dir / "nipype-auto-conv"
    specs_dir = auto_conv_dir / "specs"
    specs_dir.mkdir(parents=True)
    shutil.copy(RESOURCES_DIR / "nipype-auto-convert.py", auto_conv_dir / "generate")
    os.chmod(auto_conv_dir / "generate", 0o755)  # make executable
    shutil.copy(
        RESOURCES_DIR / "nipype-auto-convert-requirements.txt",
        auto_conv_dir / "requirements.txt",
    )

    # Setup GitHub workflows
    gh_workflows_dir = pkg_dir / ".github" / "workflows"
    gh_workflows_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        RESOURCES_DIR / "gh_workflows" / "pythonpackage.yaml",
        gh_workflows_dir / "pythonpackage.yaml",
    )
    shutil.copy(
        RESOURCES_DIR / "gh_workflows" / "auto-release.yaml",
        gh_workflows_dir / "auto-release.yaml",
    )

    # Add in conftest.py
    shutil.copy(RESOURCES_DIR / "conftest.py", pkg_dir / "conftest.py")

    # Add "pydra.tasks.<pkg>.auto to gitignore"
    with open(pkg_dir / ".gitignore", "a") as f:
        f.write(f"\npydra/tasks/{pkg}/auto")

    # rename tasks directory
    (pkg_dir / "pydra" / "tasks" / "CHANGEME").rename(pkg_dir / "pydra" / "tasks" / pkg)

    # Add in modified __init__.py
    shutil.copy(RESOURCES_DIR / "pkg_init.py", pkg_dir / "pydra" / "tasks" / pkg / "__init__.py")

    # Replace "CHANGEME" string with pkg name
    for fspath in pkg_dir.glob("**/*"):
        if fspath.is_dir():
            continue
        with open(fspath) as f:
            contents = f.read()
        contents = re.sub(r"(?<![0-9a-zA-Z])CHANGEME(?![0-9a-zA-Z])", pkg, contents)
        with open(fspath, "w") as f:
            f.write(contents)

    return pkg_dir


def generate_spec_preamble(
    nipype_interface,
) -> ty.Tuple[str, ty.List[str], ty.List[str], ty.List[str], ty.List[str]]:
    """Generate preamble comments at start of file with args and doc strings"""
    inputs_desc = ""
    file_inputs = []
    genfile_outputs = []
    multi_inputs = []
    if nipype_interface.input_spec:
        for inpt_name, inpt in nipype_interface.input_spec().traits().items():
            if inpt_name in ("trait_added", "trait_modified"):
                continue
            inpt_desc = inpt.desc.replace("\n", " ") if inpt.desc else ""
            inputs_desc += f"# {inpt_name} : {type(inpt.trait_type).__name__.lower()}\n#    {inpt_desc}\n"
            if inpt.genfile:
                genfile_outputs.append(inpt_name)
            elif type(inpt.trait_type).__name__ == "File":
                file_inputs.append(inpt_name)
            elif type(inpt.trait_type).__name__ == "InputMultiObject":
                file_inputs.append(inpt_name)
                multi_inputs.append(inpt_name)
    file_outputs = []
    outputs_desc = ""
    if nipype_interface.output_spec:
        for outpt_name, outpt in nipype_interface.output_spec().traits().items():
            if outpt_name in ("trait_added", "trait_modified"):
                continue
            outpt_desc = outpt.desc.replace("\n", " ") if outpt.desc else ""
            outputs_desc += f"# {outpt_name} : {type(outpt.trait_type).__name__.lower()}\n#    {outpt_desc}\n"
            if type(outpt.trait_type).__name__ == "File":
                file_outputs.append(outpt_name)
    doc_string = nipype_interface.__doc__ if nipype_interface.__doc__ else ""
    doc_string = doc_string.replace("\n", "\n# ")
    # Create a preamble at the top of the specificaiton explaining what to do
    preamble = (
        f"""# This file is used to manually specify the semi-automatic conversion of
        # '{nipype_interface.__module__.replace('/', '.')}.{nipype_interface.__name__}' from Nipype to Pydra.
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
    ).replace("        #", "#")
    return preamble, file_inputs, file_outputs, genfile_outputs, multi_inputs


def extract_doctest_inputs(
    doctest: str, interface: str
) -> ty.Tuple[
    ty.Optional[str], dict[str, ty.Any], ty.Optional[str], ty.List[ty.Dict[str, str]]
]:
    """Extract the inputs passed to tasks in the doctests of Nipype interfaces

    Parameters
    ----------
    doctest : str
        the doc string of the interface
    interface : str
        the name of the interface

    Returns
    -------
    cmdline : str
        the expected cmdline
    inputs : dict[str, ty.Any]
        the inputs passed to the task
    directive : str
        any doctest directives found after the cmdline, e.g. ELLIPSIS"""
    match = re.search(
        r"""^\s+>>> (?:.*)\.cmdline(\s*# doctest: .*)?\n\s*('|")(.*)(?:'|")?\s*.*(?!>>>)\2""",
        doctest,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match:
        cmdline = match.group(3)
        cmdline = re.sub(r"\s+", " ", cmdline)
        cmdline = cmdline.replace("'", '"')
        directive = match.group(2)
        if directive == '"':
            directive = None
    else:
        cmdline = directive = None
    doctest_inpts = {
        n: v.replace("'", '"')
        for n, v in re.findall(
            r"""\s+>>> (?:\w+)\.inputs\.(\w+) ?= ?(.*)\n""",
            doctest,
        )
    }
    match = re.search(
        interface + r"""\(([^\)]+)\)(\n|  ?#|\.cmdline)""",
        doctest,
    )
    if match is not None:
        arg_str = match.group(1) + ", "
        doctest_inpts.update(
            {
                n: v.replace("'", '"')
                for n, v in re.findall(r"(\w+) *= *([^=]+), *", arg_str)
            }
        )
    imports = []
    for ln in doctest.splitlines():
        if re.match(r".*>>>.*(?<!\w)import(?!\w)", ln):
            match = re.match(r".*>>> import (.*)$", ln)
            if match:
                for mod in match.group(1).split(","):
                    imports.append({"module": mod.strip()})
            else:
                match = re.match(r".*>>> from ([\w\.]+) import (.*)", ln)
                if not match:
                    raise ValueError(f"Could not parse import statement: {ln}")
                module = match.group(1)
                if "nipype.interfaces" in module:
                    continue
                for atr in match.group(2).split(","):
                    match = re.match(r"(\w+) as ((\w+))", atr)
                    if match:
                        name = match.group(1)
                        alias = match.group(2)
                    else:
                        name = atr
                        alias = None
                    imports.append(
                        {
                            "module": module,
                            "name": name,
                            "alias": alias,
                        }
                    )
    if not doctest_inpts:
        raise ValueError(f"Could not parse doctest:\n{doctest}")

    return cmdline, doctest_inpts, directive, imports


if __name__ == "__main__":
    import sys

    generate_packages(sys.argv[1:])
