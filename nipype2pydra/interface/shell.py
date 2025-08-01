import re
import typing as ty
import attrs
import inspect
import logging
from functools import cached_property
from copy import copy
from operator import attrgetter
from .base import BaseInterfaceConverter
from ..utils import (
    split_source_into_statements,
    INBUILT_NIPYPE_TRAIT_NAMES,
    extract_args,
    find_super_method,
    cleanup_function_body,
    type_to_str,
)
from fileformats.core.mixin import WithClassifiers
from fileformats.generic import File
from pydra.utils.typing import is_optional


logger = logging.getLogger("nipype2pydra")

OUT_FUNC_ARGS = ["callable", "formatter"]  # arguments to shell.out that are functions
CALLABLE_ARGS = [
    "inputs",
    "stdout",
    "stderr",
    "output_dir",
]  # Arguments for callable methods


@attrs.define(slots=False)
class ShellInterfaceConverter(BaseInterfaceConverter):

    converter_type = "shell_command"
    _format_argstrs: ty.Dict[str, str] = attrs.field(factory=dict)

    @cached_property
    def included_methods(self) -> ty.Tuple[str, ...]:
        included = []
        # if not self.method_omitted("__init__"):
        #     included.append("__init__"),
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

    def generate_code(self, input_fields, nonstd_types, output_fields) -> str:
        """
        Parameters
        ----------
        input_fields : list[tuple[str, type, dict] | tuple[str, type, object, dict]]
            list of input fields, each field is a tuple of (name, type, metadata) or
            (name, type, default, metadata)
        nonstd_types : set[type]
            set of non-standard types
        output_fields : list[tuple[str, type, dict]]
            list of output fields, each field is a tuple of (name, type, metadata)

        Returns
        -------
        converted_code : str
            the core converted code for the task
        used: UsedSymbols
            symbols used in the code
        """

        base_imports = [
            "import os",
            "from pydra.compose import shell",
        ]

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

        nonstd_types = copy(nonstd_types)

        input_names = [i[0] for i in input_fields]
        output_names = [o[0] for o in output_fields]

        # Pull out xor fields into task-level xor_sets
        xor_sets = set()
        has_zero_pos = False
        for inpt in input_fields:
            if len(inpt) == 3:
                name, _, mdata = inpt
            else:
                name, _, __, mdata = inpt
            if "xor" in mdata:
                xor_sets.add(
                    frozenset(
                        list(
                            mdata["xor"]
                            if not isinstance(mdata["xor"], str)
                            else [mdata["xor"]]
                        )
                        + [name]
                    )
                )
            pos = mdata.get("position", None)
            if isinstance(pos, str):
                # convert string reprs (I think a mistake) to ints
                pos = mdata["position"] = int(pos)
            if pos == 0:
                has_zero_pos = True

        # Increment positions if there is a zero position
        if has_zero_pos:
            for inpt in input_fields:
                if len(inpt) == 3:
                    name, _, mdata = inpt
                else:
                    name, _, __, mdata = inpt
                if "position" in mdata and mdata["position"] >= 0:
                    mdata["position"] = mdata.pop("position") + 1

        input_fields_str = ""
        output_fields_str = ""

        for inpt in input_fields:
            if len(inpt) == 3:
                name, type_, mdata = inpt
                mdata = copy(mdata)  # Copy to avoid modifying the original
            else:
                name, type_, default, mdata = inpt
                mdata = copy(mdata)  # Copy to avoid modifying the original
                mdata["default"] = default
            if (
                any(name in x for x in xor_sets)
                and type_ is not bool
                and not is_optional(type_)
                and (inspect.isclass(type_) and not issubclass(type_, ty.Sequence))
            ):
                type_ = type_ | None
            type_str = type_to_str(type_, mdata.pop("mandatory", True))
            if mdata.pop("copyfile", None):
                nonstd_types.add(File)
                mdata["copy_mode"] = "File.CopyMode.copy"
            mdata.pop("xor", None)
            args_str = ", ".join(f"{k}={v!r}" for k, v in mdata.items())
            if "path_template" in mdata:
                output_fields_str += (
                    f"        {name}: {type_str} = shell.outarg({args_str})\n"
                )
            else:
                input_fields_str += f"    {name}: {type_str} = shell.arg({args_str})\n"

        # callable_fields = set(n for n, _, __ in self.callable_output_fields)

        for outpt in output_fields:
            name, type_, mdata = outpt
            func_args = []
            for func_arg in OUT_FUNC_ARGS:
                if func_arg in mdata:
                    func_args.append(f"{func_arg}={mdata[func_arg]}")
                    mdata.pop(func_arg)
            args = [f"{k}={v!r}" for k, v in mdata.items()] + func_args
            output_fields_str += (
                f"        {name}: {type_to_str(type_)} = shell.out({', '.join(args)})\n"
            )
        if not output_fields_str:
            output_fields_str = "        pass\n"

        spec_str = (
            self.init_code
            + self.format_arg_code
            + self.parse_inputs_code
            + self.callables_code
            + self.defaults_code
        )

        spec_str += "@shell.define"
        if xor_sets:
            spec_str += f"(xor={[list(x) for x in xor_sets]})"
        spec_str += (
            f"\nclass {self.task_name}(shell.Task['{self.task_name}.Outputs']):\n"
        )
        spec_str += '    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'
        spec_str += f"    executable='{executable}'\n"

        spec_str += input_fields_str + "\n"
        spec_str += "    class Outputs(shell.Outputs):\n"
        spec_str += output_fields_str

        # spec_str = re.sub(r"'#([^'#]+)#'", r"\1", spec_str)

        for m in sorted(self.used.methods, key=attrgetter("__name__")):
            if m.__name__ in self.included_methods:
                continue
            if any(
                s[0] == self.nipype_interface._list_outputs
                for s in self.used.method_stacks[m.__name__]
            ):
                additional_args = CALLABLE_ARGS
            else:
                additional_args = []
            method_str = self.process_method(
                m, input_names, output_names, additional_args=additional_args
            )
            method_str = method_str.replace("os.getcwd()", "output_dir")
            spec_str += "\n\n" + method_str

        self.used.import_stmts.update(
            self.construct_imports(
                nonstd_types,
                spec_str,
                include_task=False,
                base=base_imports,
            )
        )

        return spec_str

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
        if not self._format_arg_body:
            return []
        sig = inspect.getsource(self.nipype_interface._format_arg).split("\n", 1)[0]
        name_arg = re.match(r"\s*def _format_arg\(self, (\w+),", sig).group(1)
        return re.findall(name_arg + r" == \"(\w+)\"", self._format_arg_body)

    @property
    def callable_default_input_field_names(self):
        if not self._gen_filename_body:
            return []
        sig = inspect.getsource(self.nipype_interface._format_arg).split("\n", 1)[0]
        name_arg = re.match(r"\s*def _gen_filename\((\w+),", sig).group(1)
        return re.findall(name_arg + r" == \"(\w+)\"", self._gen_filename_body)

    @property
    def callable_output_fields(self):
        return [
            f
            for f in super().output_fields
            if ("path_template" not in f[-1] and f[0] not in INBUILT_NIPYPE_TRAIT_NAMES)
        ]

    @property
    def callable_output_field_names(self):
        return [f[0] for f in self.callable_output_fields]

    @cached_property
    def _format_arg_body(self):
        if self.method_omitted("_format_arg"):
            return ""
        return self._unwrap_supers(
            self.nipype_interface._format_arg,
            base_replacement="return argstr.format(**inputs)",
        )

    @cached_property
    def _gen_filename_body(self):
        if self.method_omitted("_gen_filename"):
            return ""
        return self._unwrap_supers(self.nipype_interface._gen_filename)

    @property
    def init_code(self):
        if "__init__" not in self.included_methods:
            return ""
        body = self._unwrap_supers(
            self.nipype_interface.__init__,
            base_replacement="",
        )
        code_str = f"def _init():\n    {body}\n"
        return code_str

    @property
    def format_arg_code(self):
        if "_format_arg" not in self.included_methods:
            return ""
        body = self._format_arg_body
        body = self._process_inputs(body)
        existing_args = list(
            inspect.signature(self.nipype_interface._format_arg).parameters
        )[1:]
        name_arg, spec_arg, val_arg = existing_args

        # Single-line replacement args
        body = re.sub(
            spec_arg + r"\.argstr % +([^\( ].+)",
            r"argstr.format(**{" + name_arg + r": \1})",
            body,
        )
        body = body.replace(f"{spec_arg}.argstr", "argstr")

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
        if not body.strip():
            return ""
        body = self.unwrap_nested_methods(body, inputs_as_dict=True)

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
        body = self._unwrap_supers(
            self.nipype_interface._parse_inputs, base_replacement="return {}"
        )
        body = self._process_inputs(body)
        body = re.sub(
            r"self.\_format_arg\((\w+), (\w+), (\w+)\)",
            r"_format_arg(\1, \3, inputs, parsed_inputs, argstrs.get(\1))",
            body,
        )

        # Strip out return value
        body = re.sub(r"\s*return .*\n", "", body)
        if not body.strip():
            return ""
        body = self.unwrap_nested_methods(body, inputs_as_dict=True)
        # Supers are already unwrapped so this isn't necessary
        # body = self.replace_supers(
        #     body,
        #     super_base=find_super_method(
        #         self.nipype_interface, "_parse_inputs", include_class=True
        #     )[1],
        # )
        # body = self._misc_cleanups(body)

        code_str = "def _parse_inputs(inputs, output_dir=None):\n    if not output_dir:\n        output_dir = os.getcwd()\n    parsed_inputs = {}"
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

        if not body.strip():
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
            agg_body = self._unwrap_supers(
                self.nipype_interface.aggregate_outputs,
                base_replacement="    return {}",
            )
            need_list_outputs = bool(re.findall(r"\b_list_outputs\b", agg_body))
            agg_body = self._process_inputs(agg_body)

            if not agg_body.strip():
                return ""
            agg_body = self.unwrap_nested_methods(
                agg_body, additional_args=CALLABLE_ARGS, inputs_as_dict=True
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
                lo_body = self._unwrap_supers(
                    self.nipype_interface._list_outputs,
                    base_replacement="    return {}",
                )
                lo_body = self._process_inputs(lo_body)
                lo_body = re.sub(
                    r"(\w+) = self\.output_spec\(\).(?:trait_)get\(\)",
                    r"\1 = {}",
                    lo_body,
                )

                if not lo_body.strip():
                    return ""
                lo_body = self.unwrap_nested_methods(
                    lo_body, additional_args=CALLABLE_ARGS, inputs_as_dict=True
                )
                lo_body = self.replace_supers(
                    lo_body,
                    super_base=find_super_method(
                        self.nipype_interface, "_list_outputs", include_class=True
                    )[1],
                )

                parse_inputs_call = (
                    "\n    parsed_inputs = _parse_inputs(inputs, output_dir=output_dir)"
                    if self.parse_inputs_code
                    else ""
                )

                code_str += f"""def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):{inputs_as_dict_call}{parse_inputs_call}
{lo_body}


"""
        # Create separate function for each output field in the "callables" section
        for output_field in self.callable_output_fields:
            output_name = output_field[0]
            code_str += (
                f"\n\n\ndef {output_name}_callable(output_dir, inputs, stdout, stderr):\n"
                f"    outputs = {func_name}(output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr)\n"
                '    return outputs.get("' + output_name + '")\n\n'
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

    def _unwrap_supers(
        self, method: ty.Callable, base=None, base_replacement="", arg_names=None
    ) -> str:
        if base is None:
            base = find_super_method(
                self.nipype_interface, method.__name__, include_class=True
            )[1]
        if self.package.is_omitted(base):
            return base_replacement
        method_name = method.__name__
        body = inspect.getsource(method).split("\n", 1)[1]
        body = "\n" + _strip_doc_string(body)
        body = cleanup_function_body(body)
        defn_args = list(inspect.signature(method).parameters.keys())[1:]
        if arg_names:
            for new, old in zip(defn_args, arg_names):
                if new != old:
                    body = re.sub(r"\b" + old + r"\b", new, body)
        super_re = re.compile(
            r"\n( *(?:return|\w+\s*=)?\s*super\([^\)]*\)\." + method_name + ")"
        )
        if super_re.search(body):
            super_method, base = find_super_method(base, method_name)
            super_body = self._unwrap_supers(
                super_method, base, base_replacement, arg_names=defn_args
            )
            return_indent = return_val = None
            if super_body:
                super_args = list(inspect.signature(super_method).parameters.keys())[1:]
                lines = super_body.splitlines()
                match = re.match(r"(\s*)return\s+(.*)", lines[-1])
                if match:
                    return_indent, return_val = match.groups()
                    super_body = "\n".join(lines[:-1])
            else:
                super_args = []

            splits = super_re.split(body)
            new_body = splits[0]
            for call, block in zip(splits[1::2], splits[2::2]):
                _, args, post = extract_args(block)
                indent = re.match(r"^(\s*)", call).group(1)
                if "=" in call:
                    assert return_val
                    assigned_to_varname = call.split("=")[0].strip()
                    if return_val == assigned_to_varname:
                        replacement = super_body
                    else:
                        replacement = (
                            super_body
                            + f"\n{indent}{assigned_to_varname} = {return_val}"
                        )
                elif super_body:
                    replacement = super_body
                else:
                    if len(indent) > 4:
                        new_body += f"\n{indent}pass"
                    new_body += post[1:]
                    continue
                for o, n in zip(args, super_args):
                    replacement = re.sub(r"\b" + o + r"\b", n, replacement)
                new_body += replacement + post[1:]
            return new_body
        return body


def _strip_doc_string(body: str) -> str:
    if re.match(r"\s*(\"|')", body):
        body = "\n".join(split_source_into_statements(body)[1:])
    return body
