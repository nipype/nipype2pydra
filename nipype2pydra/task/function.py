import typing as ty
import re
import inspect
from operator import attrgetter, itemgetter
from functools import cached_property
import itertools
import attrs
from .base import BaseTaskConverter
from ..utils import (
    extract_args,
    UsedSymbols,
    get_source_code,
    get_local_functions,
    get_local_constants,
    cleanup_function_body,
    insert_args_in_signature,
)


@attrs.define(slots=False)
class FunctionTaskConverter(BaseTaskConverter):

    def generate_task_str(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        base_imports = [
            "import pydra.mark",
            "import logging",
            "from logging import getLogger",
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

        # Combined src of run_interface and list_outputs
        method_body = inspect.getsource(self.nipype_interface._run_interface).strip()
        method_body = "\n".join(method_body.split("\n")[1:-1])
        lo_src = inspect.getsource(self.nipype_interface._list_outputs).strip()
        lo_lines = lo_src.split("\n")
        lo_src = "\n".join(lo_lines[1:-1])
        method_body += lo_src
        method_body = self.process_method_body(method_body, input_names, output_names)

        used = UsedSymbols.find(
            self.nipype_module,
            [method_body]
            + [
                inspect.getsource(f)
                for f in itertools.chain(
                    self.referenced_local_functions, self.referenced_methods
                )
            ],
        )

        spec_str = "\n".join(f"{n} = {d}" for n, d in used.constants)

        # Create the spec string
        spec_str += "\n\n" + self.function_callables()
        spec_str += "logger = getLogger(__name__)\n\n"
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
        spec_str += method_body + "\n"
        spec_str += "\n    return {}".format(", ".join(output_names))

        spec_str += "\n\n# Nipype methods converted into functions\n\n"

        for m in sorted(self.referenced_methods, key=attrgetter("__name__")):
            spec_str += "\n\n" + self.process_method(m, input_names, output_names)

        # Replace runtime attributes
        additional_imports = set()
        for attr, repl, imprt in self.RUNTIME_ATTRS:
            repl_spec_str = spec_str.replace(f"runtime.{attr}", repl)
            if repl_spec_str != spec_str:
                additional_imports.add(imprt)
                spec_str = repl_spec_str

        spec_str += "\n\n# Functions defined locally in the original module\n\n"

        for func in sorted(used.local_functions, key=attrgetter("__name__")):
            spec_str += "\n\n" + cleanup_function_body(
                get_source_code(func)
            )

        spec_str += "\n\n# Functions defined in neighbouring modules that have been included inline instead of imported\n\n"

        for func_name, func in sorted(used.funcs_to_include, key=itemgetter(0)):
            func_src = get_source_code(func)
            func_src = re.sub(
                r"^(#[^\n]+\ndef) (\w+)(?=\()",
                r"\1 " + func_name,
                func_src,
                flags=re.MULTILINE,
            )
            spec_str += "\n\n" + cleanup_function_body(func_src)

        for klass_name, klass in sorted(used.classes_to_include, key=itemgetter(0)):
            klass_src = get_source_code(klass)
            klass_src = re.sub(
                r"^(#[^\n]+\nclass) (\w+)(?=\()",
                r"\1 " + klass_name,
                klass_src,
                flags=re.MULTILINE,
            )
            spec_str += "\n\n" + cleanup_function_body(klass_src)

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            include_task=False,
            base=base_imports + list(used.imports) + list(additional_imports),
        )
        spec_str = "\n".join(imports) + "\n\n" + spec_str

        return spec_str

    def process_method(
        self,
        method: str,
        input_names: ty.List[str],
        output_names: ty.List[str],
        method_args: ty.Dict[str, ty.List[str]] = None,
        method_returns: ty.Dict[str, ty.List[str]] = None,
    ):
        src = inspect.getsource(method)
        pre, args, post = extract_args(src)
        args.remove("self")
        if "runtime" in args:
            args.remove("runtime")
        if method.__name__ in self.method_args:
            args += [f"{a}=None" for a in self.method_args[method.__name__]]
        # Insert method args in signature if present
        return_types, method_body = post.split(":", maxsplit=1)
        method_body = method_body.split("\n", maxsplit=1)[1]
        method_body = self.process_method_body(method_body, input_names, output_names)
        if self.method_returns.get(method.__name__):
            return_args = self.method_returns[method.__name__]
            method_body = (
                "    " + " = ".join(return_args) + " = attrs.NOTHING\n" + method_body
            )
            method_lines = method_body.splitlines()
            method_body = "\n".join(method_lines[:-1])
            last_line = method_lines[-1]
            if "return" in last_line:
                method_body += "," + ",".join(return_args)
            else:
                method_body += (
                    "\n" + last_line + "\n    return " + ",".join(return_args)
                )
        return f"{pre.strip()}{', '.join(args)}{return_types}:\n{method_body}"

    def process_method_body(
        self, method_body: str, input_names: ty.List[str], output_names: ty.List[str]
    ) -> str:
        # Replace self.inputs.<name> with <name> in the function body
        input_re = re.compile(r"self\.inputs\.(\w+)")
        unrecognised_inputs = set(
            m for m in input_re.findall(method_body) if m not in input_names
        )
        assert (
            not unrecognised_inputs
        ), f"Found the following unrecognised inputs {unrecognised_inputs}"
        method_body = input_re.sub(r"\1", method_body)

        output_re = re.compile(self.return_value + r"\[(?:'|\")(\w+)(?:'|\")\]")
        unrecognised_outputs = set(
            m for m in output_re.findall(method_body) if m not in output_names
        )
        assert (
            not unrecognised_outputs
        ), f"Found the following unrecognised outputs {unrecognised_outputs}"
        method_body = output_re.sub(r"\1", method_body)
        # Strip initialisation of outputs
        method_body = re.sub(r"outputs = self.output_spec().*", r"outputs = {}", method_body)
        # Add args to the function signature of method calls
        method_re = re.compile(r"self\.(\w+)(?=\()", flags=re.MULTILINE | re.DOTALL)
        method_names = [m.__name__ for m in self.referenced_methods]
        unrecognised_methods = set(
            m for m in method_re.findall(method_body) if m not in method_names
        )
        assert (
            not unrecognised_methods
        ), f"Found the following unrecognised methods {unrecognised_methods}"
        splits = method_re.split(method_body)
        new_body = splits[0]
        for name, args in zip(splits[1::2], splits[2::2]):
            # Assign additional return values (which were previously saved to member
            # attributes) to new variables from the method call
            if self.method_returns[name]:
                match = re.match(
                    r".*\n *([a-zA-Z0-9\,\. ]+ *=)? *$",
                    new_body,
                    flags=re.MULTILINE | re.DOTALL,
                )
                if match:
                    if match.group(1):
                        new_body_lines = new_body.splitlines()
                        new_body = "\n".join(new_body_lines[:-1])
                        last_line = new_body_lines[-1]
                        new_body += "\n" + re.sub(
                            r"^ *([a-zA-Z0-9\,\. ]+) *= *$",
                            r"\1, =" + ",".join(self.method_returns[name]),
                            last_line,
                            flags=re.MULTILINE,
                        )
                    else:
                        new_body += ",".join(self.method_returns[name]) + " = "
                else:
                    raise NotImplementedError(
                        "Could not augment the return value of the method converted from "
                        "a function with the previously assigned attributes as it is used "
                        "directly. Need to replace the method call with a variable and "
                        "assign the return value to it on a previous line"
                    )
            # Insert additional arguments to the method call (which were previously
            # accessed via member attributes)
            new_body += name + insert_args_in_signature(
                args, [f"{a}={a}" for a in self.method_args[name]]
            )
        method_body = new_body
        # Convert assignment to self attributes into method-scoped variables (hopefully
        # there aren't any name clashes)
        method_body = re.sub(
            r"self\.(\w+ *)(?==)", r"\1", method_body, flags=re.MULTILINE | re.DOTALL
        )
        return cleanup_function_body(method_body)

    @property
    def referenced_local_functions(self):
        return self._referenced_funcs_and_methods[0]

    @property
    def referenced_methods(self):
        return self._referenced_funcs_and_methods[1]

    @property
    def method_args(self):
        return self._referenced_funcs_and_methods[2]

    @property
    def method_returns(self):
        return self._referenced_funcs_and_methods[3]

    @cached_property
    def _referenced_funcs_and_methods(self):
        referenced_funcs = set()
        referenced_methods = set()
        method_args = {}
        method_returns = {}
        self._get_referenced(
            self.nipype_interface._run_interface,
            referenced_funcs,
            referenced_methods,
            method_args,
            method_returns,
        )
        self._get_referenced(
            self.nipype_interface._list_outputs,
            referenced_funcs,
            referenced_methods,
            method_args,
            method_returns,
        )
        return referenced_funcs, referenced_methods, method_args, method_returns

    def replace_attributes(self, function_body: ty.Callable) -> str:
        """Replace self.inputs.<name> with <name> in the function body and add args to the
        function signature"""
        function_body = re.sub(r"self\.inputs\.(\w+)", r"\1", function_body)

    def _get_referenced(
        self,
        method: ty.Callable,
        referenced_funcs: ty.Set[ty.Callable],
        referenced_methods: ty.Set[ty.Callable] = None,
        method_args: ty.Dict[str, ty.List[str]] = None,
        method_returns: ty.Dict[str, ty.List[str]] = None,
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
        method_args: dict[str, list[str]]
            a dictionary to hold additional arguments that need to be added to each method,
            where the dictionary key is the names of the methods
        method_returns: dict[str, list[str]]
            a dictionary to hold the return values of each method,
            where the dictionary key is the names of the methods
        """
        method_body = inspect.getsource(method)
        method_body = re.sub(r"\s*#.*", "", method_body)  # Strip out comments
        ref_local_func_names = re.findall(r"(?<!self\.)(\w+)\(", method_body)
        ref_local_funcs = set(
            f
            for f in self.local_functions
            if f.__name__ in ref_local_func_names and f not in referenced_funcs
        )

        ref_method_names = re.findall(r"(?<=self\.)(\w+)\(", method_body)
        ref_methods = set(m for m in self.methods if m.__name__ in ref_method_names)

        referenced_funcs.update(ref_local_funcs)
        referenced_methods.update(ref_methods)

        referenced_inputs = set(re.findall(r"(?<=self\.inputs\.)(\w+)", method_body))
        referenced_outputs = set(re.findall(r"self\.(\w+) *=", method_body))
        if self.return_value.startswith("self."):
            referenced_outputs.update(
                re.findall(
                    self.return_value + r"\[(?:'|\")(\w+)(?:'|\")\] *=", method_body
                )
            )
        for func in ref_local_funcs:
            rf_inputs, rf_outputs = self._get_referenced(
                func, referenced_funcs, referenced_methods
            )
            referenced_inputs.update(rf_inputs)
            referenced_outputs.update(rf_outputs)
        for meth in ref_methods:
            ref_inputs, ref_outputs = self._get_referenced(
                meth,
                referenced_funcs,
                referenced_methods,
                method_args=method_args,
                method_returns=method_returns,
            )
            method_args[meth.__name__] = ref_inputs
            method_returns[meth.__name__] = ref_outputs
            referenced_inputs.update(ref_inputs)
            referenced_outputs.update(ref_outputs)
        return referenced_inputs, sorted(referenced_outputs)

    @cached_property
    def source_code(self):
        with open(inspect.getsourcefile(self.nipype_interface)) as f:
            return f.read()

    @cached_property
    def local_functions(self):
        """Get the functions defined in the same file as the interface"""
        return get_local_functions(self.nipype_module)

    @cached_property
    def local_constants(self):
        return get_local_constants(self.nipype_module)

    @cached_property
    def return_value(self):
        return_line = (
            inspect.getsource(self.nipype_interface._list_outputs)
            .strip()
            .split("\n")[-1]
        )
        match = re.match(r"\s*return(.*)", return_line)
        return match.group(1).strip()

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
