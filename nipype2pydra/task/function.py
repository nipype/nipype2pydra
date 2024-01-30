import typing as ty
import re
import inspect
from functools import cached_property
import itertools
import black
import attrs
from .base import TaskConverter


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
