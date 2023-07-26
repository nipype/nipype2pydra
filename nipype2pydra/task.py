import os
from pathlib import Path
import typing as ty
import re
from importlib import import_module
from types import ModuleType
import inspect
import black
import traits.trait_types
import attrs
from attrs.converters import default_if_none
import nipype.interfaces.base
from nipype.interfaces.base import traits_extension
from pydra.engine import specs
from pydra.engine.helpers import ensure_list
from .utils import import_module_from_path
from fileformats.core import DataType, FileSet


def str_to_type(type_str: str) -> type:
    """Resolve a string representation of a type into a valid type"""
    if "/" in type_str:
        tp = DataType.from_mime(type_str)
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
            if tp_or_str.startswith("union:"):
                union_tps = tuple(
                    str_to_type(p) for p in tp_or_str[len("union:") :].split(",")
                )
                tp: ty.Type[ty.Union] = ty.Union.__getitem__(union_tps)  # type: ignore
            else:
                tp = str_to_type(tp_or_str)
        converted[name] = tp
    return converted


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
class TestsGenerator:
    """Specifications for the automatically generated test for the generated Nipype spec

    Parameters
    ----------
    inputs : dict[str, str], optional
        values to provide to specific inputs fields (if not provided, a sensible value
        within the valid range will be provided)
    outputs: dict[str, str], optional
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
    expected_outputs: ty.Dict[str, str] = attrs.field(
        factory=dict, converter=default_if_none(factory=dict),  # type: ignore
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
        }
    )
    xfail: bool = attrs.field(
        default=True,
        metadata={
            "help": """whether the unittest is expected to fail or not. Set to false
                when you are satisfied with the edits you have made to this file"""}
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
    """

    cmdline: str = attrs.field(metadata={"help": "the expected cmdline output"})
    inputs: ty.Dict[str, str] = attrs.field(
        factory=dict,
        metadata={
            "help": """name-value pairs for inputs to be provided to the doctest.
                If the field is of file-format type and the value is None, then the
                '.mock()' method of the corresponding class is used instead."""}
    )


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


def from_dict_to_inputs(obj: ty.Union[InputsConverter, dict]) -> InputsConverter:
    return from_dict_converter(obj, InputsConverter)


def from_dict_to_outputs(obj: ty.Union[OutputsConverter, dict]) -> OutputsConverter:
    return from_dict_converter(obj, OutputsConverter)


def from_dict_to_test(obj: ty.Union[TestsGenerator, dict]) -> TestsGenerator:
    return from_dict_converter(obj, TestsGenerator)


