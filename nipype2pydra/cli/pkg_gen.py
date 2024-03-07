import os
import typing as ty
import tempfile
import re
import inspect
from importlib import import_module
from copy import copy
import subprocess as sp
import shutil
import tarfile
import string
from pathlib import Path
import attrs
from warnings import warn
import requests
import click
import yaml
import black.parsing
import fileformats.core.utils
import fileformats.core.mixin
from fileformats.generic import File, Directory
from fileformats.medimage import Nifti1, NiftiGz, Bval, Bvec
from fileformats.application import Dicom, Xml
from fileformats.text import TextFile
from fileformats.datascience import TextMatrix, DatFile
import nipype.interfaces.base.core
from nipype2pydra.task import (
    InputsConverter,
    OutputsConverter,
    TestGenerator,
    DocTestGenerator,
)
from nipype2pydra.utils import (
    to_snake_case,
    UsedSymbols,
    split_parens_contents,
    cleanup_function_body,
    insert_args_in_signature,
)
from nipype2pydra.cli.base import cli


TEMPLATES_DIR = Path(__file__).parent / "pkg-gen-resources" / "templates"

EXPECTED_FORMATS = [Nifti1, NiftiGz, TextFile, TextMatrix, DatFile, Xml]

EXT_SPECIAL_CHARS = tuple((set(string.punctuation) - set(".-")) | set(" "))


def ext2format_name(ext: str) -> str:
    return escape_leading_digits(ext[1:]).capitalize()


def escape_leading_digits(name: str) -> str:
    for k, v in ESCAPE_DIGITS.items():
        if name.startswith(k):
            name = v + name[1:]
            return name
    return name


ESCAPE_DIGITS = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}


def download_tasks_template(output_path: Path):
    """Downloads the latest pydra-template to the output path"""

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


