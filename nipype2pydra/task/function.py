import typing as ty
import re
import inspect
from operator import attrgetter, itemgetter
from functools import cached_property
import itertools
from importlib import import_module
import attrs
from .base import BaseTaskConverter


@attrs.define(slots=False)
class FunctionTaskConverter(BaseTaskConverter):
    def generate_task_str(self, filename, input_fields, nonstd_types, output_fields):
        """writing pydra task to the dile based on the input and output spec"""

        base_imports = [
            "import pydra.mark",
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

        (other_imports, funcs_to_include, used_local_functions, used_constants) = (
            self.get_imports_and_functions_to_include(
                [method_body]
                + [
                    inspect.getsource(f)
                    for f in itertools.chain(
                        self.referenced_local_functions, self.referenced_methods
                    )
                ]
            )
        )

        spec_str = "\n".join(f"{n} = {d}" for n, d in used_constants)

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

        for func in sorted(used_local_functions, key=attrgetter("__name__")):
            spec_str += "\n\n" + self.process_function_body(
                inspect.getsource(func), input_names
            )

        spec_str += "\n\n# Functions defined in neighbouring modules that have been included inline instead of imported\n\n"

        for func_name, func in sorted(funcs_to_include, key=itemgetter(0)):
            func_src = inspect.getsource(func)
            func_src = re.sub(
                r"^(def|class) (\w+)(?=\()",
                r"\1 " + func_name,
                func_src,
                flags=re.MULTILINE,
            )
            spec_str += "\n\n" + self.process_function_body(func_src, input_names)

        imports = self.construct_imports(
            nonstd_types,
            spec_str,
            include_task=False,
            base=base_imports + list(other_imports) + list(additional_imports),
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
        pre, argstr, post = split_parens_contents(src)
        args = re.split(r" *, *", argstr)
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
            method_body = ("    " + " = ".join(return_args) + " = attrs.NOTHING\n" + method_body)
            method_lines = method_body.splitlines()
            method_body = "\n".join(method_lines[:-1])
            last_line = method_lines[-1]
            if "return" in last_line:
                method_body += "," + ",".join(return_args)
            else:
                method_body += "\n" + last_line + "\n    return " + ",".join(return_args)
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
            if self.method_returns[name]:
                match = re.match(r".*\n *([a-zA-Z0-9\,\. ]+ *=)? *$", new_body, flags=re.MULTILINE | re.DOTALL)
                if match:
                    if match.group(1):
                        new_body_lines = new_body.splitlines()
                        new_body = '\n'.join(new_body_lines[:-1])
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
            new_body += name + self.insert_args_in_signature(
                args, [f"{a}={a}" for a in self.method_args[name]]
            )
        method_body = new_body
        # Convert assignment to self attributes into method-scoped variables (hopefully
        # there aren't any name clashes)
        method_body = re.sub(
            r"self\.(\w+ *)(?==)", r"\1", method_body, flags=re.MULTILINE | re.DOTALL
        )
        return self.process_function_body(method_body, input_names=input_names)

    def process_function_body(
        self, function_body: str, input_names: ty.List[str]
    ) -> str:
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
        # Detect the indentation of the source code in src and reduce it to 4 spaces
        indents = re.findall(r"^\s+", function_body, flags=re.MULTILINE)
        min_indent = min(len(i) for i in indents if i)
        indent_reduction = min_indent - 4
        function_body = re.sub(
            r"^" + " " * indent_reduction, "", function_body, flags=re.MULTILINE
        )
        # Other misc replacements
        function_body = function_body.replace("LOGGER.", "logger.")
        function_body = re.sub(
            r"not isdefined\((\w+)\)", r"\1 is attrs.NOTHING", function_body
        )
        function_body = re.sub(
            r"isdefined\((\w+)\)", r"\1 is not attrs.NOTHING", function_body
        )
        return function_body

    def get_imports_and_functions_to_include(
        self,
        function_bodies: ty.List[str],
        source_code: str = None,
        local_functions: ty.List[ty.Callable] = None,
        local_constants: ty.List[ty.Tuple[str, str]] = None,
    ) -> ty.Tuple[ty.List[str], ty.List[ty.Tuple[str, ty.Any]]]:
        """Get the imports required for the function body

        Parameters
        ----------
        function_bodies: list[str]
            the source of all functions that need to be checked for used imports
        source_code: str, optional
            the source code containing the relevant import statements, by default the
            source file containing the interface to be converted
        local_functions: list[callable], optional
            local functions defined in the source code, by default the functions in the
            same file as the interface
        local_constants: list[tuple[str, str]], optional
            local constants defined in the source code with their definitions,
            by default the functions in the same file as the interface

        Returns
        -------
        used_imports : list[str]
            the import statements that need to be included in the converted file
        external_functions: list[tuple[str, Any]]
            list of objects (e.g. classes, functions and variables) that are defined
            in neighbouring modules that need to be included in the converted file
            (as opposed of just imported from independent packages) along with the name
            that they were imported as and therefore should be named as in the converted
            module
        """
        if source_code is None:
            source_code = self.source_code
        if local_functions is None:
            local_functions = self.local_functions
        if local_constants is None:
            local_constants = self.local_constants
        imports = []
        block = ""
        for line in source_code.split("\n"):
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
        used_imports = set()
        used_local_functions = set()
        used_constants = set()
        # Keep looping through local function source until all local functions and constants
        # are added to the used symbols
        new_symbols = True
        while new_symbols:
            new_symbols = False
            for local_func in local_functions:
                if (
                    local_func.__name__ in used_symbols
                    and local_func not in used_local_functions
                ):
                    used_local_functions.add(local_func)
                    func_body = inspect.getsource(local_func)
                    func_body = re.sub(r"\s*#.*", "", func_body)
                    local_func_symbols = re.findall(r"(\w+)", func_body)
                    used_symbols.update(local_func_symbols)
                    new_symbols = True
            for const_name, const_def in local_constants:
                if (
                    const_name in used_symbols
                    and (const_name, const_def) not in used_constants
                ):
                    if const_name == "LOGGER":
                        continue
                    used_constants.add((const_name, const_def))
                    const_def_symbols = re.findall(r"(\w+)", const_def)
                    used_symbols.update(const_def_symbols)
                    new_symbols = True
        # functions to copy from a relative or nipype module into the output module
        external_functions = set()
        for stmt in imports:
            stmt = stmt.replace("\n", "")
            stmt = stmt.replace("(", "")
            stmt = stmt.replace(")", "")
            base_stmt, symbol_str = stmt.split("import ")
            symbol_parts = re.split(r" *, *", symbol_str)
            split_parts = [re.split(r" +as +", p) for p in symbol_parts]
            used_parts = [p for p in split_parts if p[-1] in used_symbols]
            if used_parts:
                required_stmt = (
                    base_stmt
                    + "import "
                    + ", ".join(" as ".join(p) for p in used_parts)
                )
                match = re.match(r"from ([\w\.]+)", base_stmt)
                import_mod = match.group(1) if match else ""
                if import_mod.startswith(".") or import_mod.startswith("nipype."):
                    if import_mod.startswith("."):
                        match = re.match(r"(\.*)(.*)", import_mod)
                        mod_parts = self.nipype_module.__name__.split(".")
                        nparents = len(match.group(1))
                        if nparents:
                            mod_parts = mod_parts[:-nparents]
                        mod_name = ".".join(mod_parts) + "." + match.group(2)
                    elif import_mod.startswith("nipype."):
                        mod_name = import_mod
                    else:
                        assert False
                    mod = import_module(mod_name)
                    mod_func_bodies = []
                    for used_part in used_parts:
                        func = getattr(mod, used_part[0])
                        external_functions.add((used_part[-1], func))
                        mod_func_bodies.append(inspect.getsource(func))
                    # Recursively include neighbouring objects imported in the module
                    (
                        mod_used_imports,
                        mod_external_funcs,
                        mod_local_funcs,
                        mod_constants,
                    ) = self.get_imports_and_functions_to_include(
                        function_bodies=mod_func_bodies,
                        source_code=inspect.getsource(mod),
                        local_functions=get_local_functions(mod),
                        local_constants=get_local_constants(mod),
                    )
                    used_imports.update(mod_used_imports)
                    external_functions.update(mod_external_funcs)
                    external_functions.update((f.__name__, f) for f in mod_local_funcs)
                    used_constants.update(mod_constants)
                else:
                    used_imports.add(required_stmt)

        return used_imports, external_functions, used_local_functions, used_constants

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
        method_body = re.sub(r"\s*#.*", "", method_body)
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
            referenced_inputs.update(
                self._get_referenced(func, referenced_funcs, referenced_methods)
            )
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

    @classmethod
    def insert_args_in_signature(cls, snippet: str, new_args: ty.Iterable[str]) -> str:
        """Insert the arguments into the function signature"""
        # Split out the argstring from the rest of the code snippet
        pre, argstr, post = split_parens_contents(snippet)
        if argstr:
            args = re.split(r" *, *", argstr)
            if "runtime" in args:
                args.remove("runtime")
        else:
            args = []
        return pre + ", ".join(args + new_args) + post


def split_parens_contents(snippet):
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


def get_local_functions(mod):
    """Get the functions defined in the same file as the interface"""
    functions = []
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if inspect.isfunction(attr) and attr.__module__ == mod.__name__:
            functions.append(attr)
    return functions


def get_local_constants(mod):
    source_code = inspect.getsource(mod)
    parts = re.split(r"^(\w+) *= *", source_code, flags=re.MULTILINE)
    local_vars = []
    for attr_name, following in zip(parts[1::2], parts[2::2]):
        if "(" in following.splitlines()[0]:
            pre, args, _ = split_parens_contents(following)
            local_vars.append((attr_name, pre + re.sub(r"\n *", "", args) + ")"))
        else:
            local_vars.append((attr_name, following.splitlines()[0]))
    return local_vars