def from_dict_to_doctest(obj: ty.Union[DocTestGenerator, dict]) -> DocTestGenerator:
    converted = from_dict_converter(obj, DocTestGenerator, allow_none=True)
    if converted.inputs is None:
        converted = None
    return converted


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
    test: TestsGenerator or dict, optional
        specficiations for how to construct the test. A default test is generated if no
        specs are provided
    doctest: DocTestGenerator or dict, optional
        specifications for how to construct the docttest. Doctest is omitted if not
        provided
    callables_module: ModuleType or str, optional
        a module, or path to a module, containing any required callables
    """

    name: str
    nipype_module: ModuleType = attrs.field(converter=import_module_from_path)
    output_module: str = attrs.field(default=None)
    new_name: str = attrs.field(default=None)
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
    test: TestsGenerator = attrs.field(  # type: ignore
        factory=TestsGenerator, converter=from_dict_to_test
    )
    doctest: ty.Optional[DocTestGenerator] = attrs.field(
        default=None, converter=from_dict_to_doctest
    )

    def __attrs_post_init__(self):
        if self.output_module is None:
            if self.nipype_module.__name__.startswith("nipype.interfaces."):
                self.output_module = (
                    "pydra.tasks."
                    + self.nipype_module.__name__[len("nipype.interfaces.") :]
                    + "."
                    + self.task_name.lower()
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
        return getattr(self.nipype_module, self.new_name)

    @property
    def nipype_input_spec(self) -> nipype.interfaces.base.BaseInterfaceInputSpec:
        return self.nipype_interface.input_spec()

    @property
    def nipype_output_spec(self) -> nipype.interfaces.base.BaseTraitedSpec:
        return self.nipype_interface.output_spec()

    @property
    def task_name(self):
        return self.new_name if self.new_name is not None else self.name

    def generate(self, package_root: Path):
        """creating pydra input/output spec from nipype specs
        if write is True, a pydra Task class will be written to the file together with tests
        """
        input_fields, inp_templates = self.convert_input_fields()
        output_fields = self.convert_output_spec(fields_from_template=inp_templates)

        nonstd_types = set(
            f[1]
            for f in input_fields
            if f[1].__module__ not in ["builtins", "pathlib", "typing"]
        )

        output_file = (
            Path(package_root)
            .joinpath(*self.output_module.split("."))
            .with_suffix(".py")
        )
        testdir = output_file.parent / "tests"
        testdir.mkdir(parents=True)

        self.write_task(
            output_file,
            input_fields=input_fields,
            output_fields=output_fields,
            nonstd_types=nonstd_types,
        )

        filename_test = testdir / f"test_{self.task_name.lower()}.py"
        # filename_test_run = testdir / f"test_run_{self.task_name.lower()}.py"
        self.write_test(
            filename_test,
            input_fields=input_fields,
            nonstd_types=nonstd_types,
        )
        # self.write_test(filename_test=filename_test_run, run=True)

    def convert_input_fields(self):
        """creating fields list for pydra input spec"""
        fields_pdr_dict = {}
        position_dict = {}
        has_template = []
        for name, fld in self.nipype_input_spec.traits().items():
            if name in self.TRAITS_IRREL:
                continue
            if name in self.inputs.omit:
                continue
            fld_pdr, pos = self.pydra_fld_input(fld, name)
            meta_pdr = fld_pdr[-1]
            if "output_file_template" in meta_pdr:
                has_template.append(name)
            fields_pdr_dict[name] = (name,) + fld_pdr
            if pos is not None:
                position_dict[name] = pos

        fields_pdr_l = list(fields_pdr_dict.values())
        return fields_pdr_l, has_template

    def pydra_fld_input(self, field, nm):
        """converting a single nipype field to one element of fields for pydra input_spec"""
        tp_pdr = self.pydra_type_converter(field, spec_type="input", name=nm)
        if nm in self.inputs.metadata:
            metadata_extra_spec = self.inputs.metadata[nm]
        else:
            metadata_extra_spec = {}

        if "default" in metadata_extra_spec:
            default_pdr = metadata_extra_spec.pop("default")
        elif (
            getattr(field, "usedefault")
            and field.default is not traits.ctrait.Undefined
        ):
            default_pdr = field.default
        else:
            default_pdr = None

        metadata_pdr = {"help_string": ""}
        for key in self.INPUT_KEYS:
            key_nm_pdr = self.NAME_MAPPING.get(key, key)
            val = getattr(field, key)
            if val is not None:
                if key == "argstr" and "%" in val:
                    val = self.string_formats(argstr=val, name=nm)
                metadata_pdr[key_nm_pdr] = val

        if getattr(field, "name_template"):
            template = getattr(field, "name_template")
            name_source = ensure_list(getattr(field, "name_source"))

            metadata_pdr["output_file_template"] = self.string_formats(
                argstr=template, name=name_source[0]
            )
            if tp_pdr in [specs.File, specs.Directory]:
                tp_pdr = str
        elif getattr(field, "genfile"):
            if nm in self.outputs.templates:
                try:
                    metadata_pdr["output_file_template"] = self.outputs.templates[nm]
                except KeyError:
                    raise Exception(
                        f"{nm} is has genfile=True and therefore needs an 'output_file_template' value"
                    )
                if tp_pdr in [
                    specs.File,
                    specs.Directory,
                ]:  # since this is a template, the file doesn't exist
                    tp_pdr = Path
            elif nm not in self.outputs.callables:
                raise Exception(
                    f"the filed {nm} has genfile=True, but no output template or callables_module provided"
                )

        metadata_pdr.update(metadata_extra_spec)

        pos = metadata_pdr.get("position", None)

        if default_pdr is not None and not metadata_pdr.get("mandatory", None):
            return (tp_pdr, default_pdr, metadata_pdr), pos
        else:
            return (tp_pdr, metadata_pdr), pos

    def convert_output_spec(self, fields_from_template):
        """creating fields list for pydra input spec"""
        fields_pdr_l = []
        for name, fld in self.nipype_output_spec.traits().items():
            if name in self.outputs.requirements and name not in fields_from_template:
                fld_pdr = self.pydra_fld_output(fld, name)
                fields_pdr_l.append((name,) + fld_pdr)
        return fields_pdr_l

    def pydra_fld_output(self, field, name):
        """converting a single nipype field to one element of fields for pydra output_spec"""
        tp_pdr = self.pydra_type_converter(field, spec_type="output", name=name)

        metadata_pdr = {}
        for key in self.OUTPUT_KEYS:
            key_nm_pdr = self.NAME_MAPPING.get(key, key)
            val = getattr(field, key)
            if val:
                metadata_pdr[key_nm_pdr] = val

        if self.outputs.requirements[name]:
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

            metadata_pdr["requires"] = []
            for requires in requires_l:
                requires_mod = []
                for el in requires:
                    if isinstance(el, str):
                        requires_mod.append(el)
                    elif isinstance(el, dict):
                        requires_mod += list(el.items())
                metadata_pdr["requires"].append(requires_mod)
            if nested_flag is False:
                metadata_pdr["requires"] = metadata_pdr["requires"][0]

        if name in self.outputs.templates:
            metadata_pdr["output_file_template"] = self.interface_spec[
                "output_templates"
            ][name]
        elif name in self.outputs.callables:
            metadata_pdr["callable"] = self.outputs.callables[name]
        return (tp_pdr, metadata_pdr)

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
        types_dict = self.inputs.types if spec_type == "inputs" else self.outputs.types
        try:
            return types_dict[name]
        except KeyError:
            pass
        tp = field.trait_type
        if isinstance(tp, traits.trait_types.Int):
            tp_pdr = int
        elif isinstance(tp, traits.trait_types.Float):
            tp_pdr = float
        elif isinstance(tp, traits.trait_types.Str):
            tp_pdr = str
        elif isinstance(tp, traits.trait_types.Bool):
            tp_pdr = bool
        elif isinstance(tp, traits.trait_types.Dict):
            tp_pdr = dict
        elif isinstance(tp, traits_extension.InputMultiObject):
            if isinstance(field.inner_traits[0].trait_type, traits_extension.File):
                tp_pdr = specs.MultiInputFile
            else:
                tp_pdr = specs.MultiInputObj
        elif isinstance(tp, traits_extension.OutputMultiObject):
            if isinstance(field.inner_traits[0].trait_type, traits_extension.File):
                tp_pdr = specs.MultiOutputFile
            else:
                tp_pdr = specs.MultiOutputObj
        elif isinstance(tp, traits.trait_types.List):
            if isinstance(field.inner_traits[0].trait_type, traits_extension.File):
                if spec_type == "input":
                    tp_pdr = specs.MultiInputFile
                else:
                    tp_pdr = specs.MultiOutputFile
            else:
                tp_pdr = list
        elif isinstance(tp, traits_extension.File):
            if (
                spec_type == "output" or tp.exists is True
            ):  # TODO check the hash_file metadata in nipype
                tp_pdr = specs.File
            else:
                tp_pdr = Path
        else:
            tp_pdr = ty.Any
        return tp_pdr

    def string_formats(self, argstr, name):
        import re

        if "%s" in argstr:
            argstr_new = argstr.replace("%s", f"{{{name}}}")
        elif "%d" in argstr:
            argstr_new = argstr.replace("%d", f"{{{name}}}")
        elif "%f" in argstr:
            argstr_new = argstr.replace("%f", f"{{{name}}}")
        elif "%g" in argstr:
            argstr_new = argstr.replace("%g", f"{{{name}}}")
        elif len(re.findall("%[0-9.]+f", argstr)) == 1:
            old_format = re.findall("%[0-9.]+f", argstr)[0]
            argstr_new = argstr.replace(old_format, f"{{{name}:{old_format[1:]}}}")
        else:
            raise Exception(f"format from {argstr} is not supported TODO")
        return argstr_new

    def write_task(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        def types_to_names(spec_fields):
            spec_fields_str = []
            for el in spec_fields:
                el = list(el)
                try:
                    el[1] = el[1].__name__
                    # add 'TYPE_' to the beginning of the name
                    el[1] = "TYPE_" + el[1]
                except AttributeError:
                    el[1] = el[1]._name
                    # add 'TYPE_' to the beginning of the name
                    el[1] = "TYPE_" + el[1]
                spec_fields_str.append(tuple(el))
            return spec_fields_str

        input_fields_str = types_to_names(spec_fields=input_fields)
        output_fields_str = types_to_names(spec_fields=output_fields)
        functions_str = self.function_callables()
        spec_str = (
            "from pydra.engine import specs \nfrom pydra import ShellCommandTask \n"
        )
        spec_str += self.import_types(nonstd_types)
        spec_str += functions_str
        spec_str += f"input_fields = {input_fields_str}\n"
        spec_str += f"{self.task_name}_input_spec = specs.SpecInfo(name='Input', fields=input_fields, bases=(specs.ShellSpec,))\n\n"
        spec_str += f"output_fields = {output_fields_str}\n"
        spec_str += f"{self.task_name}_output_spec = specs.SpecInfo(name='Output', fields=output_fields, bases=(specs.ShellOutSpec,))\n\n"
        spec_str += f"class {self.task_name}(ShellCommandTask):\n"
        if self.doctest is not None:
            spec_str += self.create_doctest(
                input_fields=input_fields, nonstd_types=nonstd_types
            )
        spec_str += f"    input_spec = {self.task_name}_input_spec\n"
        spec_str += f"    output_spec = {self.task_name}_output_spec\n"
        spec_str += f"    executable='{self.nipype_interface._cmd}'\n"

        for tp_repl in self.TYPE_REPLACE:
            spec_str = spec_str.replace(*tp_repl)

        spec_str_black = black.format_file_contents(
            spec_str, fast=False, mode=black.FileMode()
        )

        with open(filename, "w") as f:
            f.write(spec_str_black)

    @staticmethod
    def import_types(nonstd_types: ty.List[type], prefix="") -> str:
        imports = "import typing as ty\nfrom pathlib import Path\n"
        for tp in nonstd_types:
            imports += f"{prefix}from {tp.__module__} import {tp.__name__}\n"
        return imports

    def write_test(self, filename_test, input_fields, nonstd_types, run=False):
        spec_str = "import os, pytest \n"
        spec_str += self.import_types(nonstd_types=nonstd_types)
        spec_str += f"from {self.output_module} import {self.task_name}\n"
        spec_str += "\n"
        if self.test.xfail:
            spec_str += "@pytest.mark.xfail\n"
        spec_str += f"@pytest.mark.timeout_pass(timeout={self.test.timeout})\n"
        spec_str += f"def test_{self.task_name.lower()}():\n"
        spec_str += f"    task = {self.task_name}()\n"
        for field in input_fields:
            nm, tp = field[:2]
            # Try to get a sensible value for the traits value
            try:
                value = self.test.inputs[nm]
            except KeyError:
                if len(field) == 4:  # field has default
                    value = field[2]
                else:
                    assert len(field) == 3
                    if inspect.isclass(tp) and issubclass(tp, FileSet):
                        value = f"{tp.__name__}.sample()"
                    else:
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
        spec_str += "    res = task()\n"
        spec_str += "    print('RESULT: ', res)\n"
        for name, value in self.test.expected_outputs.items():
            spec_str += f"    assert res.output.{name} == {value}\n"

        spec_str_black = black.format_file_contents(
            spec_str, fast=False, mode=black.FileMode()
        )

        with open(filename_test, "w") as f:
            f.write(spec_str_black)

    def create_doctest(self, input_fields, nonstd_types):
        """adding doctests to the interfaces"""
        doctest = '    """\n    Example\n    -------\n'
        doctest += self.import_types(nonstd_types, prefix="    >>> ")
        doctest += f"    >>> task = {self.task_name}()\n"
        for field in input_fields:
            nm, tp = field[:2]
            try:
                val = self.doctest.inputs[nm]
            except KeyError:
                if inspect.isclass(tp) and issubclass(tp, FileSet):
                    val = f"{tp.__name__}.mock()"
                else:
                    val = attrs.NOTHING
            else:
                if type(val) is str:
                    val = f'"{val}"'
            if val is not attrs.NOTHING:
                doctest += f"    >>> task.inputs.{nm} = {val}\n"
        doctest += "    >>> task.cmdline\n"
        doctest += f"    '{self.doctest.cmdline}'"
        doctest += '\n    """\n'
        return doctest

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

    TYPE_REPLACE = [
        ("'TYPE_File'", "specs.File"),
        ("'TYPE_bool'", "bool"),
        ("'TYPE_str'", "str"),
        ("'TYPE_Any'", "ty.Any"),
        ("'TYPE_int'", "int"),
        ("'TYPE_float'", "float"),
        ("'TYPE_list'", "list"),
        ("'TYPE_dict'", "dict"),
        ("'TYPE_MultiInputObj'", "specs.MultiInputObj"),
        ("'TYPE_MultiOutputObj'", "specs.MultiOutputObj"),
        ("'TYPE_MultiInputFile'", "specs.MultiInputFile"),
        ("'TYPE_MultiOutputFile'", "specs.MultiOutputFile"),
    ]
