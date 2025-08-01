import typing as ty
import re
import inspect
from operator import attrgetter, itemgetter
from functools import cached_property
import logging
import attrs
from .base import BaseInterfaceConverter
from ..symbols import UsedSymbols, get_return_line, find_super_method


logger = logging.getLogger("nipype2pydra")


def type2str(type_):
    """Convert a type to a string representation."""
    if isinstance(type_, str):
        return type_
    if type_ is ty.Any:
        return "ty.Any"
    if origin := ty.get_origin(type_):
        return f"{type2str(origin)}[{', '.join(type2str(arg) for arg in ty.get_args(type_))}]"
    module_name = "ty." if type_.__module__ == "typing" else ""
    if hasattr(type_, "__name__"):
        return module_name + type_.__name__
    elif hasattr(type_, "__qualname__"):
        return module_name + type_.__qualname__
    else:
        return str(type_).replace("typing.", "ty.")


@attrs.define(slots=False)
class PythonInterfaceConverter(BaseInterfaceConverter):

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
        used: UsedSymbols
            symbols used in the code
        """

        base_imports = [
            "import logging",
            "import attrs",
            "from logging import getLogger",
            "from pydra.compose import python",
        ]

        # def types_to_names(spec_fields):
        #     spec_fields_str = []
        #     for el in spec_fields:
        #         el = list(el)
        #         tp_str = str(el[1])
        #         if tp_str.startswith("<class "):
        #             tp_str = el[1].__name__
        #         else:
        #             # Alter modules in type string to match those that will be imported
        #             tp_str = tp_str.replace("typing", "ty")
        #             tp_str = re.sub(r"(\w+\.)+(?<!ty\.)(\w+)", r"\2", tp_str)
        #         el[1] = tp_str
        #         spec_fields_str.append(tuple(el))
        #     return spec_fields_str

        # input_fields_str = types_to_names(spec_fields=input_fields)
        # output_fields_str = types_to_names(spec_fields=output_fields)
        input_names = [i[0] for i in input_fields]
        output_names = [o[0] for o in output_fields]
        # output_type_names = [o[1] for o in output_fields_str]

        method_body = ""
        for field in input_fields:
            if field[-1].get("copyfile"):
                method_body += f"    {field[0]} = {field[0]}.copy(Path.cwd())\n"
        for field in output_fields:
            method_body += f"    {field[0]} = attrs.NOTHING\n"

        used_method_names = [m.__name__ for m in self.used.methods]
        # Combined src of init and list_outputs
        if "__init__" in used_method_names:
            init_code = inspect.getsource(self.nipype_interface.__init__).strip()
            init_class = find_super_method(
                self.nipype_interface, "__init__", include_class=True
            )[1]
            assert not self.package.is_omitted(init_class)
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
            method_body += init_code + "\n"

        # Combined src of run_interface and list_outputs
        if "_run_interface" in used_method_names:
            run_interface_code = inspect.getsource(
                self.nipype_interface._run_interface
            ).strip()
            run_interface_class = find_super_method(
                self.nipype_interface, "_run_interface", include_class=True
            )[1]
            assert not self.package.is_omitted(run_interface_class)
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
            method_body += run_interface_code + "\n"

        if "_list_outputs" in used_method_names:
            list_outputs_code = inspect.getsource(
                self.nipype_interface._list_outputs
            ).strip()
            list_outputs_class = find_super_method(
                self.nipype_interface, "_list_outputs", include_class=True
            )[1]
            assert not self.package.is_omitted(list_outputs_class)
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
            method_body += list_outputs_code + "\n"

        assert method_body, "Neither `run_interface` and `list_outputs` are defined"

        spec_str = "@python.define\n"
        spec_str += (
            f"class {self.task_name}(python.Task['{self.task_name}.Outputs']):\n"
        )
        spec_str += '    """\n'
        spec_str += self.create_doctests(
            input_fields=input_fields, nonstd_types=nonstd_types
        )
        spec_str += '    """\n'

        for inpt in input_fields:
            if len(inpt) == 4:
                name, type_, default, _ = inpt
                spec_str += f"    {name}: {type2str(type_)} = {default}\n"
            else:
                name, type_, _ = inpt
                spec_str += f"    {name}: {type2str(type_)}\n"

        spec_str += "\n\n    class Outputs(python.Outputs):\n"
        for outpt in output_fields:
            name, type_, _ = outpt
            spec_str += f"        {name}: {type2str(type_)}\n"

        spec_str += "\n    @staticmethod\n"
        spec_str += (
            "    def function("
            + ", ".join(f"{i[0]}: {type2str(i[1])}" for i in input_fields)
            + ")"
        )
        output_types = [type2str(o[1]) for o in output_fields]
        if any(t is not ty.Any for t in output_types):
            spec_str += " -> "
            if len(output_types) > 1:
                spec_str += "tuple[" + ", ".join(output_types) + "]"
            else:
                spec_str += output_types[0]
        spec_str += ":\n"
        spec_str += "    " + method_body.replace("\n", "\n    ") + "\n"
        spec_str += "\n        return {}".format(", ".join(output_names))

        for m in sorted(self.used.methods, key=attrgetter("__name__")):
            if m.__name__ not in self.included_methods:
                spec_str += "\n\n" + self.process_method(
                    m,
                    input_names,
                    output_names,
                    super_base=find_super_method(
                        self.nipype_interface, m.__name__, include_class=True
                    )[1],
                )

        for name, (m, super_base) in sorted(
            self.used.supers.items(), key=itemgetter(0)
        ):
            spec_str += "\n\n" + self.process_method(
                m,
                input_names,
                output_names,
                super_base=super_base,
                new_name=name,
            )

        # Replace runtime attributes
        additional_imports = set()
        for attr, repl, imprt in self.RUNTIME_ATTRS:
            repl_spec_str = spec_str.replace(f"runtime.{attr}", repl)
            if repl_spec_str != spec_str:
                additional_imports.add(imprt)
                spec_str = repl_spec_str

        self.used.import_stmts.update(
            self.construct_imports(
                nonstd_types,
                spec_str,
                include_task=False,
                base=base_imports
                + list(self.used.import_stmts)
                + list(additional_imports),
            )
        )

        return spec_str

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
