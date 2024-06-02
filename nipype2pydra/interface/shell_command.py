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
    find_super_method,
)
from fileformats.core.mixin import WithClassifiers
from fileformats.generic import File, Directory


logger = logging.getLogger("nipype2pydra")

CALLABLES_ARGS = ["inputs", "stdout", "stderr", "output_dir"]


@attrs.define(slots=False)
class ShellCommandInterfaceConverter(BaseInterfaceConverter):

    _format_argstrs: ty.Dict[str, str] = attrs.field(factory=dict)

    @cached_property
    def included_methods(self) -> ty.Tuple[str, ...]:
        included = []
        if not self.method_omitted("_parse_inputs"):
            included.append("_parse_inputs"),
        if not self.method_omitted("_format_arg"):
            included.append("_format_arg")
        if not self.method_omitted("_gen_filename"):
            included.append("_gen_filename")
        if self.callable_output_fields:
            if not self.method_omitted("aggregate_outputs"):
                included.append("aggregate_outputs")
            if not self.method_omitted("_list_outputs"):
                included.append("_list_outputs")
        return tuple(included)

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
            if m.__name__ in self.included_methods:
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
            ]
            + list(self.referenced_methods),
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
                self._format_argstrs[field[0]] = field[-1].pop("argstr", "")
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

    @property
    def callable_output_field_names(self):
        return [f[0] for f in self.callable_output_fields]

    @cached_property
    def _format_arg_body(self):
        if self.method_omitted("_format_arg"):
            return ""
        return _strip_doc_string(
            inspect.getsource(self.nipype_interface._format_arg).split("\n", 1)[-1]
        )

    @cached_property
    def _gen_filename_body(self):
        if self.method_omitted("_gen_filename"):
            return ""
        return _strip_doc_string(
            inspect.getsource(self.nipype_interface._gen_filename).split("\n", 1)[-1]
        )

    @property
    def format_arg_code(self):
        if "_format_arg" not in self.included_methods:
            return ""
        body = self._format_arg_body
        body = self._process_inputs(body)
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
                r"^    return super\((\w+,\s*self)?\)\._format_arg\("
                + ", ".join(existing_args)
                + r"\)\n"
            ),
            "return argstr.format(**inputs)",
            body,
            flags=re.MULTILINE,
        )
        if not body:
            return ""
        body = self.unwrap_nested_methods(body, inputs_as_dict=True)
        body = self.replace_supers(
            body,
            super_base=find_super_method(
                self.nipype_interface, "_format_arg", include_class=True
            )[1],
        )
        # body = self._misc_cleanups(body)
        code_str = f"""def _format_arg({name_arg}, {val_arg}, inputs, argstr):{self.parse_inputs_call}
    if {val_arg} is None:
        return ""
{body}"""

        if not code_str.rstrip().endswith("return argstr.format(**inputs)"):
            code_str += "\n    return argstr.format(**inputs)"

        code_str += "\n\n"

        for field_name in self.formatted_input_field_names:
            code_str += (
                f"def {field_name}_formatter(field, inputs):\n"
                f"    return _format_arg({field_name!r}, field, inputs, "
                f"argstr={self._format_argstrs[field_name]!r})\n\n\n"
            )
        return code_str

    @property
    def parse_inputs_code(self) -> str:
        if "_parse_inputs" not in self.included_methods:
            return ""
        body = _strip_doc_string(
            inspect.getsource(self.nipype_interface._parse_inputs).split("\n", 1)[-1]
        )
        body = self._process_inputs(body)
        body = re.sub(
            r"self.\_format_arg\((\w+), (\w+), (\w+)\)",
            r"_format_arg(\1, \3, inputs, parsed_inputs, argstrs.get(\1))",
            body,
        )

        # Strip out return value
        body = re.sub(r"\s*return .*\n", "", body)
        if not body:
            return ""
        body = self.unwrap_nested_methods(body, inputs_as_dict=True)
        body = self.replace_supers(
            body,
            super_base=find_super_method(
                self.nipype_interface, "_parse_inputs", include_class=True
            )[1],
        )
        # body = self._misc_cleanups(body)

        code_str = "def _parse_inputs(inputs):\n    parsed_inputs = {}"
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
        if "_gen_filename" not in self.included_methods:
            return ""

        body = _strip_doc_string(
            inspect.getsource(self.nipype_interface._gen_filename).split("\n", 1)[-1]
        )
        body = self._process_inputs(body)

        if not body:
            return ""
        body = self.unwrap_nested_methods(body, inputs_as_dict=True)
        body = self.replace_supers(
            body,
            super_base=find_super_method(
                self.nipype_interface, "_gen_filename", include_class=True
            )[1],
        )
        # body = self._misc_cleanups(body)

        code_str = f"""def _gen_filename(name, inputs):{self.parse_inputs_call}
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
        code_str = ""
        if "aggregate_outputs" in self.included_methods:
            func_name = "aggregate_outputs"
            agg_body = _strip_doc_string(
                inspect.getsource(self.nipype_interface.aggregate_outputs).split(
                    "\n", 1
                )[-1]
            )
            need_list_outputs = bool(re.findall(r"\b_list_outputs\b", agg_body))
            agg_body = self._process_inputs(agg_body)

            if not agg_body:
                return ""
            agg_body = self.unwrap_nested_methods(
                agg_body, additional_args=CALLABLES_ARGS, inputs_as_dict=True
            )
            agg_body = self.replace_supers(
                agg_body,
                super_base=find_super_method(
                    self.nipype_interface, "aggregate_outputs", include_class=True
                )[1],
            )

            code_str += f"""def aggregate_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    inputs = attrs.asdict(inputs){self.parse_inputs_call}
    needed_outputs = {self.callable_output_field_names!r}
{agg_body}


