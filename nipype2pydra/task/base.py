import os
from pathlib import Path
import typing as ty
import re
import logging
from abc import ABCMeta, abstractmethod
from importlib import import_module
from types import ModuleType
import itertools
import inspect
import black
import traits.trait_types
import json
import attrs
from attrs.converters import default_if_none
import nipype.interfaces.base
from nipype.interfaces.base import traits_extension
from pydra.engine import specs
from pydra.engine.helpers import ensure_list
from ..utils import import_module_from_path, is_fileset, to_snake_case
from fileformats.core import from_mime
from fileformats.core.mixin import WithClassifiers
from fileformats.generic import File


T = ty.TypeVar("T")

logger = logging.getLogger("nipype2pydra")


def from_dict_converter(
    obj: ty.Union[T, dict], klass: ty.Type[T], allow_none=False
) -> T:
    if obj is None:
        if allow_none:
            converted = None
        else:
            converted = klass()
    elif isinstance(obj, dict):
        converted = klass(**obj)
    elif isinstance(obj, klass):
        converted = obj
    else:
        raise TypeError(
            f"Input must be of type {klass} or dict, not {type(obj)}: {obj}"
        )
    return converted


def str_to_type(type_str: str) -> type:
    """Resolve a string representation of a type into a valid type"""
    if "/" in type_str:
        tp = from_mime(type_str)
        try:
            # If datatype is a field, use its primitive instead
            tp = tp.primitive  # type: ignore
        except AttributeError:
            pass
    else:

        def resolve_type(type_str: str) -> type:
            if "." in type_str:
                parts = type_str.split(".")
                module = import_module(".".join(parts[:-1]))
                class_str = parts[-1]
            else:
                class_str = type_str
                module = None
            match = re.match(r"(\w+)(\[.*\])?", class_str)
            class_str = match.group(1)
            if module:
                t = getattr(module, match.group(1))
            else:
                if not re.match(r"^\w+$", class_str):
                    raise ValueError(f"Cannot parse {class_str} to a type safely")
                t = eval(class_str)
            if match.group(2):
                args = tuple(
                    resolve_type(arg) for arg in match.group(2)[1:-1].split(",")
                )
                t = t.__getitem__(args)
            return t

        tp = resolve_type(type_str)
        if not inspect.isclass(tp) and type(tp).__module__ != "typing":
            raise TypeError(f"Designated type at {type_str} is not a class {tp}")
    return tp


def types_converter(types: ty.Dict[str, ty.Union[str, type]]) -> ty.Dict[str, type]:
    if types is None:
        return {}
    converted = {}
    for name, tp_or_str in types.items():
        if isinstance(tp_or_str, str):
            tp = str_to_type(tp_or_str)
        converted[name] = tp
    return converted


@attrs.define
class ImportStatement:
    module: str
    name: ty.Optional[str] = None
    alias: ty.Optional[str] = None


def from_list_to_imports(
    obj: ty.Union[ty.List[ImportStatement], list]
) -> ty.List[ImportStatement]:
    if obj is None:
        return []
    return [from_dict_converter(t, ImportStatement) for t in obj]


@attrs.define
class SpecConverter:
    omit: ty.List[str] = attrs.field(
        factory=list,
        converter=default_if_none(factory=list),  # type: ignore
        metadata={"help": "fields to omit from the Pydra interface"},
    )
    rename: ty.Dict[str, str] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={"help": "fields to rename in the Pydra interface"},
    )
    types: ty.Dict[str, type] = attrs.field(
        converter=types_converter,
        factory=dict,
        metadata={
            "help": """override inferred types (use \"mime-like\" string for file-format types,
                e.g. 'medimage/nifti-gz'). For most fields the type will be correctly inferred
                from the nipype interface, but you may want to be more specific, particularly
                for file types, where specifying the format also specifies the file that will be
                passed to the field in the automatically generated unittests."""
        },
    )


