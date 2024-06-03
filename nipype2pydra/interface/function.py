import typing as ty
import re
import inspect
from operator import attrgetter
from functools import cached_property
import logging
import attrs
from nipype.interfaces.base import BaseInterface, TraitedSpec
from .base import BaseInterfaceConverter
from ..utils import UsedSymbols, get_return_line, find_super_method


logger = logging.getLogger("nipype2pydra")


@attrs.define(slots=False)
class FunctionInterfaceConverter(BaseInterfaceConverter):

    converter_type = "function"

    @property
    def included_methods(self) -> ty.Tuple[str, ...]:
        return ("__init__", "_run_interface", "_list_outputs")

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
            "import pydra.mark",
            "import logging",
            "from logging import getLogger",
            "from pydra.engine.task import FunctionTask",
            "import attrs",
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

        used = UsedSymbols.find(
            self.nipype_module,
            self.referenced_local_functions,
            omit_classes=self.package.omit_classes,
            omit_modules=self.package.omit_modules,
            omit_functions=self.package.omit_functions,
            omit_constants=self.package.omit_constants,
            always_include=self.package.all_explicit,
            translations=self.package.all_import_translations,
            absolute_imports=True,
        )

        for ref_method in self.referenced_methods:
            method_module = find_super_method(
                self.nipype_interface, ref_method.__name__, include_class=True
            )[1].__module__
            method_used = UsedSymbols.find(
                method_module,
                [ref_method],
                omit_classes=self.package.omit_classes,
                omit_modules=self.package.omit_modules,
                omit_functions=self.package.omit_functions,
                omit_constants=self.package.omit_constants,
                always_include=self.package.all_explicit,
                translations=self.package.all_import_translations,
                absolute_imports=True,
            )
            used.update(method_used, from_other_module=False)

        method_body = ""
        for field in input_fields:
            if field[-1].get("copyfile"):
                method_body += f"    {field[0]} = {field[0]}.copy(Path.cwd())\n"
        for field in output_fields:
            method_body += f"    {field[0]} = attrs.NOTHING\n"

        # Combined src of init and list_outputs
        init_code = inspect.getsource(self.nipype_interface.__init__).strip()
        init_class = find_super_method(
            self.nipype_interface, "__init__", include_class=True
        )[1]
        if not self.package.is_omitted(init_class):
            # Strip out method def and return statement
            method_lines = init_code.strip().split("\n")[1:]
            if re.match(r"\s*return", method_lines[-1]):
                method_lines = method_lines[:-1]
            init_code = "\n".join(method_lines)
            init_code = self.process_method_body(
                init_code,
                input_names,
                output_names,
                super_base=init_class,
            )

            init_used = UsedSymbols.find(
                init_class.__module__,
                [init_code],
                omit_classes=self.package.omit_classes + [BaseInterface, TraitedSpec],
                omit_modules=self.package.omit_modules,
                omit_functions=self.package.omit_functions,
                omit_constants=self.package.omit_constants,
                always_include=self.package.all_explicit,
                translations=self.package.all_import_translations,
                absolute_imports=True,
            )
            used.update(init_used, from_other_module=False)
            method_body += init_code + "\n"

        # Combined src of run_interface and list_outputs
        run_interface_code = inspect.getsource(
            self.nipype_interface._run_interface
        ).strip()
        run_interface_class = find_super_method(
            self.nipype_interface, "_run_interface", include_class=True
        )[1]
        if not self.package.is_omitted(run_interface_class):
            # Strip out method def and return statement
            method_lines = run_interface_code.strip().split("\n")[1:]
            if re.match(r"\s*return", method_lines[-1]):
                method_lines = method_lines[:-1]
            run_interface_code = "\n".join(method_lines)
            run_interface_code = self.process_method_body(
                run_interface_code,
                input_names,
                output_names,
                super_base=run_interface_class,
            )

            run_interface_used = UsedSymbols.find(
                run_interface_class.__module__,
                [run_interface_code],
                omit_classes=self.package.omit_classes,
                omit_modules=self.package.omit_modules,
                omit_functions=self.package.omit_functions,
                omit_constants=self.package.omit_constants,
                always_include=self.package.all_explicit,
                translations=self.package.all_import_translations,
                absolute_imports=True,
            )
            used.update(run_interface_used, from_other_module=False)
            method_body += run_interface_code + "\n"

        list_outputs_code = inspect.getsource(
            self.nipype_interface._list_outputs
        ).strip()
        list_outputs_class = find_super_method(
            self.nipype_interface, "_list_outputs", include_class=True
        )[1]
        if not self.package.is_omitted(list_outputs_class):
            # Strip out method def and return statement
            lo_lines = list_outputs_code.strip().split("\n")[1:]
            if re.match(r"\s*(return|raise NotImplementedError)", lo_lines[-1]):
                lo_lines = lo_lines[:-1]
            list_outputs_code = "\n".join(lo_lines)
            list_outputs_code = self.process_method_body(
                list_outputs_code,
                input_names,
                output_names,
                super_base=list_outputs_class,
                unwrap_return_dict=True,
            )

            list_outputs_used = UsedSymbols.find(
                list_outputs_class.__module__,
                [list_outputs_code],
                omit_classes=self.package.omit_classes,
                omit_modules=self.package.omit_modules,
                omit_functions=self.package.omit_functions,
                omit_constants=self.package.omit_constants,
                always_include=self.package.all_explicit,
                translations=self.package.all_import_translations,
                absolute_imports=True,
            )
            used.update(list_outputs_used, from_other_module=False)
            method_body += list_outputs_code + "\n"

        assert method_body, "Neither `run_interface` and `list_outputs` are defined"

        spec_str = "@pydra.mark.task\n"
        spec_str += "@pydra.mark.annotate({'return': {"
        spec_str += ", ".join(f"'{n}': {t}" for n, t, _ in output_fields_str)
        spec_str += "}})\n"
        spec_str += f"def {self.task_name}("
        spec_str += ", ".join(
            (
                f"{i[0]}: {i[1]} = {i[2]!r}"
                if len(i) == 4
                else f"{i[0]}: {i[1]} = attrs.NOTHING"
            )
            for i in input_fields_str
        )
        spec_str += ")"
        if output_type_names:
            spec_str += "-> "
            if len(output_type_names) > 1:
                spec_str += "ty.Tuple[" + ", ".join(output_type_names) + "]"
            else:
                spec_str += output_type_names[0]
        spec_str += ':\n    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'
        spec_str += method_body + "\n"
        spec_str += "\n    return {}".format(", ".join(output_names))

        spec_str += "\n\n# Nipype methods converted into functions\n\n"

        for m in sorted(self.referenced_methods, key=attrgetter("__name__")):
            spec_str += "\n\n" + self.process_method(
                m,
                input_names,
                output_names,
                super_base=find_super_method(
                    self.nipype_interface, m.__name__, include_class=True
                )[1],
            )

        # Replace runtime attributes
        additional_imports = set()
        for attr, repl, imprt in self.RUNTIME_ATTRS:
            repl_spec_str = spec_str.replace(f"runtime.{attr}", repl)
            if repl_spec_str != spec_str:
                additional_imports.add(imprt)
                spec_str = repl_spec_str

        used.imports.update(
            self.construct_imports(
                nonstd_types,
                spec_str,
                include_task=False,
                base=base_imports + list(used.imports) + list(additional_imports),
            )
        )

        return spec_str, used

    def replace_attributes(self, function_body: ty.Callable) -> str:
        """Replace self.inputs.<name> with <name> in the function body and add args to the
        function signature"""
        function_body = re.sub(r"self\.inputs\.(\w+)", r"\1", function_body)

    @cached_property
    def return_value(self):
        return_value = get_return_line(self.nipype_interface._list_outputs)
        if not return_value:
            return_value = get_return_line(self.nipype_interface._outputs)
        return return_value

    RUNTIME_ATTRS = (
        ("cwd", "os.getcwd()", "import os"),
        ("environ", "os.environ", "import os"),
        ("hostname", "platform.node()", "import platform"),
        ("platform", "platform.platform()", "import platform"),
    )
