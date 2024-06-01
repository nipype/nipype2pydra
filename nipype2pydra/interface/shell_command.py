import re
import typing as ty
import attrs
import inspect
import logging
from functools import cached_property
from copy import copy
from operator import attrgetter, itemgetter
from importlib import import_module
from nipype.interfaces.base import BaseInterface, TraitedSpec
from .base import BaseInterfaceConverter
from ..utils import (
    UsedSymbols,
    split_source_into_statements,
    INBUILT_NIPYPE_TRAIT_NAMES,
)
from fileformats.core.mixin import WithClassifiers
from fileformats.generic import File, Directory


logger = logging.getLogger("nipype2pydra")

CALLABLES_ARGS = ["inputs", "stdout", "stderr", "output_dir"]


@attrs.define(slots=False)
class ShellCommandInterfaceConverter(BaseInterfaceConverter):

    _format_argstrs: ty.Dict[str, str] = attrs.field(factory=dict)

    INCLUDED_METHODS = (
        "_parse_inputs",
        "_format_arg",
        "_list_outputs",
        "_gen_filename",
    )

    def generate_code(self, input_fields, nonstd_types, output_fields) -> ty.Tuple[
        str,
        UsedSymbols,
    ]:
        """
        Returns
        -------
        converted_code : str
            the core converted code for the task
        used_symbols: UsedSymbols
            symbols used in the code
        """

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
                    f"Could not find executable for {self.nipype_interface}, "
                    "try the FunctionInterfaceConverter class instead"
                )

        def unwrap_field_type(t):
            if issubclass(t, WithClassifiers) and t.is_classified:
                unwraped_classifiers = ", ".join(
                    unwrap_field_type(c) for c in t.classifiers
                )
                return f"{t.unclassified.__name__}[{unwraped_classifiers}]"
            return t.__name__

        nonstd_types = copy(nonstd_types)

        def types_to_names(spec_fields):
            spec_fields_str = []
            for el in spec_fields:
                el = list(el)
                field_type = el[1]
                if inspect.isclass(field_type) and issubclass(
                    field_type, WithClassifiers
                ):
                    field_type_str = unwrap_field_type(field_type)
                else:
                    field_type_str = str(field_type)
                    if field_type_str.startswith("<class "):
                        field_type_str = el[1].__name__
                    else:
                        # Alter modules in type string to match those that will be imported
                        field_type_str = field_type_str.replace("typing", "ty")
                        field_type_str = re.sub(
                            r"(\w+\.)+(?<!ty\.)(\w+)", r"\2", field_type_str
                        )
                if field_type_str == "File":
                    nonstd_types.add(File)
                elif field_type_str == "Directory":
                    nonstd_types.add(Directory)
                el[1] = "#" + field_type_str + "#"
                spec_fields_str.append(tuple(el))
            return spec_fields_str

        input_names = [i[0] for i in input_fields]
        output_names = [o[0] for o in output_fields]
        input_fields_str = str(types_to_names(spec_fields=input_fields))
        input_fields_str = re.sub(
            r"'formatter': '(\w+)'", r"'formatter': \1", input_fields_str
        )
        output_fields_str = str(types_to_names(spec_fields=output_fields))
        output_fields_str = re.sub(
            r"'callable': '(\w+)'", r"'callable': \1", output_fields_str
        )
        # functions_str = self.function_callables()
        # functions_imports, functions_str = functions_str.split("\n\n", 1)
        # spec_str = functions_str
        spec_str = (
            self.format_arg_code
            + self.parse_inputs_code
            + self.callables_code
            + self.defaults_code
        )
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

        for m in sorted(self.referenced_methods, key=attrgetter("__name__")):
            if m.__name__ in self.INCLUDED_METHODS:
                continue
            if self.method_stacks[m.__name__][0] == self.nipype_interface._list_outputs:
                additional_args = CALLABLES_ARGS
            else:
                additional_args = []
            spec_str += "\n\n" + self.process_method(
                m, input_names, output_names, additional_args=additional_args
            )

        for new_name, (m, _) in sorted(
            self.referenced_supers.items(), key=itemgetter(0)
        ):
            if self.method_stacks[new_name][0] == self.nipype_interface._list_outputs:
                additional_args = CALLABLES_ARGS
            else:
                additional_args = []
            spec_str += "\n\n" + self.process_method(
                m,
                input_names,
                output_names,
                additional_args=additional_args,
                new_name=new_name,
            )

        used = UsedSymbols.find(
            self.nipype_module,
            [
                self.format_arg_code,
                self.parse_inputs_code,
                self.callables_code,
                self.defaults_code,
            ],
            omit_classes=self.package.omit_classes + [BaseInterface, TraitedSpec],
            omit_modules=self.package.omit_modules,
            omit_functions=self.package.omit_functions,
            omit_constants=self.package.omit_constants,
            always_include=self.package.all_explicit,
            translations=self.package.all_import_translations,
            absolute_imports=True,
        )
        for super_method, base in self.referenced_supers.values():
            super_used = UsedSymbols.find(
                import_module(base.__module__),
                [super_method],
                omit_classes=self.package.omit_classes + [BaseInterface, TraitedSpec],
                omit_modules=self.package.omit_modules,
                omit_functions=self.package.omit_functions,
                omit_constants=self.package.omit_constants,
                always_include=self.package.all_explicit,
                translations=self.package.all_import_translations,
                absolute_imports=True,
                collapse_intra_pkg=True,
            )
            used.update(super_used)

        used.imports.update(
            self.construct_imports(
                nonstd_types,
                spec_str,
                include_task=False,
                base=base_imports,
            )
        )

        return spec_str, used

    @cached_property
    def input_fields(self):
        input_fields = super().input_fields
        for field in input_fields:
            if field[0] in self.formatted_input_field_names:
                field[-1]["formatter"] = f"{field[0]}_formatter"
                self._format_argstrs[field[0]] = field[-1].pop("argstr")
        return input_fields

    @cached_property
    def output_fields(self):
        output_fields = super().output_fields
        for field in self.callable_output_fields:
            field[-1]["callable"] = f"{field[0]}_callable"
        return output_fields

    @property
    def formatted_input_field_names(self):
        return re.findall(r"name == \"(\w+)\"", self._format_arg_body)

    @property
    def callable_default_input_field_names(self):
        return re.findall(r"name == \"(\w+)\"", self._gen_filename_body)

    @property
    def callable_output_fields(self):
        return [
            f
            for f in super().output_fields
            if (
                "output_file_template" not in f[-1]
                and f[0] not in INBUILT_NIPYPE_TRAIT_NAMES
            )
        ]

    @cached_property
    def _format_arg_body(self):
        if "_format_arg" not in self.nipype_interface.__dict__:
            return ""
        return _strip_doc_string(
            inspect.getsource(self.nipype_interface._format_arg).split("\n", 1)[-1]
        )

    @cached_property
    def _gen_filename_body(self):
        if "_gen_filename" not in self.nipype_interface.__dict__:
            return ""
        return _strip_doc_string(
            inspect.getsource(self.nipype_interface._gen_filename).split("\n", 1)[-1]
        )

    @property
    def format_arg_code(self):
        if not self._format_arg_body:
            return ""
        body = self._format_arg_body
        body = self._process_inputs(body)
        body = self._misc_cleanups(body)
        existing_args = list(
            inspect.signature(self.nipype_interface._format_arg).parameters
        )[1:]
        name_arg, _, val_arg = existing_args
        body = re.sub(
            r"trait_spec\.argstr % (.*)",
            r"argstr.format(**{" + name_arg + r": \1})",
            body,
        )

        # Strip out return value
        body = re.sub(
            (
                r"\s*return super\((\w+,\s*self)?\)\._format_arg\("
                + ", ".join(existing_args)
                + r"\)\n"
            ),
            "",
            body,
        )
        if not body:
            return ""
        body = self.unwrap_nested_methods(body)
        body = self.replace_supers(body)

        code_str = f"""def _format_arg({name_arg}, {val_arg}, inputs, argstr):
    parsed_inputs = _parse_inputs(inputs) if inputs else {{}}
    if {val_arg} is None:
        return ""
{body}


"""
        for field_name in self.formatted_input_field_names:
            code_str += (
                f"def {field_name}_formatter(field, inputs):\n"
                f"    return _format_arg({field_name!r}, field, inputs, "
                f"argstr={self._format_argstrs[field_name]!r})\n\n\n"
            )
        return code_str

    @property
    def parse_inputs_code(self) -> str:
        if "_parse_inputs" not in self.nipype_interface.__dict__:
            return ""
        body = _strip_doc_string(
            inspect.getsource(self.nipype_interface._parse_inputs).split("\n", 1)[-1]
        )
        body = self._process_inputs(body)
        body = self._misc_cleanups(body)
        body = re.sub(
            r"self.\_format_arg\((\w+), (\w+), (\w+)\)",
            r"_format_arg(\1, \3, inputs, parsed_inputs, argstrs.get(\1))",
            body,
        )

        # Strip out return value
        body = re.sub(r"\s*return .*\n", "", body)
        body = self.unwrap_nested_methods(body)
        body = self.replace_supers(body)

        code_str = "def _parse_inputs(inputs):\n    parsed_inputs = {{}}"
        if re.findall(r"\bargstrs\b", body):
            code_str += f"\n    argstrs = {self._format_argstrs!r}"
        code_str += f"""
    skip = []
{body}
    return parsed_inputs


"""
        return code_str

    @cached_property
    def defaults_code(self):
        if not self.callable_default_input_field_names:
            return ""

        body = _strip_doc_string(
            inspect.getsource(self.nipype_interface._gen_filename).split("\n", 1)[-1]
        )
        body = self._process_inputs(body)
        body = self._misc_cleanups(body)

        if not body:
            return ""
        body = self.unwrap_nested_methods(body)
        body = self.replace_supers(body)

        code_str = f"""def _gen_filename(name, inputs):
    parsed_inputs = _parse_inputs(inputs) if inputs else {{}}
{body}
"""
        # Create separate default function for each input field with genfile, which
        # reference the magic "_gen_filename" method
        for inpt_name, inpt in sorted(
            self.nipype_interface.input_spec().traits().items()
        ):
            if inpt.genfile:
                code_str += (
                    f"\n\n\ndef {inpt_name}_default(inputs):\n"
                    f'    return _gen_filename("{inpt_name}", inputs=inputs)\n\n'
                )
        return code_str

    @cached_property
    def callables_code(self):

        if not self.callable_output_fields:
            return ""

        body = _strip_doc_string(
            inspect.getsource(self.nipype_interface._list_outputs).split("\n", 1)[-1]
        )
        body = self._process_inputs(body)
        body = self._misc_cleanups(body)

        if not body:
            return ""
        body = self.unwrap_nested_methods(
            body,
            additional_args=CALLABLES_ARGS,
        )
        body = self.replace_supers(body)

        code_str = f"""def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    parsed_inputs = _parse_inputs(inputs) if inputs else {{}}
{body}
"""
        # Create separate function for each output field in the "callables" section
        for output_field in self.callable_output_fields:
            output_name = output_field[0]
            code_str += (
                f"\n\n\ndef {output_name}_callable(output_dir, inputs, stdout, stderr):\n"
                "    outputs = _list_outputs(output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr)\n"
                '    return outputs["' + output_name + '"]\n\n'
            )
        return code_str

    def _process_inputs(self, body: str) -> str:
        # Replace self.inputs.<name> with <name> in the function body
        input_re = re.compile(r"self\.inputs\.(\w+)\b(?!\()")
        unrecognised_inputs = set(
            m for m in input_re.findall(body) if m not in self.input_names
        )
        if unrecognised_inputs:
            logger.warning(
                "Found the following unrecognised (potentially dynamic) inputs %s in "
                "'%s' task",
                unrecognised_inputs,
                self.task_name,
            )
        body = input_re.sub(r"inputs['\1']", body)
        body = re.sub(r"self\.(?!inputs)(\w+)", r"parsed_inputs['\1']", body)
        return body


def _strip_doc_string(body: str) -> str:
    if re.match(r"\s*(\"|')", body):
        body = "\n".join(split_source_into_statements(body)[1:])
    return body