"""
            inputs_as_dict_call = ""

        else:
            func_name = "_list_outputs"
            inputs_as_dict_call = "\n    inputs = attrs.asdict(inputs)"
            need_list_outputs = True

        if need_list_outputs:
            if "_list_outputs" not in self.included_methods:
                assert self.callable_output_fields
                # Need to reimplemt the base _list_outputs method in Pydra, which maps
                # inputs with 'output_name' to outputs
                for f in self.callable_output_fields:
                    output_name = f[0]
                    code_str += f"\n\n\ndef {output_name}_callable(output_dir, inputs, stdout, stderr):\n"
                    try:
                        input_name = self._output_name_mappings[output_name]
                    except KeyError:
                        logger.warning(
                            "Could not find input name with 'output_name' for "
                            "%s output, attempting to create something that can be worked "
                            "with",
                            output_name,
                        )
                        if "_parse_inputs" in self.included_methods:
                            code_str += (
                                f"    parsed_inputs = _parse_inputs(inputs)\n"
                                f"    return parsed_inputs.get('{output_name}', attrs.NOTHING)\n"
                            )
                        else:
                            code_str += "    raise NotImplementedError\n"

                    else:
                        code_str += f"    return inputs.{input_name}\n"

                return code_str
            else:
                lo_body = _strip_doc_string(
                    inspect.getsource(self.nipype_interface._list_outputs).split(
                        "\n", 1
                    )[-1]
                )
                lo_body = self._process_inputs(lo_body)

                if not lo_body:
                    return ""
                lo_body = self.unwrap_nested_methods(
                    lo_body, additional_args=CALLABLES_ARGS, inputs_as_dict=True
                )
                lo_body = self.replace_supers(
                    lo_body,
                    super_base=find_super_method(
                        self.nipype_interface, "_list_outputs", include_class=True
                    )[1],
                )

                code_str += f"""def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):{inputs_as_dict_call}{self.parse_inputs_call}
{lo_body}


"""
        # Create separate function for each output field in the "callables" section
        for output_field in self.callable_output_fields:
            output_name = output_field[0]
            code_str += (
                f"\n\n\ndef {output_name}_callable(output_dir, inputs, stdout, stderr):\n"
                f"    outputs = {func_name}(output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr)\n"
                '    return outputs.get("' + output_name + '", attrs.NOTHING)\n\n'
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
        body = re.sub(r"self\.(?!inputs)(\w+)\b(?!\()", r"parsed_inputs['\1']", body)
        return body

    @property
    def parse_inputs_call(self):
        if not self.parse_inputs_code:
            return ""
        return "\n    parsed_inputs = _parse_inputs(inputs) if inputs else {}"

    def method_omitted(self, method_name: str) -> bool:
        return self.package.is_omitted(
            find_super_method(self.nipype_interface, method_name, include_class=True)[1]
        )


def _strip_doc_string(body: str) -> str:
    if re.match(r"\s*(\"|')", body):
        body = "\n".join(split_source_into_statements(body)[1:])
    return body