@cli.command("pkg-gen", help="Generates stub pydra packages for all nipype interfaces to import")
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--work-dir", type=click.Path(path_type=Path), default=None)
@click.option("--task-template", type=click.Path(path_type=Path), default=None)
@click.option("--packages-to-import", type=click.Path(path_type=Path), default=None)
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
            }
        }
        if packages_to_import:
            raise ValueError(
                "Cannot specify both --single-package and --packages-to-import"
            )
    else:
        if packages_to_import is None:
            packages_to_import = (
                Path(__file__).parent.parent.parent / "nipype-interfaces-to-import.yaml"
            )

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
                spec_name = to_snake_case(interface)
                callables_fspath = spec_dir / f"{spec_name}_callables.py"
                spec_stub = {}

                # Import interface from module
                nipype_module_str = base_package + "." + ".".join(module.split("/"))
                nipype_module = import_module(nipype_module_str)
                nipype_interface = getattr(nipype_module, interface)
                if not issubclass(
                    nipype_interface, nipype.interfaces.base.core.Interface
                ):
                    not_interfaces.append(f"{module}.{interface}")
                    continue

                (
                    preamble,
                    input_helps,
                    output_helps,
                    file_inputs,
                    path_inputs,
                    file_outputs,
                    template_outputs,
                    multi_inputs,
                    dir_inputs,
                    dir_outputs,
                    callables,
                ) = parse_nipype_interface(nipype_interface)

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
                input_types.update({i: Directory for i in dir_inputs})
                input_types.update({i: Path for i in path_inputs})
                output_types = {o: File for o in file_outputs}
                output_types.update({o: Directory for o in dir_outputs})
                output_templates = {}

                # Attempt to parse doctest to pull out sensible defaults for input/output
                # values
                doc_str = nipype_interface.__doc__ if nipype_interface.__doc__ else ""
                doc_str = re.sub(r"\n\s+\.\.\.\s+", "", doc_str)
                prev_block = ""
                doctest_blocks = []
                for para in doc_str.split("\n\n"):
                    if "cmdline" in para:
                        doctest_blocks.append(prev_block + "\n" + para)
                        prev_block = ""
                    elif ">>>" in para:
                        prev_block += "\n" + para

                doctests: ty.List[DocTestGenerator] = []
                tests: ty.List[TestGenerator] = [
                    fields_stub(
                        "test",
                        TestGenerator,
                        {"inputs": {i: None for i in input_helps}, "imports": None},
                    )
                ]

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
                                format_ext = File.decompose_fspath(
                                    fspath.strip(),
                                    mode=File.ExtensionDecomposition.single,
                                )[2]
                                if any(c in format_ext for c in EXT_SPECIAL_CHARS):
                                    return (
                                        File  # Skip any extensions with special chars
                                    )
                                unmatched_formats.append(
                                    f"{module}.{interface}: {fspath}"
                                )
                                if format_ext:
                                    pkg_formats.add(format_ext)
                                    return f"fileformats.medimage_{pkg}.{ext2format_name(format_ext)}"
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

                        test_inpts: ty.Dict[str, ty.Optional[ty.Type]] = {}
                        for name, val in inpts.items():
                            if name in file_inputs and name != "flags":
                                guessed_type = guess_type(val)
                                input_types[name] = combine_types(
                                    guessed_type, input_types[name]
                                )
                                test_inpts[name] = None
                            else:
                                test_inpts[name] = val
                            if name in file_outputs:
                                guessed_type = guess_type(val)
                                output_types[name] = combine_types(
                                    guessed_type, output_types[name]
                                )
                            if name in template_outputs:
                                output_templates[name] = val

                        tests.append(
                            fields_stub(
                                "test",
                                TestGenerator,
                                {"inputs": test_inpts, "imports": imports},
                            )
                        )
                        doctests.append(
                            fields_stub(
                                "doctest",
                                DocTestGenerator,
                                {
                                    "cmdline": cmdline,
                                    "inputs": copy(test_inpts),
                                    "imports": imports,
                                    "directive": directive,
                                },
                            )
                        )
                        has_doctests.add(f"{module.replace('/', '.')}.{interface}")

                # Add default template names for fields not explicitly listed in doctests
                for outpt in template_outputs:
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

                non_mime = [Path]

                def type2str(tp):
                    if tp in non_mime:
                        return tp.__name__
                    return fileformats.core.utils.to_mime(tp, official=False)

                spec_stub = {
                    "task_name": interface,
                    "nipype_name": interface,
                    "nipype_module": nipype_module_str,
                    "inputs": fields_stub(
                        "inputs",
                        InputsConverter,
                        {"types": {n: type2str(t) for n, t in input_types.items()}},
                    ),
                    "outputs": fields_stub(
                        "outputs",
                        OutputsConverter,
                        {
                            "types": {n: type2str(t) for n, t in output_types.items()},
                            "templates": output_templates,
                            "callables": {n: f"{n}_callable" for n in callables},
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
                        comment = f"  # {tp_name} - " + field.metadata["help"].replace(
                            "\n                ", "\n  # "
                        )
                        yaml_str = re.sub(
                            f" {category_name}.{field.name}:" + r"(.*)",
                            f" {field.name}:" + r"\1" + f"\n{comment}",
                            yaml_str,
                        )
                # Add comments to input and output fields, with their type and description
                for inpt, desc in input_helps.items():
                    yaml_str = re.sub(
                        f"    ({inpt}):(.*)",
                        r"    \1:\2\n    # ##PLACEHOLDER##",
                        yaml_str,
                    )
                    yaml_str = yaml_str.replace("##PLACEHOLDER##", desc)
                for outpt, desc in output_helps.items():
                    yaml_str = re.sub(
                        f"    ({outpt}):(.*)",
                        r"    \1:\2\n    # ##PLACEHOLDER##",
                        yaml_str,
                    )
                    yaml_str = yaml_str.replace("##PLACEHOLDER##", desc)

                with open(spec_dir / (spec_name + ".yaml"), "w") as f:
                    f.write(preamble + yaml_str)
                callables_str = (
                    f'"""Module to put any functions that are referred to in the "callables"'
                    f' section of {interface}.yaml"""\n\n'
                )
                if callables:
                    # Convert the "_gen_filename" method into a function with any referenced
                    # methods, functions and constants included in the module
                    funcs, imports, consts = get_gen_filename_to_funcs(nipype_interface)
                    callables_str += "\n".join(imports) + "\n\n"
                    # Create separate callable function for each callable field, which
                    # reference the magic "_gen_filename" method
                    for name in callables:
                        callables_str += (
                            f"def {name}_callable(output_dir, inputs, stdout, stderr):\n"
                            f'    return _gen_filename("{name}", output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr)\n\n'
                        )
                    for const in consts:
                        callables_str += f"{const[0]} = {const[1]}\n" + "\n\n"
                    callables_str += "\n\n".join(funcs) + "\n\n"
                # Format the generated code with black
                try:
                    callables_str = black.format_file_contents(
                        callables_str, fast=False, mode=black.FileMode()
                    )
                except black.parsing.InvalidInput as e:
                    raise RuntimeError(
                        f"Black could not parse generated code: {e}\n\n{callables_str}"
                    )
                with open(callables_fspath, "w") as f:
                    f.write(callables_str)

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

    if example_packages:
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
            shutil.copytree(specs_dir, examples_dir / example_pkg_name)

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
    shutil.copy(TEMPLATES_DIR / "nipype-auto-convert.py", auto_conv_dir / "generate")
    os.chmod(auto_conv_dir / "generate", 0o755)  # make executable
    shutil.copy(
        TEMPLATES_DIR / "nipype-auto-convert-requirements.txt",
        auto_conv_dir / "requirements.txt",
    )

    # Setup GitHub workflows
    gh_workflows_dir = pkg_dir / ".github" / "workflows"
    gh_workflows_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        TEMPLATES_DIR / "gh_workflows" / "ci-cd.yaml",
        gh_workflows_dir / "ci-cd.yaml",
    )

    # Add modified README
    os.unlink(pkg_dir / "README.md")
    shutil.copy(TEMPLATES_DIR / "README.rst", pkg_dir / "README.rst")
    with open(pkg_dir / "pyproject.toml") as f:
        pyproject_toml = f.read()
    pyproject_toml = pyproject_toml.replace("README.md", "README.rst")
    pyproject_toml = pyproject_toml.replace(
        "test = [\n", 'test = [\n    "nipype2pydra",\n'
    )
    with open(pkg_dir / "pyproject.toml", "w") as f:
        f.write(pyproject_toml)

    # Add "pydra.tasks.<pkg>.auto to gitignore"
    with open(pkg_dir / ".gitignore", "a") as f:
        f.write(f"\n/pydra/tasks/{pkg}/auto" f"\n/pydra/tasks/{pkg}/_version.py\n")

    # rename tasks directory
    (pkg_dir / "pydra" / "tasks" / "CHANGEME").rename(pkg_dir / "pydra" / "tasks" / pkg)
    (
        pkg_dir
        / "related-packages"
        / "fileformats"
        / "fileformats"
        / "medimage_CHANGEME"
    ).rename(
        pkg_dir / "related-packages" / "fileformats" / "fileformats" / f"medimage_{pkg}"
    )
    (
        pkg_dir
        / "related-packages"
        / "fileformats-extras"
        / "fileformats"
        / "extras"
        / "medimage_CHANGEME"
    ).rename(
        pkg_dir
        / "related-packages"
        / "fileformats-extras"
        / "fileformats"
        / "extras"
        / f"medimage_{pkg}"
    )

    # Add in modified __init__.py
    shutil.copy(
        TEMPLATES_DIR / "pkg_init.py", pkg_dir / "pydra" / "tasks" / pkg / "__init__.py"
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

    return pkg_dir


def parse_nipype_interface(
    nipype_interface,
) -> ty.Tuple[
    str,
    ty.Dict[str, str],
    ty.Dict[str, str],
    ty.List[str],
    ty.List[str],
    ty.List[str],
    ty.List[str],
    ty.List[str],
    ty.List[str],
]:
    """Generate preamble comments at start of file with args and doc strings"""
    input_helps = {}
    file_inputs = []
    file_outputs = []
    dir_inputs = []
    path_inputs = []
    template_outputs = []
    multi_inputs = []
    dir_outputs = []
    output_helps = {}
    callables = []
    if nipype_interface.output_spec:
        for outpt_name, outpt in nipype_interface.output_spec().traits().items():
            if outpt_name in ("trait_added", "trait_modified"):
                continue
            outpt_desc = outpt.desc.replace("\n", " ") if outpt.desc else ""
            output_helps[outpt_name] = (
                f"type={type(outpt.trait_type).__name__.lower()}: {outpt_desc}"
            )
            if type(outpt.trait_type).__name__ == "File":
                file_outputs.append(outpt_name)
            elif type(outpt.trait_type).__name__ == "Directory":
                dir_outputs.append(outpt_name)
    if nipype_interface.input_spec:
        for inpt_name, inpt in nipype_interface.input_spec().traits().items():
            if inpt_name in ("trait_added", "trait_modified"):
                continue
            inpt_desc = inpt.desc.replace("\n", " ") if inpt.desc else ""
            inpt_mdata = f"type={type(inpt.trait_type).__name__.lower()}|default={inpt.default!r}"
            if isinstance(inpt.trait_type, nipype.interfaces.base.core.traits.Enum):
                inpt_mdata += f"|allowed[{','.join(sorted(repr(v) for v in inpt.trait_type.values))}]"
            input_helps[inpt_name] = f"{inpt_mdata}: {inpt_desc}"
            trait_type_name = type(inpt.trait_type).__name__
            if inpt.genfile:
                if trait_type_name in ("File", "Directory"):
                    path_inputs.append(inpt_name)
                if inpt_name in (file_outputs + dir_outputs):
                    template_outputs.append(inpt_name)
                else:
                    callables.append(inpt_name)
            elif trait_type_name == "File" and inpt_name not in file_outputs:
                file_inputs.append(inpt_name)
            elif trait_type_name == "Directory" and inpt_name not in dir_outputs:
                dir_inputs.append(inpt_name)
            elif trait_type_name == "InputMultiObject":
                inner_trait_type_name = type(
                    inpt.trait_type.item_trait.trait_type
                ).__name__
                if inner_trait_type_name == "Directory":
                    dir_inputs.append(inpt_name)
                elif inner_trait_type_name == "File":
                    file_inputs.append(inpt_name)
                multi_inputs.append(inpt_name)
            elif type(inpt.trait_type).__name__ == "List" and type(
                inpt.trait_type.inner_traits()[0].handler
            ).__name__ in ("File", "Directory"):
                item_type_name = type(
                    inpt.trait_type.inner_traits()[0].handler
                ).__name__
                if item_type_name == "File":
                    file_inputs.append(inpt_name)
                else:
                    dir_inputs.append(inpt_name)
                multi_inputs.append(inpt_name)
            elif trait_type_name in ("File", "Directory"):
                path_inputs.append(inpt_name)
    doc_string = nipype_interface.__doc__ if nipype_interface.__doc__ else ""
    doc_string = doc_string.replace("\n", "\n# ")
    # Create a preamble at the top of the specificaiton explaining what to do
    preamble = (
        f"""# This file is used to manually specify the semi-automatic conversion of
        # '{nipype_interface.__module__.replace('/', '.')}.{nipype_interface.__name__}' from Nipype to Pydra.
        #
        # Please fill-in/edit the fields below where appropriate
        #
        # Docs
        # ----
        # {doc_string}\n"""
    ).replace("        #", "#")
    return (
        preamble,
        input_helps,
        output_helps,
        file_inputs,
        path_inputs,
        file_outputs,
        template_outputs,
        multi_inputs,
        dir_inputs,
        dir_outputs,
        callables,
    )


def extract_doctest_inputs(
    doctest: str, interface: str
) -> ty.Tuple[
    ty.Optional[str], ty.Dict[str, ty.Any], ty.Optional[str], ty.List[ty.Dict[str, str]]
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
        cmdline = cmdline.replace("'", '"') if '"' not in cmdline else cmdline
        directive = match.group(2)
        if directive == '"' or directive == "'":
            directive = None
    else:
        cmdline = directive = None
    doctest_inpts = {
        n: v.replace("'", '"') if '"' not in v else v
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
                n: v.replace("'", '"') if '"' not in v else v
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

    if not directive or directive == "''" or directive == '""':
        directive = None

    return cmdline, doctest_inpts, directive, imports


def gen_fileformats_module(pkg_formats: ty.Set[str]):
    code_str = "from fileformats.generic import File"
    for ext in pkg_formats:
        frmt = ext2format_name(ext)
        code_str += f"""

class {frmt}(File):
    ext = "{ext}"
    binary = True
"""
    return code_str


def gen_fileformats_extras_module(pkg: str, pkg_formats: ty.Set[str]):
    code_str = """from pathlib import Path
import typing as ty
from random import Random
from fileformats.core import FileSet
"""
    code_str += f"from fileformats.medimage_{pkg} import (\n"
    for ext in pkg_formats:
        frmt = ext2format_name(ext)
        code_str += f"    {frmt},\n"
    code_str += ")\n\n"
    for ext in pkg_formats:
        frmt = ext2format_name(ext)
        code_str += f"""

@FileSet.generate_sample_data.register
def gen_sample_{frmt.lower()}_data({frmt.lower()}: {frmt}, dest_dir: Path, seed: ty.Union[int, Random] = 0, stem: ty.Optional[str] = None) -> ty.Iterable[Path]:
    raise NotImplementedError
"""
    return code_str


def get_gen_filename_to_funcs(
    nipype_interface,
) -> ty.Tuple[ty.List[str], ty.Set[str], ty.Set[ty.Tuple[str, str]]]:
    """
    Convert the _gen_filename method of a nipype interface into a function that can be
    imported and used by the auto-convert scripts

    Parameters
    ----------
    nipype_interface : type
        the nipype interface to convert

    Returns
    -------
    list[str]
        the source code of functions to be added to the callables
    set[str]
        the imports required for the function
    set[tuple[str, str]]
        the external constants required by the function, as (name, value) tuples
    """

    if not hasattr(nipype_interface, "_gen_filename"):
        func_src = f"""
def _gen_filename(field, inputs, output_dir, stdout, stderr):
    raise NotImplementedError(
        "Could not find '_gen_filename' method in {nipype_interface.__module__}.{nipype_interface.__name__}"
    )
"""
        warn(f"Could not find '_gen_filename' method in {nipype_interface}")
        return [func_src], set(), set()

    IMPLICIT_ARGS = ["inputs", "stdout", "stderr", "output_dir"]

    def find_nested_methods(method: ty.Callable) -> ty.List[str]:
        all_nested = set()
        for match in re.findall(r"self\.(\w+)\(", inspect.getsource(method)):
            nested = getattr(nipype_interface, match)
            all_nested.add(nested)
            all_nested.update(find_nested_methods(nested))
        return all_nested

    def process_method(method: ty.Callable) -> str:
        src = inspect.getsource(method)
        prefix, args_str, body = split_parens_contents(src)
        body = insert_args_in_method_calls(body, [f"{a}={a}" for a in IMPLICIT_ARGS])
        body = body.replace("self.cmd", f'"{nipype_interface._cmd}"')
        body = body.replace("self.", "")
        body = re.sub(r"\w+runtime\.(stdout|stderr)", r"\1", body)
        body = body.replace("os.getcwd()", "output_dir")
        # drop 'self' from the args and add the implicit callable args
        args = args_str.split(",")[1:]
        arg_names = [a.split("=")[0].split(":")[0] for a in args]
        for implicit in IMPLICIT_ARGS:
            if implicit not in arg_names:
                args.append(f"{implicit}=None")
        src = prefix + ", ".join(args) + body
        src = cleanup_function_body(src, with_signature=True)
        return src

    def insert_args_in_method_calls(src: str, args: ty.List[ty.Tuple[str, str]]) -> str:
        """Insert additional arguments into the method calls

        Parameters
        ----------
        body : str
            the body of th
        args : list[tuple[str, str]]
            the arguments to insert into the method calls
        """
        # Split the src code into chunks delimited by calls to methods (i.e. 'self.<method>(.*)')
        method_re = re.compile(r"self\.(\w+)(?=\()", flags=re.MULTILINE | re.DOTALL)
        splits = method_re.split(src)
        new_src = splits[0]
        # Iterate through these chunks and add the additional args to the method calls
        # using insert_args_in_signature function
        for name, sig in zip(splits[1::2], splits[2::2]):
            new_src += name + insert_args_in_signature(sig, args)
        return new_src

    func_srcs = [
        process_method(m)
        for m in (
            [nipype_interface._gen_filename]
            + list(find_nested_methods(nipype_interface._gen_filename))
        )
    ]

    mod = import_module(nipype_interface.__module__)
    used = UsedSymbols.find(mod, func_srcs)
    for func in used.local_functions:
        func_srcs.append(
            cleanup_function_body(inspect.getsource(func), with_signature=True)
        )
    for new_func_name, func in used.funcs_to_include:
        func_src = inspect.getsource(func)
        match = re.match(
            r" *(def|class) *" + func.__name__ + r"(?=\()(.*)$",
            func_src,
            re.DOTALL | re.MULTILINE,
        )
        func_src = match.group(1) + " " + new_func_name + match.group(2)
        func_srcs.append(cleanup_function_body(func_src, with_signature=True))
    return (
        func_srcs,
        used.imports,
        used.constants,
    )


if __name__ == "__main__":
    import sys

    pkg_gen(sys.argv[1:])
