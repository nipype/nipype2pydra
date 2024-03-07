import os
import typing as ty
import re
import inspect
from importlib import import_module
from copy import copy
import shutil
import string
from pathlib import Path
import attrs
from warnings import warn
import requests
from operator import itemgetter
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
    UsedSymbols,
    split_parens_contents,
    cleanup_function_body,
    insert_args_in_signature,
)


TEMPLATES_DIR = Path(__file__).parent.parent / "pkg_gen" / "resources" / "templates"

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


@attrs.define
class NipypeInterface:
    """A class to hold the parsed structure of a Nipype interface"""

    name: str
    doc_str: str
    module: str
    pkg: str
    base_package: str
    preamble: str = attrs.field()
    input_helps: ty.Dict[str, str] = attrs.field()
    output_helps: ty.Dict[str, str] = attrs.field()
    file_inputs: ty.Dict[str, str] = attrs.field()
    path_inputs: ty.List[str] = attrs.field()
    str_inputs: ty.List[str] = attrs.field()
    file_outputs: ty.List[str] = attrs.field()
    template_outputs: ty.List[str] = attrs.field()
    multi_inputs: ty.List[str] = attrs.field()
    dir_inputs: ty.List[str] = attrs.field()
    dir_outputs: ty.List[str] = attrs.field()
    callables: ty.List[str] = attrs.field()

    unmatched_formats: ty.List[str] = attrs.field(factory=list)
    ambiguous_formats: ty.List[str] = attrs.field(factory=list)
    pkg_formats: ty.Set[str] = attrs.field(factory=set)
    has_doctests: bool = False

    @classmethod
    def parse(
        cls, nipype_interface: type, pkg: str, base_package: str
    ) -> "NipypeInterface":
        """Generate preamble comments at start of file with args and doc strings"""
        input_helps = {}
        file_inputs = []
        file_outputs = []
        dir_inputs = []
        path_inputs = []
        str_inputs = []
        template_outputs = []
        multi_inputs = []
        dir_outputs = []
        output_helps = {}
        callables = []
        # Parse output types and descriptions
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
        # Parse input types, descriptions and metadata
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
                # override logic if it is named as an output
                if (
                    inpt_name.startswith("out_")
                    or inpt_name.startswith("output_")
                    or inpt_name.endswith("_out")
                    or inpt_name.endswith("_output")
                ):
                    if "fix" in inpt_name:
                        str_inputs.append(inpt_name)
                    else:
                        path_inputs.append(inpt_name)
                else:
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
        return cls(
            name=nipype_interface.__name__,
            doc_str=nipype_interface.__doc__ if nipype_interface.__doc__ else "",
            module=nipype_interface.__module__[len(base_package) + 1 :],
            pkg=pkg,
            base_package=base_package,
            preamble=preamble,
            input_helps=input_helps,
            output_helps=output_helps,
            file_inputs=file_inputs,
            path_inputs=path_inputs,
            str_inputs=str_inputs,
            file_outputs=file_outputs,
            template_outputs=template_outputs,
            multi_inputs=multi_inputs,
            dir_inputs=dir_inputs,
            dir_outputs=dir_outputs,
            callables=callables,
        )

    def generate_yaml_spec(self) -> str:
        """Convert the NipypeInterface to a YAML string"""

        input_types = {i: File for i in self.file_inputs}
        input_types.update({i: Directory for i in self.dir_inputs})
        input_types.update({i: Path for i in self.path_inputs})
        input_types.update({i: str for i in self.str_inputs})
        output_types = {o: File for o in self.file_outputs}
        output_types.update({o: Directory for o in self.dir_outputs})
        output_templates = {}

        # Attempt to parse doctest to pull out sensible defaults for input/output
        # values
        stripped_doc_str = re.sub(r"\n\s+\.\.\.\s+", "", self.doc_str)
        prev_block = ""
        doctest_blocks = []
        for para in stripped_doc_str.split("\n\n"):
            if "cmdline" in para:
                doctest_blocks.append(prev_block + "\n" + para)
                prev_block = ""
            elif ">>>" in para:
                prev_block += "\n" + para

        # Add default template names for fields not explicitly listed in doctests
        for outpt in self.template_outputs:
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
            n: ty.List[t] if n in self.multi_inputs else t
            for n, t in input_types.items()
        }

        non_mime = [Path, str]

        def type2str(tp):
            if tp in non_mime:
                return tp.__name__
            return fileformats.core.utils.to_mime(tp, official=False)

        tests, doctests = self._gen_tests(
            doctest_blocks, input_types, output_types, output_templates
        )

        # sort dictionaries by key
        input_types = dict(sorted(input_types.items(), key=itemgetter(0)))
        output_types = dict(sorted(output_types.items(), key=itemgetter(0)))
        output_templates = dict(sorted(output_templates.items(), key=itemgetter(0)))

        spec_stub = {
            "task_name": self.name,
            "nipype_name": self.name,
            "nipype_module": self.base_package + "." + self.module,
            "inputs": self._fields_stub(
                "inputs",
                InputsConverter,
                {"types": {n: type2str(t) for n, t in input_types.items()}},
            ),
            "outputs": self._fields_stub(
                "outputs",
                OutputsConverter,
                {
                    "types": {n: type2str(t) for n, t in output_types.items()},
                    "templates": output_templates,
                    "callables": {n: f"{n}_callable" for n in sorted(self.callables)},
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
        for inpt, desc in self.input_helps.items():
            yaml_str = re.sub(
                f"    ({inpt}):(.*)",
                r"    \1:\2\n    # ##PLACEHOLDER##",
                yaml_str,
            )
            yaml_str = yaml_str.replace("##PLACEHOLDER##", desc)
        for outpt, desc in self.output_helps.items():
            yaml_str = re.sub(
                f"    ({outpt}):(.*)",
                r"    \1:\2\n    # ##PLACEHOLDER##",
                yaml_str,
            )
            yaml_str = yaml_str.replace("##PLACEHOLDER##", desc)
        return self.preamble + yaml_str

    def generate_callables(self, nipype_interface) -> str:
        callables_str = (
            f'"""Module to put any functions that are referred to in the "callables"'
            f' section of {self.name}.yaml"""\n\n'
        )
        if self.callables:
            # Convert the "_gen_filename" method into a function with any referenced
            # methods, functions and constants included in the module
            funcs, imports, consts = get_gen_filename_to_funcs(nipype_interface)
            callables_str += "\n".join(imports) + "\n\n"
            # Create separate callable function for each callable field, which
            # reference the magic "_gen_filename" method
            for name in self.callables:
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
        return callables_str

    def _gen_tests(
        self, doctest_blocks, input_types, output_types, output_templates
    ) -> ty.Tuple[ty.List[TestGenerator], ty.List[DocTestGenerator]]:

        doctests: ty.List[DocTestGenerator] = []
        tests: ty.List[TestGenerator] = [
            self._fields_stub(
                "test",
                TestGenerator,
                {"inputs": {i: None for i in self.input_helps}, "imports": None},
            )
        ]

        for doctest_str in doctest_blocks:
            if ">>>" in doctest_str:
                try:
                    cmdline, inpts, directive, imports = extract_doctest_inputs(
                        doctest_str, self.name
                    )
                except ValueError:
                    intf_name = f"{self.module}.{self.name}"
                    warn(f"Could not parse doctest for {intf_name}:\n{doctest_str}")
                    continue

                def guess_type(fspath):
                    try:
                        fspath = re.search(r"""['"]([^'"]*)['"]""", fspath).group(1)
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
                            return File  # Skip any extensions with special chars
                        self.unmatched_formats.append(
                            f"{self.module}.{self.name}: {fspath}"
                        )
                        if format_ext:
                            self.pkg_formats.add(format_ext)
                            return f"fileformats.medimage_{self.pkg}.{ext2format_name(format_ext)}"
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
                        self.ambiguous_formats.append(possible_formats)
                    return possible_formats[0]

                def combine_types(type_, prev_type):
                    as_list = False
                    if ty.get_origin(prev_type) is list:
                        as_list = True
                        prev_type = ty.get_args(prev_type)[0]
                    if ty.get_origin(type_) is list:
                        as_list = True
                        type_ = ty.get_args(type_)[0]
                    if issubclass(type_, prev_type):
                        combined = type_
                    elif issubclass(prev_type, type_):
                        combined = prev_type
                    else:
                        if ty.get_origin(prev_type) is ty.Union:
                            prev_types = ty.get_args(prev_type)
                        else:
                            prev_types = [prev_type]
                        combined = ty.Union.__getitem__((type_,) + tuple(prev_types))
                    if as_list:
                        combined = ty.List.__getitem__(combined)
                    return combined

                test_inpts: ty.Dict[str, ty.Optional[ty.Type]] = {}
                for name, val in inpts.items():
                    if name in self.file_inputs and name != "flags":
                        guessed_type = guess_type(val)
                        input_types[name] = combine_types(
                            guessed_type, input_types[name]
                        )
                        test_inpts[name] = None
                    else:
                        test_inpts[name] = val
                    if name in self.file_outputs:
                        guessed_type = guess_type(val)
                        output_types[name] = combine_types(
                            guessed_type, output_types[name]
                        )
                    if name in self.template_outputs:
                        output_templates[name] = val

                tests.append(
                    self._fields_stub(
                        "test",
                        TestGenerator,
                        {"inputs": test_inpts, "imports": imports},
                    )
                )
                doctests.append(
                    self._fields_stub(
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
                self.has_doctests = True
        return tests, doctests

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
