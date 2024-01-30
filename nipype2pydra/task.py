import os
from pathlib import Path
import typing as ty
import re
from importlib import import_module
from types import ModuleType
import itertools
import inspect
from functools import cached_property
import itertools
import black
import traits.trait_types
import json
import attrs
from attrs.converters import default_if_none
import nipype.interfaces.base
from nipype.interfaces.base import traits_extension
from pydra.engine import specs
from pydra.engine.helpers import ensure_list
from .utils import import_module_from_path, is_fileset, to_snake_case
from fileformats.core import from_mime
from fileformats.core.mixin import WithClassifiers
from fileformats.generic import File


T = ty.TypeVar("T")


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
    elif "." in type_str:
        parts = type_str.split(".")
        module = import_module(".".join(parts[:-1]))
        tp = getattr(module, parts[-1])
        if not inspect.isclass(tp):
            raise TypeError(f"Designated type at {type_str} is not a class {tp}")
    elif re.match(r"^\w+$", type_str):
        tp = eval(type_str)
    else:
        raise ValueError(f"Cannot parse {type_str} to a type safely")
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
class TaskConverter:
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
        converter=import_module_from_path, default=None
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

    @classmethod
    def load(cls, nipype_module: str, nipype_name: str, **kwargs):
        nipype_interface = getattr(import_module(nipype_module), nipype_name)

        if hasattr(nipype_interface, "_cmd"):
            converter_cls = ShellCommandTaskConverter
        else:
            converter_cls = FunctionTaskConverter
        return converter_cls(
            nipype_module=nipype_module, nipype_name=nipype_name, **kwargs
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
            pydra_metadata["output_file_template"] = tmpl
            if pydra_type in [specs.File, specs.Directory]:
                pydra_type = str
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
            elif nm not in self.outputs.callables:
                raise Exception(
                    f"the filed {nm} has genfile=True, but no output template or callables_module provided"
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
            if name not in self.TRAITS_IRREL and name not in fields_from_template:
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
        python_functions_spec = (
            Path(os.path.dirname(__file__)) / "../specs/callables.py"
        )
        if not python_functions_spec.exists():
            raise Exception(
                "specs/callables.py file is needed if output_callables in the spec files"
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

        def unwrap_field_type(t):
            if issubclass(t, WithClassifiers) and t.is_classified:
                unwraped_classifiers = ", ".join(unwrap_field_type(c) for c in t.classifiers)
                return f"{t.unclassified.__name__}[{unwraped_classifiers}]"
            return t.__name__

        def types_to_names(spec_fields):
            spec_fields_str = []
            for el in spec_fields:
                el = list(el)
                field_type = el[1]
                if inspect.isclass(field_type) and issubclass(field_type, WithClassifiers):
                    field_type_str = unwrap_field_type(field_type)
                else:
                    field_type_str = str(field_type)
                    if field_type_str.startswith("<class "):
                        field_type_str = el[1].__name__
                    else:
                        # Alter modules in type string to match those that will be imported
                        field_type_str = field_type_str.replace("typing", "ty")
                        field_type_str = re.sub(r"(\w+\.)+(?<!ty\.)(\w+)", r"\2", field_type_str)
                el[1] = "#" + field_type_str + "#"
                spec_fields_str.append(tuple(el))
            return spec_fields_str

        base_imports = [
            "from pydra.engine import specs",
        ]
        if hasattr(self.nipype_interface, "_cmd"):
            task_base = "ShellCommandTask"
            base_imports.append("from pydra.engine import ShellCommandTask")
        else:
            task_base = "FunctionTask"
            base_imports.append("from pydra.engine.task import FunctionTask")

        try:
            executable = self.nipype_interface._cmd
        except AttributeError:
            executable = None
        if not executable:
            executable = self.nipype_interface.cmd
            if not isinstance(executable, str):
                raise RuntimeError(
                    f"Could not find executable for {self.nipype_interface}"
                )

        input_fields_str = types_to_names(spec_fields=input_fields)
        output_fields_str = types_to_names(spec_fields=output_fields)
        functions_str = self.function_callables()
        spec_str = functions_str
        spec_str += f"input_fields = {input_fields_str}\n"
        spec_str += f"{self.task_name}_input_spec = specs.SpecInfo(name='Input', fields=input_fields, bases=(specs.ShellSpec,))\n\n"
        spec_str += f"output_fields = {output_fields_str}\n"
        spec_str += f"{self.task_name}_output_spec = specs.SpecInfo(name='Output', fields=output_fields, bases=(specs.ShellOutSpec,))\n\n"
        spec_str += f"class {self.task_name}({task_base}):\n"
        spec_str += '    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'
        spec_str += f"    input_spec = {self.task_name}_input_spec\n"
        spec_str += f"    output_spec = {self.task_name}_output_spec\n"
        if task_base == "ShellCommandTask":
            spec_str += f"    executable='{executable}'\n"

        spec_str = re.sub(r"'#([^'#]+)#'", r"\1", spec_str)

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            include_task=False,
            base=base_imports,
        )
        spec_str = "\n".join(imports) + "\n\n" + spec_str

        spec_str = black.format_file_contents(
            spec_str, fast=False, mode=black.FileMode()
        )

        with open(filename, "w") as f:
            f.write(spec_str)

    def construct_imports(
        self, nonstd_types: ty.List[type], spec_str="", base=(), include_task=True
    ) -> ty.List[str]:
        """Constructs a list of imports to include at start of file"""
        stmts: ty.Dict[str, str] = {}

        def add_import(stmt):
            match = re.match(r".*\s+as\s+(\w+)\s*", stmt)
            if not match:
                match = re.match(r".*import\s+([\w\.]+)\s*$", stmt)
            if not match:
                raise ValueError(f"Unrecognised import statment {stmt}")
            token = match.group(1)
            try:
                prev_stmt = stmts[token]
            except KeyError:
                pass
            else:
                if prev_stmt != stmt:
                    raise ValueError(
                        f"Cannot add import statement {stmt} as it clashes with "
                        f"previous import {prev_stmt}"
                    )
            stmts[token] = stmt

        for b in base:
            add_import(b)

        if re.match(r".*(?<!\w)ty\.", spec_str, flags=re.MULTILINE | re.DOTALL):
            add_import("import typing as ty")
        if re.match(r".*(?<!\w)Path(?!\w)", spec_str, flags=re.MULTILINE | re.DOTALL):
            add_import("from pathlib import Path")
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

        return list(stmts.values())

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
                                trait = self.nipype_interface.input_spec.class_traits()[nm]
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
            spec_str += "    res = task(plugin=\"with-timeout\")\n"
            spec_str += "    print('RESULT: ', res)\n"
            for name, value in test.expected_outputs.items():
                spec_str += f"    assert res.output.{name} == {value}\n"
            spec_str += "\n\n\n"

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            base={"import pytest"}  # , "from conftest import pass_after_timeout"},
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
                f.write(self.TIMEOUT_PASS)

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
                    if type(val) is str:
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

    TIMEOUT_PASS = """import time
from traceback import format_exc
import threading
from dataclasses import dataclass
from _pytest.runner import TestReport


def pass_after_timeout(seconds, poll_interval=0.1):
    \"\"\"Cancel the test after a certain period, after which it is assumed that the arguments
    passed to the underying command have passed its internal validation (so we don't have
    to wait until the tool completes)

    Parameters
    ----------
    seconds : int
        the number of seconds to wait until cancelling the test (and marking it as passed)
    \"\"\"

    def decorator(test_func):
        def wrapper(*args, **kwargs):
            @dataclass
            class TestState:
                \"\"\"A way of passing a reference to the result that can be updated by
                the test thread\"\"\"

                result = None
                trace_back = None

            state = TestState()

            def test_runner():
                try:
                    state.result = test_func(*args, **kwargs)
                except Exception:
                    state.trace_back = format_exc()
                    raise

            thread = threading.Thread(target=test_runner)
            thread.start()

            # Calculate the end time for the timeout
            end_time = time.time() + seconds

            while thread.is_alive() and time.time() < end_time:
                time.sleep(poll_interval)

            if thread.is_alive():
                thread.join()
                return state.result

            if state.trace_back:
                raise state.trace_back

            outcome = "passed after timeout"
            rep = TestReport.from_item_and_call(
                item=args[0],
                when="call",
                excinfo=None,
                outcome=outcome,
                sections=None,
                duration=0,
                keywords=None,
            )
            args[0].ihook.pytest_runtest_logreport(report=rep)

            return state.result

        return wrapper

    return decorator
"""


@attrs.define
class FunctionTaskConverter(TaskConverter):
    def write_task(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        base_imports = [
            "import pydra.mark",
        ]

        def types_to_names(spec_fields):
            spec_fields_str = []
            for el in spec_fields:
                el = list(el)
                tp_str = str(el[1])
                if tp_str.startswith("<class "):
                    tp_str = el[1].__name__
                else:
                    # Alter modules in type string to match those that will be imported
                    tp_str = tp_str.replace("typing", "ty")
                    tp_str = re.sub(r"(\w+\.)+(?<!ty\.)(\w+)", r"\2", tp_str)
                el[1] = tp_str
                spec_fields_str.append(tuple(el))
            return spec_fields_str

        input_fields_str = types_to_names(spec_fields=input_fields)
        output_fields_str = types_to_names(spec_fields=output_fields)
        input_names = [i[0] for i in input_fields]
        output_names = [o[0] for o in output_fields]
        output_type_names = [o[1] for o in output_fields_str]

        # Combined src of run_interface and list_outputs
        function_body = inspect.getsource(self.nipype_interface._run_interface).strip()
        function_body = "\n".join(function_body.split("\n")[1:-1])
        lo_src = inspect.getsource(self.nipype_interface._list_outputs).strip()
        lo_lines = lo_src.split("\n")
        lo_src = "\n".join(lo_lines[1:-1])
        function_body += lo_src

        # Replace return outputs dictionary with individual outputs
        return_line = lo_lines[-1]
        match = re.match(r"\s*return(.*)", return_line)
        return_value = match.group(1).strip()
        output_re = re.compile(return_value + r"\[(?:'|\")(\w+)(?:'|\")\]")
        unrecognised_outputs = set(
            m for m in output_re.findall(function_body) if m not in output_names
        )
        assert (
            not unrecognised_outputs
        ), f"Found the following unrecognised outputs {unrecognised_outputs}"
        function_body = output_re.sub(r"\1", function_body)
        function_body = self.process_function_body(function_body, input_names)

        # Create the spec string
        spec_str = self.function_callables()
        spec_str += "@pydra.mark.task\n"
        spec_str += "@pydra.mark.annotate({'return': {"
        spec_str += ", ".join(f"'{n}': {t}" for n, t, _ in output_fields_str)
        spec_str += "}})\n"
        spec_str += f"def {self.task_name}("
        spec_str += ", ".join(f"{i[0]}: {i[1]}" for i in input_fields_str)
        spec_str += ") -> "
        if len(output_type_names) > 1:
            spec_str += "ty.Tuple[" + ", ".join(output_type_names) + "]"
        else:
            spec_str += output_type_names[0]
        spec_str += ':\n    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'
        spec_str += function_body + "\n"
        spec_str += "\n    return {}".format(", ".join(output_names))

        for f in self.local_functions:
            spec_str += "\n\n" + inspect.getsource(f)
        spec_str += "\n\n".join(
            inspect.getsource(f) for f in self.local_functions
        )

        spec_str += "\n\n" + "\n\n".join(
            self.process_method(m, input_names, output_names) for m in self.referenced_methods
        )

        # Replace runtime attributes
        additional_imports = set()
        for attr, repl, imprt in self.RUNTIME_ATTRS:
            repl_spec_str = spec_str.replace(f"runtime.{attr}", repl)
            if repl_spec_str != spec_str:
                additional_imports.add(imprt)
                spec_str = repl_spec_str

        other_imports = self.get_imports(
            [function_body] + [inspect.getsource(f) for f in itertools.chain(self.referenced_local_functions, self.referenced_methods)]
        )

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            include_task=False,
            base=base_imports + other_imports + list(additional_imports),
        )
        spec_str = "\n".join(imports) + "\n\n" + spec_str

        spec_str = black.format_file_contents(
            spec_str, fast=False, mode=black.FileMode()
        )

        with open(filename, "w") as f:
            f.write(spec_str)

    def process_method(
        self,
        func: str,
        input_names: ty.List[str],
        output_names: ty.List[str],
    ):
        src = inspect.getsource(func)
        pre, arglist, post = self.split_parens_contents(src)
        if func.__name__ in self.method_args:
            arglist = (arglist + ", " if arglist else "") + ", ".join(f"{a}=None" for a in self.method_args[func.__name__])
        # Insert method args in signature if present
        return_types, function_body = post.split(":", maxsplit=1)
        function_body = function_body.split("\n", maxsplit=1)[1]
        function_body = self.process_function_body(function_body, input_names)
        return f"{pre.strip()}{arglist}{return_types}:\n{function_body}"

    def process_function_body(self, function_body: str, input_names: ty.List[str]) -> str:
        """Replace self.inputs.<name> with <name> in the function body and add args to the
        function signature

        Parameters
        ----------
        function_body: str
            The source code of the function to process
        input_names: list[str]
            The names of the inputs to the function

        Returns
        -------
        function_body: str
            The processed source code
        """
        # Replace self.inputs.<name> with <name> in the function body
        input_re = re.compile(r"self\.inputs\.(\w+)")
        unrecognised_inputs = set(
            m for m in input_re.findall(function_body) if m not in input_names
        )
        assert (
            not unrecognised_inputs
        ), f"Found the following unrecognised inputs {unrecognised_inputs}"
        function_body = input_re.sub(r"\1", function_body)
        # Add args to the function signature of method calls
        method_re = re.compile(r"self\.(\w+)(?=\()", flags=re.MULTILINE | re.DOTALL)
        method_names = [m.__name__ for m in self.referenced_methods]
        unrecognised_methods = set(
            m for m in method_re.findall(function_body) if m not in method_names
        )
        assert (
            not unrecognised_methods
        ), f"Found the following unrecognised methods {unrecognised_methods}"
        splits = method_re.split(function_body)
        new_body = splits[0]
        for name, args in zip(splits[1::2], splits[2::2]):
            new_body += name + self.insert_args_in_signature(args, [f"{a}={a}" for a in self.method_args[name]])
        function_body = new_body
        # Detect the indentation of the source code in src and reduce it to 4 spaces
        indents = re.findall(r"^\s+", function_body, flags=re.MULTILINE)
        min_indent = min(len(i) for i in indents if i)
        indent_reduction = min_indent - 4
        function_body = re.sub(r"^" + " " * indent_reduction, "", function_body, flags=re.MULTILINE)
        return function_body

    def get_imports(
        self, function_bodies: ty.List[str]
    ) -> ty.Tuple[ty.List[str], ty.List[str]]:
        """Get the imports required for the function body

        Parameters
        ----------
        src: str
            the source of the file to extract the import statements from
        """
        imports = []
        block = ""
        for line in self.source_code.split("\n"):
            if line.startswith("from") or line.startswith("import"):
                if "(" in line:
                    block = line
                else:
                    imports.append(line)
            if ")" in line and block:
                imports.append(block + line)
                block = ""
        # extract imported symbols from import statements
        used_symbols = set()
        for function_body in function_bodies:
            # Strip comments from function body
            function_body = re.sub(r"\s*#.*", "", function_body)
            used_symbols.update(re.findall(r"(\w+)", function_body))
        used_imports = []
        for stmt in imports:
            stmt = stmt.replace("\n", "")
            stmt = stmt.replace("(", "")
            stmt = stmt.replace(")", "")
            base_stmt, symbol_str = stmt.split("import ")
            symbol_parts = symbol_str.split(",")
            split_parts = [p.split(" as ") for p in symbol_parts]
            split_parts = [p for p in split_parts if p[-1] in used_symbols]
            if split_parts:
                used_imports.append(
                    base_stmt
                    + "import "
                    + ",".join(" as ".join(p) for p in split_parts)
                )
        return used_imports

    @property
    def referenced_local_functions(self):
        return self._referenced_funcs_and_methods[0]

    @property
    def referenced_methods(self):
        return self._referenced_funcs_and_methods[1]

    @property
    def method_args(self):
        return self._referenced_funcs_and_methods[2]

    @cached_property
    def _referenced_funcs_and_methods(self):
        referenced_funcs = set()
        referenced_methods = set()
        method_args = {}
        self._get_referenced(
            self.nipype_interface._run_interface,
            referenced_funcs,
            referenced_methods,
            method_args,
        )
        self._get_referenced(
            self.nipype_interface._list_outputs,
            referenced_funcs,
            referenced_methods,
            method_args,
        )
        return referenced_funcs, referenced_methods, method_args

    def replace_attributes(self, function_body: ty.Callable) -> str:
        """Replace self.inputs.<name> with <name> in the function body and add args to the
        function signature"""
        function_body = re.sub(r"self\.inputs\.(\w+)", r"\1", function_body)

    def _get_referenced(
        self,
        function: ty.Callable,
        referenced_funcs: ty.Set[ty.Callable],
        referenced_methods: ty.Set[ty.Callable],
        method_args: ty.Dict[str, ty.List[str]],
    ):
        """Get the local functions referenced in the source code

        Parameters
        ----------
        src: str
            the source of the file to extract the import statements from
        referenced_funcs: set[function]
            the set of local functions that have been referenced so far
        referenced_methods: set[function]
            the set of methods that have been referenced so far
        """
        function_body = inspect.getsource(function)
        function_body = re.sub(r"\s*#.*", "", function_body)
        ref_local_func_names = re.findall(r"(?<!self\.)(\w+)\(", function_body)
        ref_local_funcs = set(
            f
            for f in self.local_functions
            if f.__name__ in ref_local_func_names and f not in referenced_funcs
        )

        ref_method_names = re.findall(r"(?<=self\.)(\w+)\(", function_body)
        ref_methods = set(m for m in self.methods if m.__name__ in ref_method_names)

        referenced_funcs.update(ref_local_funcs)
        referenced_methods.update(ref_methods)

        referenced_inputs = set(re.findall(r"(?<=self\.inputs\.)(\w+)", function_body))
        for func in ref_local_funcs:
            referenced_inputs.update(
                self._get_referenced(func, referenced_funcs, referenced_methods)
            )
        for meth in ref_methods:
            ref_inputs = self._get_referenced(
                meth, referenced_funcs, referenced_methods, method_args=method_args
            )
            method_args[meth.__name__] = ref_inputs
            referenced_inputs.update(ref_inputs)
        return referenced_inputs

    @cached_property
    def source_code(self):
        with open(inspect.getsourcefile(self.nipype_interface)) as f:
            return f.read()

    @cached_property
    def local_functions(self):
        """Get the functions defined in the same file as the interface"""
        functions = []
        for attr_name in dir(self.nipype_module):
            attr = getattr(self.nipype_module, attr_name)
            if (
                inspect.isfunction(attr)
                and attr.__module__ == self.nipype_module.__name__
            ):
                functions.append(attr)
        return functions

    @cached_property
    def methods(self):
        """Get the functions defined in the interface"""
        methods = []
        for attr_name in dir(self.nipype_interface):
            if attr_name.startswith("__"):
                continue
            attr = getattr(self.nipype_interface, attr_name)
            if inspect.isfunction(attr):
                methods.append(attr)
        return methods

    @cached_property
    def local_function_names(self):
        return [f.__name__ for f in self.local_functions]

    RUNTIME_ATTRS = (
        ("cwd", "os.getcwd()", "import os"),
        ("environ", "os.environ", "import os"),
        ("hostname", "platform.node()", "import platform"),
        ("platform", "platform.platform()", "import platform"),
    )

    @classmethod
    def insert_args_in_signature(cls, snippet: str, args: ty.Iterable[str]) -> str:
        """Insert the arguments into the function signature"""
        # Insert method args in signature if present
        pre, contents, post = cls.split_parens_contents(snippet)
        return pre + (contents + ", " if contents else "") + ", ".join(args) + post

    @classmethod
    def split_parens_contents(cls, snippet):
        """Splits the code snippet at the first opening parenthesis into a 3-tuple
        consisting of the pre-paren text, the contents of the parens and the post-paren

        Parameters
        ----------
        snippet: str
            the code snippet to split

        Returns
        -------
        pre: str
            the text before the opening parenthesis
        contents: str
            the contents of the parens
        post: str
            the text after the closing parenthesis
        """
        splits = re.split(r"(\(|\))", snippet, flags=re.MULTILINE | re.DOTALL)
        depth = 1
        pre = "".join(splits[:2])
        contents = ""
        for i, s in enumerate(splits[2:], start=2):
            if s == "(":
                depth += 1
            else:
                if s == ")":
                    depth -= 1
                    if depth == 0:
                        return pre, contents, "".join(splits[i:])
                contents += s
        raise ValueError(f"No matching parenthesis found in '{snippet}'")


@attrs.define
class ShellCommandTaskConverter(TaskConverter):
    def write_task(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        base_imports = [
            "from pydra.engine import specs",
        ]

        task_base = "ShellCommandTask"
        base_imports.append("from pydra.engine import ShellCommandTask")

        try:
            executable = self.nipype_interface._cmd
        except AttributeError:
            executable = None
        if not executable:
            executable = self.nipype_interface.cmd
            if not isinstance(executable, str):
                raise RuntimeError(
                    f"Could not find executable for {self.nipype_interface}"
                )

        def types_to_names(spec_fields):
            spec_fields_str = []
            for el in spec_fields:
                el = list(el)
                tp_str = str(el[1])
                if tp_str.startswith("<class "):
                    tp_str = el[1].__name__
                else:
                    # Alter modules in type string to match those that will be imported
                    tp_str = tp_str.replace("typing", "ty")
                    tp_str = re.sub(r"(\w+\.)+(?<!ty\.)(\w+)", r"\2", tp_str)
                el[1] = "#" + tp_str + "#"
                spec_fields_str.append(tuple(el))
            return spec_fields_str

        input_fields_str = types_to_names(spec_fields=input_fields)
        output_fields_str = types_to_names(spec_fields=output_fields)
        functions_str = self.function_callables()
        spec_str = functions_str
        spec_str += f"input_fields = {input_fields_str}\n"
        spec_str += f"{self.task_name}_input_spec = specs.SpecInfo(name='Input', fields=input_fields, bases=(specs.ShellSpec,))\n\n"
        spec_str += f"output_fields = {output_fields_str}\n"
        spec_str += f"{self.task_name}_output_spec = specs.SpecInfo(name='Output', fields=output_fields, bases=(specs.ShellOutSpec,))\n\n"
        spec_str += f"class {self.task_name}({task_base}):\n"
        spec_str += '    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'
        spec_str += f"    input_spec = {self.task_name}_input_spec\n"
        spec_str += f"    output_spec = {self.task_name}_output_spec\n"
        if task_base == "ShellCommandTask":
            spec_str += f"    executable='{executable}'\n"

        spec_str = re.sub(r"'#([^'#]+)#'", r"\1", spec_str)

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            include_task=False,
            base=base_imports,
        )
        spec_str = "\n".join(imports) + "\n\n" + spec_str

        spec_str = black.format_file_contents(
            spec_str, fast=False, mode=black.FileMode()
        )

        with open(filename, "w") as f:
            f.write(spec_str)