@attrs.define
class InputsConverter(SpecConverter):
    """Specification of how to conver Nipype inputs into Pydra inputs

    Parameters
    ----------
    omit : list[str], optional
        input fields to omit from the Pydra interface
    rename : dict[str, str], optional
        input fields to rename in the Pydra interface
    types : dict[str, type], optional
        Override inferred type (use mime-type string for file-format types).
        Most of the time the correct type will be inferred from the nipype interface,
        but you may want to be more specific, typically for the case of file types
        where specifying the format will change the type of file that will be
        passed to the field in the automatically generated unittests.
    metadata: dict[str, dict[str, Any]], optional
        additional metadata to set on any of the input fields (e.g. out_file: position: 1)
    """

    callable_defaults: ty.Dict[str, str] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": """names of methods/callable classes defined in the adjacent `*_callables.py`
                to set as the `default` method of input fields"""
        },
    )
    metadata: ty.Dict[str, ty.Dict[str, ty.Any]] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": "additional metadata to set on any of the input fields (e.g. out_file: position: 1)"
        },
    )


@attrs.define
class OutputsConverter(SpecConverter):
    """Specification of how to conver Nipype outputs into Pydra outputs

    Parameters
    ----------
    omit : list[str], optional
        input fields to omit from the Pydra interface
    rename : dict[str, str], optional
        input fields to rename in the Pydra interface
    types : dict[str, type], optional
        types to set explicitly (i.e. instead of determining from nipype interface),
        particularly relevant for file-types, where specifying the format will determine
        the type of file that is passed to the field in the automatically generated unittests
    callables : dict[str, str or callable], optional
        names of methods/callable classes defined in the adjacent `*_callables.py`
        to set to the `callable` attribute of output fields
    templates : dict[str, str], optional
        `output_file_template` values to be provided to output fields
    requirements : dict[str, list[str]]
        input fields that are required to be provided for the output field to be present
    """

    callables: ty.Dict[str, str] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": """names of methods/callable classes defined in the adjacent `*_callables.py`
                to set to the `callable` attribute of output fields"""
        },
    )
    templates: ty.Dict[str, str] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": "`output_file_template` values to be provided to output fields"
        },
    )
    requirements: ty.Dict[str, ty.List[str]] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": "input fields that are required to be provided for the output field to be present"
        },
    )

    @callables.validator
    def callables_validator(self, _, output_callables: dict):
        overlapping = set(output_callables.keys()) & set(self.templates.keys())
        if overlapping:
            raise ValueError(
                f"callables and templates have overlapping same keys: {overlapping}"
            )


@attrs.define
class TestGenerator:
    """Specifications for the automatically generated test for the generated Nipype spec

    Parameters
    ----------
    inputs : dict[str, str], optional
        values to provide to specific inputs fields (if not provided, a sensible value
        within the valid range will be provided)
    imports : list[ImportStatement or dict]
        list import statements required by the test, with each list item
        consisting of 'module', 'name', and optionally 'alias' keys
    expected_outputs: dict[str, str], optional
        expected values for selected outputs, noting that in tests will typically
        be terminated before they complete for time-saving reasons and will therefore
        be ignored
    timeout: int, optional
        the time to wait for in order to be satisfied that the tool has been initialised
        and performs any internal validation before exiting
    """

    inputs: ty.Dict[str, str] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": """values to provide to inputs fields in the task initialisation
                (if not specified, will try to choose a sensible value)"""
        },
    )
    imports: ty.List[ImportStatement] = attrs.field(
        factory=list,
        converter=from_list_to_imports,
        metadata={
            "help": """list import statements required by the test, with each list item
                consisting of 'module', 'name', and optionally 'alias' keys"""
        },
    )
    expected_outputs: ty.Dict[str, str] = attrs.field(
        factory=dict,
        converter=default_if_none(factory=dict),  # type: ignore
        metadata={
            "help": """expected values for selected outputs, noting that tests will typically
                be terminated before they complete for time-saving reasons, and therefore
                these values will be ignored, when running in CI"""
        },
    )
    timeout: int = attrs.field(
        default=10,
        metadata={
            "help": """the value to set for the timeout in the generated test, 
                after which the test will be considered to have been initialised 
                successfully. Set to 0 to disable the timeout (warning, this could
                lead to the unittests taking a very long time to complete)"""
        },
    )
    xfail: bool = attrs.field(
        default=True,
        metadata={
            "help": """whether the unittest is expected to fail or not. Set to false
                when you are satisfied with the edits you have made to this file"""
        },
    )


@attrs.define
class DocTestGenerator:
    """Specifies how the doctest should be constructed

    Parameters
    ----------
    cmdline: str
        the expected cmdline output
    inputs : dict[str, str or None]
        name-value pairs for inputs to be provided to the doctest. If the value is None
        then the ".mock()" method of the corresponding class is used instead.
    imports : list[ImportStatement or dict]
        list import statements required by the test, with each list item
        consisting of 'module', 'name', and optionally 'alias' keys
    directive : str
        any doctest directive to be applied to the cmdline line
    """

    cmdline: str = attrs.field(metadata={"help": "the expected cmdline output"})
    inputs: ty.Dict[str, str] = attrs.field(
        factory=dict,
        metadata={
            "help": """name-value pairs for inputs to be provided to the doctest.
                If the field is of file-format type and the value is None, then the
                '.mock()' method of the corresponding class is used instead."""
        },
    )
    imports: ty.List[ImportStatement] = attrs.field(
        factory=list,
        converter=from_list_to_imports,
        metadata={
            "help": """list import statements required by the test, with each list item
                consisting of 'module', 'name', and optionally 'alias' keys"""
        },
    )
    directive: str = attrs.field(
        default=None,
        metadata={
            "help": "any doctest directive to place on the cmdline call, e.g. # doctest: +ELLIPSIS"
        },
    )


def from_dict_to_inputs(obj: ty.Union[InputsConverter, dict]) -> InputsConverter:
    return from_dict_converter(obj, InputsConverter)


def from_dict_to_outputs(obj: ty.Union[OutputsConverter, dict]) -> OutputsConverter:
    return from_dict_converter(obj, OutputsConverter)


def from_list_to_tests(
    obj: ty.Union[ty.List[TestGenerator], list]
) -> ty.List[TestGenerator]:
    if obj is None:
        return []
    return [from_dict_converter(t, TestGenerator) for t in obj]


def from_list_to_doctests(
    obj: ty.Union[ty.List[DocTestGenerator], list]
) -> ty.List[DocTestGenerator]:
    if obj is None:
        return []
    return [from_dict_converter(t, DocTestGenerator) for t in obj]


@attrs.define
class BaseTaskConverter(metaclass=ABCMeta):
    """Specifies how the semi-automatic conversion from Nipype to Pydra should
    be performed

    Parameters
    ----------
    task_name: str
        name of the Pydra task
    nipype_module: str or ModuleType
        the nipype module or module path containing the Nipype interface
    nipype_name: str, optional
        the name of the task in the nipype module, defaults to the output task_name
    output_module: str
        relative path to the package root to write the output module to ('.' delimited)
    inputs: InputsConverter or dict
        specficiations for the conversion of inputs
    outputs: OutputsConverter or dict
        specficiations for the conversion of inputs
    tests: ty.List[TestGenerator] or list, optional
        specficiations for how to construct the test. A default test is generated if no
        specs are provided
    doctests: ty.List[DocTestGenerator] or list, optional
        specifications for how to construct the docttest. Doctest is omitted if not
        provided
    callables_module: ModuleType or str, optional
        a module, or path to a module, containing any required callables
    """

    task_name: str
    nipype_name: str
    nipype_module: ModuleType = attrs.field(
        converter=lambda m: import_module(m) if not isinstance(m, ModuleType) else m
    )
    output_module: str = attrs.field(default=None)
    inputs: InputsConverter = attrs.field(
        factory=InputsConverter, converter=from_dict_to_inputs
    )
    outputs: OutputsConverter = attrs.field(  # type: ignore
        factory=OutputsConverter,
        converter=from_dict_to_outputs,
    )
    callables_module: ModuleType = attrs.field(
        converter=import_module_from_path,
        default=None,
    )
    tests: ty.List[TestGenerator] = attrs.field(  # type: ignore
        factory=list, converter=from_list_to_tests
    )
    doctests: ty.List[DocTestGenerator] = attrs.field(
        factory=list, converter=from_list_to_doctests
    )

    def __attrs_post_init__(self):
        if self.output_module is None:
            if self.nipype_module.__name__.startswith("nipype.interfaces."):
                pkg_name = self.nipype_module.__name__.split(".")[2]
                self.output_module = (
                    f"pydra.tasks.{pkg_name}.auto.{to_snake_case(self.task_name)}"
                )
            else:
                raise RuntimeError(
                    "Output-module needs to be explicitly provided to task converter "
                    "when converting Nipype interefaces in non standard locations such "
                    f"as {self.nipype_module.__name__}.{self.task_name} (i.e. not in "
                    "nipype.interfaces)"
                )

    @property
    def nipype_interface(self) -> nipype.interfaces.base.BaseInterface:
        return getattr(self.nipype_module, self.nipype_name)

    @property
    def nipype_input_spec(self) -> nipype.interfaces.base.BaseInterfaceInputSpec:
        return (
            self.nipype_interface.input_spec()
            if self.nipype_interface.input_spec
            else None
        )

    @property
    def nipype_output_spec(self) -> nipype.interfaces.base.BaseTraitedSpec:
        return (
            self.nipype_interface.output_spec()
            if self.nipype_interface.output_spec
            else None
        )

    def generate(self, package_root: Path):
        """creating pydra input/output spec from nipype specs
        if write is True, a pydra Task class will be written to the file together with tests
        """
        input_fields, inp_templates = self.convert_input_fields()
        output_fields = self.convert_output_spec(fields_from_template=inp_templates)

        nonstd_types = set()

        def add_nonstd_types(tp):
            if ty.get_origin(tp) in (list, ty.Union):
                for tp_arg in ty.get_args(tp):
                    add_nonstd_types(tp_arg)
            elif tp.__module__ not in ["builtins", "pathlib", "typing"]:
                nonstd_types.add(tp)

        for f in input_fields:
            add_nonstd_types(f[1])

        for f in output_fields:
            add_nonstd_types(f[1])

        output_file = (
            Path(package_root)
            .joinpath(*self.output_module.split("."))
            .with_suffix(".py")
        )
        testdir = output_file.parent / "tests"
        testdir.mkdir(parents=True, exist_ok=True)

        self.write_task(
            output_file,
            input_fields=input_fields,
            output_fields=output_fields,
            nonstd_types=nonstd_types,
        )

        filename_test = testdir / f"test_{self.task_name.lower()}.py"
        # filename_test_run = testdir / f"test_run_{self.task_name.lower()}.py"
        self.write_tests(
            filename_test,
            input_fields=input_fields,
            nonstd_types=nonstd_types,
        )

    def convert_input_fields(self):
        """creating fields list for pydra input spec"""
        pydra_fields_dict = {}
        position_dict = {}
        has_template = []
        for name, fld in self.nipype_input_spec.traits().items():
            if name in self.TRAITS_IRREL:
                continue
            if name in self.inputs.omit:
                continue
            pydra_fld, pos = self.pydra_fld_input(fld, name)
            pydra_meta = pydra_fld[-1]
            if "output_file_template" in pydra_meta:
                has_template.append(name)
            pydra_fields_dict[name] = (name,) + pydra_fld
            if pos is not None:
                position_dict[name] = pos

        pydra_fields_l = list(pydra_fields_dict.values())
        return pydra_fields_l, has_template

    def pydra_fld_input(self, field, nm):
        """converting a single nipype field to one element of fields for pydra input_spec"""
        pydra_type = self.pydra_type_converter(field, spec_type="input", name=nm)
        if nm in self.inputs.metadata:
            metadata_extra_spec = self.inputs.metadata[nm]
        else:
            metadata_extra_spec = {}

        if "default" in metadata_extra_spec:
            pydra_default = metadata_extra_spec.pop("default")
        elif (
            getattr(field, "usedefault")
            and field.default is not traits.ctrait.Undefined
        ):
            pydra_default = field.default
        else:
            pydra_default = None

        pydra_metadata = {"help_string": ""}
        for key in self.INPUT_KEYS:
            pydra_key_nm = self.NAME_MAPPING.get(key, key)
            val = getattr(field, key)
            if val is not None:
                if key == "argstr" and "%" in val:
                    val = self.string_formats(argstr=val, name=nm)
                pydra_metadata[pydra_key_nm] = val

        if getattr(field, "name_template"):
            template = getattr(field, "name_template")
            name_source = ensure_list(getattr(field, "name_source"))
            if name_source:
                tmpl = self.string_formats(argstr=template, name=name_source[0])
            else:
                tmpl = template
            if nm in self.nipype_interface.output_spec().class_trait_names():
                pydra_metadata["output_file_template"] = tmpl
            if pydra_type in [specs.File, specs.Directory]:
                pydra_type = Path
        elif getattr(field, "genfile"):
            if nm in self.outputs.templates:
                try:
                    pydra_metadata["output_file_template"] = self.outputs.templates[nm]
                except KeyError:
                    raise Exception(
                        f"{nm} is has genfile=True and therefore needs an 'output_file_template' value"
                    )
                if pydra_type in [
                    specs.File,
                    specs.Directory,
                ]:  # since this is a template, the file doesn't exist
                    pydra_type = Path
            elif nm not in self.inputs.callable_defaults:
                raise Exception(
                    f"the filed {nm} has genfile=True, but no template or "
                    "`callables_default` function in the callables_module provided"
                )

        pydra_metadata.update(metadata_extra_spec)

        pos = pydra_metadata.get("position", None)

        if pydra_default is not None and not pydra_metadata.get("mandatory", None):
            return (pydra_type, pydra_default, pydra_metadata), pos
        else:
            return (pydra_type, pydra_metadata), pos

    def convert_output_spec(self, fields_from_template):
        """creating fields list for pydra input spec"""
        pydra_fields_l = []
        if not self.nipype_output_spec:
            return pydra_fields_l
        for name, fld in self.nipype_output_spec.traits().items():
            if (
                name not in self.TRAITS_IRREL
                and name not in fields_from_template
                and name not in self.outputs.omit
            ):
                pydra_fld = self.pydra_fld_output(fld, name)
                pydra_fields_l.append((name,) + pydra_fld)
        return pydra_fields_l

    def pydra_fld_output(self, field, name):
        """converting a single nipype field to one element of fields for pydra output_spec"""
        pydra_type = self.pydra_type_converter(field, spec_type="output", name=name)

        pydra_metadata = {}
        for key in self.OUTPUT_KEYS:
            pydra_key_nm = self.NAME_MAPPING.get(key, key)
            val = getattr(field, key)
            if val:
                pydra_metadata[pydra_key_nm] = val

        if name in self.outputs.requirements and self.outputs.requirements[name]:
            if all([isinstance(el, list) for el in self.outputs.requirements[name]]):
                requires_l = self.outputs.requirements[name]
                nested_flag = True
            elif all(
                [isinstance(el, (str, dict)) for el in self.outputs.requirements[name]]
            ):
                requires_l = [self.outputs.requirements[name]]
                nested_flag = False
            else:
                Exception("has to be either list of list or list of str/dict")

            pydra_metadata["requires"] = []
            for requires in requires_l:
                requires_mod = []
                for el in requires:
                    if isinstance(el, str):
                        requires_mod.append(el)
                    elif isinstance(el, dict):
                        requires_mod += list(el.items())
                pydra_metadata["requires"].append(requires_mod)
            if nested_flag is False:
                pydra_metadata["requires"] = pydra_metadata["requires"][0]

        if name in self.outputs.templates:
            pydra_metadata["output_file_template"] = self.interface_spec[
                "output_templates"
            ][name]
        elif name in self.outputs.callables:
            pydra_metadata["callable"] = self.outputs.callables[name]
        return (pydra_type, pydra_metadata)

    def function_callables(self):
        if not self.outputs.callables:
            return ""
        if not self.callables_module:
            raise Exception(
                "callables module must be provided if output_callables are set in the spec file"
            )
        fun_str = ""
        fun_names = list(set(self.outputs.callables.values()))
        fun_names.sort()
        for fun_nm in fun_names:
            fun = getattr(self.callables_module, fun_nm)
            fun_str += inspect.getsource(fun) + "\n"
        return fun_str

    def pydra_type_converter(self, field, spec_type, name):
        """converting types to types used in pydra"""
        if spec_type not in ["input", "output"]:
            raise Exception(
                f"spec_type has to be input or output, but {spec_type} provided"
            )
        types_dict = self.inputs.types if spec_type == "input" else self.outputs.types
        try:
            return types_dict[name]
        except KeyError:
            pass
        trait_tp = field.trait_type
        if isinstance(trait_tp, traits.trait_types.Int):
            pydra_type = int
        elif isinstance(trait_tp, traits.trait_types.Float):
            pydra_type = float
        elif isinstance(trait_tp, traits.trait_types.Str):
            pydra_type = str
        elif isinstance(trait_tp, traits.trait_types.Bool):
            pydra_type = bool
        elif isinstance(trait_tp, traits.trait_types.Dict):
            pydra_type = dict
        elif isinstance(trait_tp, traits_extension.InputMultiObject):
            if isinstance(field.inner_traits[0].trait_type, traits_extension.File):
                pydra_type = ty.List[File]
            else:
                pydra_type = specs.MultiInputObj
        elif isinstance(trait_tp, traits_extension.OutputMultiObject):
            if isinstance(field.inner_traits[0].trait_type, traits_extension.File):
                pydra_type = specs.MultiOutputFile
            else:
                pydra_type = specs.MultiOutputObj
        elif isinstance(trait_tp, traits.trait_types.List):
            if isinstance(field.inner_traits[0].trait_type, traits_extension.File):
                if spec_type == "input":
                    pydra_type = ty.List[File]
                else:
                    pydra_type = specs.MultiOutputFile
            else:
                pydra_type = list
        elif isinstance(trait_tp, traits_extension.File):
            if (
                spec_type == "output" or trait_tp.exists is True
            ):  # TODO check the hash_file metadata in nipype
                pydra_type = specs.File
            else:
                pydra_type = Path
        else:
            pydra_type = ty.Any
        return pydra_type

    def string_formats(self, argstr, name):
        keys = re.findall(r"(%[0-9\.]*(?:s|d|i|g|f))", argstr)
        new_argstr = argstr
        for i, key in enumerate(keys):
            repl = f"{name}" if len(keys) == 1 else f"{name}[{i}]"
            match = re.match(r"%([0-9\.]+)f", key)
            if match:
                repl += ":" + match.group(1)
            new_argstr = new_argstr.replace(key, r"{" + repl + r"}", 1)
        return new_argstr

    def write_task(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        spec_str = self.generate_task_str(
            filename, input_fields, nonstd_types, output_fields
        )

        spec_str = black.format_file_contents(
            spec_str, fast=False, mode=black.FileMode()
        )

        # # FIXME: bit of a hack, should make sure that multi-input/output objects
        # #        are referenced properly without this substitution
        # spec_str = re.sub(
        #     r"(?<!specs\.|mport )Multi(Input|Output)", r"specs.Multi\1", spec_str
        # )

        with open(filename, "w") as f:
            f.write(spec_str)

    @abstractmethod
    def generate_task_str(self, filename, input_fields, nonstd_types, output_fields):
        raise NotImplementedError

    def construct_imports(
        self, nonstd_types: ty.List[type], spec_str="", base=(), include_task=True
    ) -> ty.List[str]:
        """Constructs a list of imports to include at start of file"""
        stmts: ty.Dict[str, str] = {}

        def add_import(stmt):
            if stmt == "from nipype import logging":
                return
            match = re.match(r".*\s+as\s+(\w+)\s*", stmt)
            if not match:
                match = re.match(r".*import\s+([\w\., ]+)\s*$", stmt)
            if not match:
                raise ValueError(f"Unrecognised import statment {stmt}")
            token = match.group(1)
            try:
                prev_stmt = stmts[token]
            except KeyError:
                pass
            else:
                if prev_stmt != stmt:
                    logger.warning(
                        f"Cannot add import statement {stmt} as it clashes with "
                        f"previous import {prev_stmt}"
                    )
            stmts[token] = stmt

        for b in base:
            add_import(b)

        if re.match(r".*(?<!\w)ty\.", spec_str, flags=re.MULTILINE | re.DOTALL):
            add_import("import typing as ty")
        if re.match(r".*\bPath\b", spec_str, flags=re.MULTILINE | re.DOTALL):
            add_import("from pathlib import Path")
        if re.match(r".*\blogging\b", spec_str, flags=re.MULTILINE | re.DOTALL):
            add_import("import logging")
        for test in self.tests:
            for stmt in test.imports:
                if "nipype" in stmt.module:
                    continue
                if stmt.name is None:
                    add_import(f"import {stmt.module}")
                else:
                    nm = (
                        stmt.name
                        if stmt.alias is None
                        else f"{stmt.name} as {stmt.alias}"
                    )
                    add_import(f"from {stmt.module} import {nm}")

        def unwrap_nested_type(t: type) -> ty.List[type]:
            if issubclass(t, WithClassifiers) and t.is_classified:
                unwrapped = [t.unclassified]
                for c in t.classifiers:
                    unwrapped.extend(unwrap_nested_type(c))
                return unwrapped
            return [t]

        for tp in itertools.chain(*(unwrap_nested_type(t) for t in nonstd_types)):
            add_import(f"from {tp.__module__} import {tp.__name__}")
        if include_task:
            add_import(f"from {self.output_module} import {self.task_name}")

        return sorted(stmts.values())

    def write_tests(self, filename_test, input_fields, nonstd_types, run=False):
        spec_str = ""
        for i, test in enumerate(self.tests, start=1):
            if test.xfail:
                spec_str += "@pytest.mark.xfail\n"
            # spec_str += f"@pass_after_timeout(seconds={test.timeout})\n"
            spec_str += f"def test_{self.task_name.lower()}_{i}():\n"
            spec_str += f"    task = {self.task_name}()\n"
            for i, field in enumerate(input_fields):
                nm, tp = field[:2]
                # Try to get a sensible value for the traits value
                try:
                    value = test.inputs[nm]
                except KeyError:
                    pass
                else:
                    if value is None:
                        if is_fileset(tp):
                            value = f"{tp.__name__}.sample(seed={i})"
                        elif ty.get_origin(tp) in (list, ty.Union) and is_fileset(
                            ty.get_args(tp)[0]
                        ):
                            arg_tp = ty.get_args(tp)[0]
                            value = f"{arg_tp.__name__}.sample(seed={i})"
                            if ty.get_origin(tp) is list:
                                value = "[" + value + "]"
                        else:
                            if len(field) == 4:  # field has default
                                if isinstance(field[2], bool):
                                    value = str(field[2])
                                else:
                                    value = json.dumps(field[2])
                            else:
                                assert len(field) == 3
                                # Attempt to pick a sensible value for field
                                trait = self.nipype_interface.input_spec.class_traits()[
                                    nm
                                ]
                                if isinstance(trait, traits.trait_types.Enum):
                                    value = trait.values[0]
                                elif isinstance(trait, traits.trait_types.Range):
                                    value = (trait.high - trait.low) / 2.0
                                elif isinstance(trait, traits.trait_types.Bool):
                                    value = True
                                elif isinstance(trait, traits.trait_types.Int):
                                    value = 1
                                elif isinstance(trait, traits.trait_types.Float):
                                    value = 1.0
                                elif isinstance(trait, traits.trait_types.List):
                                    value = [1] * trait.minlen
                                elif isinstance(trait, traits.trait_types.Tuple):
                                    value = tuple([1] * len(trait.types))
                                else:
                                    value = attrs.NOTHING
                    if value is not attrs.NOTHING:
                        spec_str += f"    task.inputs.{nm} = {value}\n"
            if hasattr(self.nipype_interface, "_cmd"):
                spec_str += r'    print(f"CMDLINE: {task.cmdline}\n\n")' + "\n"
            spec_str += "    res = task(plugin=PassAfterTimeoutWorker)\n"
            spec_str += "    print('RESULT: ', res)\n"
            for name, value in test.expected_outputs.items():
                spec_str += f"    assert res.output.{name} == {value}\n"
            spec_str += "\n\n\n"

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            base={
                "import pytest",
                "from nipype2pydra.testing import PassAfterTimeoutWorker",
            },
        )
        spec_str = "\n".join(imports) + "\n\n" + spec_str

        try:
            spec_str_black = black.format_file_contents(
                spec_str, fast=False, mode=black.FileMode()
            )
        except black.parsing.InvalidInput as e:
            raise RuntimeError(
                f"Black could not parse generated code: {e}\n\n{spec_str}"
            )

        with open(filename_test, "w") as f:
            f.write(spec_str_black)

        conftest_fspath = filename_test.parent / "conftest.py"
        if not conftest_fspath.exists():
            with open(conftest_fspath, "w") as f:
                f.write(self.CONFTEST)

    def create_doctests(self, input_fields, nonstd_types):
        """adding doctests to the interfaces"""
        doctest_str = ""
        for doctest in self.doctests:
            doctest_str += f"    >>> task = {self.task_name}()\n"
            for field in input_fields:
                nm, tp = field[:2]
                try:
                    val = doctest.inputs[nm]
                except KeyError:
                    if is_fileset(tp):
                        val = f"{tp.__name__}.mock()"
                    else:
                        val = attrs.NOTHING
                else:
                    if isinstance(val, str):
                        val = f'"{val}"'
                if val is not attrs.NOTHING:
                    doctest_str += f"    >>> task.inputs.{nm} = {val}\n"
            doctest_str += "    >>> task.cmdline\n"
            doctest_str += f"    '{doctest.cmdline}'"
            doctest_str += "\n\n\n"

        imports = self.construct_imports(nonstd_types, doctest_str)
        if imports:
            doctest_str = "    >>> " + "\n    >>> ".join(imports) + "\n\n" + doctest_str

        return "    Examples\n    -------\n\n" + doctest_str

    INPUT_KEYS = [
        "allowed_values",
        "argstr",
        "container_path",
        "copyfile",
        "desc",
        "mandatory",
        "position",
        "requires",
        "sep",
        "xor",
    ]
    OUTPUT_KEYS = ["desc"]
    NAME_MAPPING = {"desc": "help_string"}

    TRAITS_IRREL = [
        "output_type",
        "args",
        "environ",
        "environ_items",
        "__all__",
        "trait_added",
        "trait_modified",
    ]

    CONFTEST = """
# For debugging in IDE's don't catch raised exceptions and let the IDE
# break at it
import os
import pytest


if os.getenv("_PYTEST_RAISE", "0") != "0":

    @pytest.hookimpl(tryfirst=True)
    def pytest_exception_interact(call):
        raise call.excinfo.value  # raise internal errors instead of capturing them

    @pytest.hookimpl(tryfirst=True)
    def pytest_internalerror(excinfo):
        raise excinfo.value  # raise internal errors instead of capturing them

    def pytest_configure(config):
        config.option.capture = 'no'  # allow print statements to show up in the console
        config.option.log_cli = True  # show log messages in the console
        config.option.log_level = "INFO"  # set the log level to INFO

    CATCH_CLI_EXCEPTIONS = False
else:
    CATCH_CLI_EXCEPTIONS = True
"""
