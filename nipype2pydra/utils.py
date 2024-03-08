import traceback
import typing as ty
from types import ModuleType
import sys
import re
import os
import inspect
from contextlib import contextmanager
import attrs
from pathlib import Path
from fileformats.core import FileSet

try:
    from typing import GenericAlias
except ImportError:
    from typing import _GenericAlias as GenericAlias

from importlib import import_module


def load_class_or_func(location_str):
    module_str, name = location_str.split(":")
    module = import_module(module_str)
    return getattr(module, name)


def show_cli_trace(result):
    return "".join(traceback.format_exception(*result.exc_info))


def import_module_from_path(module_path: ty.Union[ModuleType, Path, str]) -> ModuleType:
    if isinstance(module_path, ModuleType) or module_path is None:
        return module_path
    module_path = Path(module_path).resolve()
    sys.path.insert(0, str(module_path.parent))
    try:
        return import_module(module_path.stem)
    finally:
        sys.path.pop(0)


@contextmanager
def set_cwd(path):
    """Sets the current working directory to `path` and back to original
    working directory on exit

    Parameters
    ----------
    path : str
        The file system path to set as the current working directory
    """
    pwd = os.getcwd()
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(pwd)


@contextmanager
def add_to_sys_path(path: Path):
    """Adds the given `path` to the Python system path and then reverts it back to the
    original value on exit

    Parameters
    ----------
    path : str
        The file system path to add to the system path
    """
    sys.path.insert(0, str(path))
    try:
        yield sys.path
    finally:
        sys.path.pop(0)


def is_fileset(tp: type):
    return (
        inspect.isclass(tp) and type(tp) is not GenericAlias and issubclass(tp, FileSet)
    )


def to_snake_case(name: str) -> str:
    """
    Converts a PascalCase string to a snake_case one
    """
    snake_str = ""

    # Loop through each character in the input string
    for i, char in enumerate(name):
        # If the current character is uppercase and it's not the first character or
        # followed by another uppercase character, add an underscore before it and
        # convert it to lowercase
        if (
            i > 0
            and (char.isupper() or char.isdigit())
            and (
                not (name[i - 1].isupper() or name[i - 1].isdigit())
                or (
                    (i + 1) < len(name)
                    and (name[i + 1].islower() or name[i + 1].islower())
                )
            )
        ):
            snake_str += "_"
            snake_str += char.lower()
        else:
            # Otherwise, just add the character as it is
            snake_str += char.lower()

    return snake_str


def add_exc_note(e, note):
    """Adds a note to an exception in a Python <3.11 compatible way

    Parameters
    ----------
    e : Exception
        the exception to add the note to
    note : str
        the note to add

    Returns
    -------
    Exception
        returns the exception again
    """
    if hasattr(e, "add_note"):
        e.add_note(note)
    else:
        e.args = (e.args[0] + "\n" + note,)
    return e


def split_parens_contents(snippet, brackets: bool = False):
    """Splits the code snippet at the first opening parenthesis into a 3-tuple
    consisting of the pre-paren text, the contents of the parens and the post-paren

    Parameters
    ----------
    snippet: str
        the code snippet to split
    brackets: bool, optional
        whether to split at brackets instead of parens, by default False

    Returns
    -------
    pre: str
        the text before the opening parenthesis
    contents: str
        the contents of the parens
    post: str
        the text after the closing parenthesis
    """
    if brackets:
        open = "["
        close = "]"
        pattern = r"(\[|\])"
    else:
        open = "("
        close = ")"
        pattern = r"(\(|\))"
    splits = re.split(pattern, snippet, flags=re.MULTILINE | re.DOTALL)
    depth = 1
    pre = "".join(splits[:2])
    contents = ""
    for i, s in enumerate(splits[2:], start=2):
        if s == open:
            depth += 1
        else:
            if s == close:
                depth -= 1
                if depth == 0:
                    return pre, contents, "".join(splits[i:])
            contents += s
    raise ValueError(f"No matching parenthesis found in '{snippet}'")


@attrs.define
class UsedSymbols:
    """
    A class to hold the used symbols in a module

    Parameters
    -------
    used_imports : list[str]
        the import statements that need to be included in the converted file
    funcs_to_include: list[tuple[str, callable]]
        list of objects (e.g. classes, functions and variables) that are defined
        in neighbouring modules that need to be included in the converted file
        (as opposed of just imported from independent packages) along with the name
        that they were imported as and therefore should be named as in the converted
        module
    used_local_functions: set[callable]
        locally-defined functions used in the function bodies, or nested functions thereof
    used_constants: set[tuple[str, str]]
        constants used in the function bodies, or nested functions thereof, tuples consist
        of the constant name and its definition
    """

    imports: ty.Set[str] = attrs.field(factory=set)
    funcs_to_include: ty.Set[ty.Tuple[str, ty.Callable]] = attrs.field(factory=set)
    classes_to_include: ty.List[ty.Tuple[str, ty.Callable]] = attrs.field(factory=set)
    local_functions: ty.Set[ty.Callable] = attrs.field(factory=set)
    local_classes: ty.List[type] = attrs.field(factory=list)
    constants: ty.Set[ty.Tuple[str, str]] = attrs.field(factory=set)

    def update(self, other: "UsedSymbols"):
        self.imports.update(other.imports)
        self.funcs_to_include.update(other.funcs_to_include)
        self.funcs_to_include.update((f.__name__, f) for f in other.local_functions)
        self.constants.update(other.constants)

    @classmethod
    def find(
        cls,
        module,
        function_bodies: ty.List[str],
    ) -> "UsedSymbols":
        """Get the imports required for the function body

        Parameters
        ----------
        module: ModuleType
            the module containing the functions to be converted
        function_bodies: list[str]
            the source of all functions that need to be checked for used imports

        Returns
        -------
        UsedSymbols
            a class containing the used symbols in the module
        """
        used = cls()
        imports = [
            "import attrs",
            "from fileformats.generic import File, Directory",
            "import logging",
            "from logging import getLogger",
        ]  # attrs is included in imports in case we reference attrs.NOTHING
        block = ""
        source_code = inspect.getsource(module)
        local_functions = get_local_functions(module)
        local_constants = get_local_constants(module)
        local_classes = get_local_classes(module)
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
            used_symbols.update(re.findall(r"\b(\w+)\b", function_body))
        used_symbols -= set(cls.SYMBOLS_TO_IGNORE)
        # Keep looping through local function source until all local functions and constants
        # are added to the used symbols
        new_symbols = True
        while new_symbols:
            new_symbols = False
            for local_func in local_functions:
                if (
                    local_func.__name__ in used_symbols
                    and local_func not in used.local_functions
                ):
                    used.local_functions.add(local_func)
                    func_body = inspect.getsource(local_func)
                    func_body = re.sub(r"\s*#.*", "", func_body)
                    local_func_symbols = re.findall(r"\b(\w+)\b", func_body)
                    used_symbols.update(local_func_symbols)
                    new_symbols = True
            for local_class in local_classes:
                if (
                    local_class.__name__ in used_symbols
                    and local_class not in used.local_classes
                ):
                    used.local_classes.append(local_class)
                    class_body = inspect.getsource(local_class)
                    bases = [
                        b.strip()
                        for b in split_parens_contents(class_body)[1].split(",")
                    ]
                    used_symbols.update(bases)
                    class_body = re.sub(r"\s*#.*", "", class_body)
                    local_class_symbols = re.findall(r"\b(\w+)\b", class_body)
                    used_symbols.update(local_class_symbols)
                    new_symbols = True
            for const_name, const_def in local_constants:
                if (
                    const_name in used_symbols
                    and (const_name, const_def) not in used.constants
                ):
                    used.constants.add((const_name, const_def))
                    const_def_symbols = re.findall(r"\b(\w+)\b", const_def)
                    used_symbols.update(const_def_symbols)
                    new_symbols = True
        # functions to copy from a relative or nipype module into the output module
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
                        mod_parts = module.__name__.split(".")
                        nparents = len(match.group(1))
                        if nparents:
                            mod_parts = mod_parts[:-nparents]
                        mod_name = ".".join(mod_parts)
                        if match.group(2):
                            mod_name += "." + match.group(2)
                    elif import_mod.startswith("nipype."):
                        mod_name = import_mod
                    else:
                        assert False
                    mod = import_module(mod_name)
                    mod_func_bodies = []
                    for used_part in used_parts:
                        atr = getattr(mod, used_part[0])
                        if inspect.isfunction(atr):
                            used.funcs_to_include.add((used_part[-1], atr))
                            mod_func_bodies.append(inspect.getsource(atr))
                        elif inspect.isclass(atr):
                            used.classes_to_include.add((used_part[-1], atr))
                            class_body = split_parens_contents(inspect.getsource(atr))[2].split("\n", 1)[1]
                            mod_func_bodies.append(class_body)
                    # Recursively include neighbouring objects imported in the module
                    used_in_mod = cls.find(
                        mod,
                        function_bodies=mod_func_bodies,
                    )
                    used.update(used_in_mod)
                else:
                    used.imports.add(required_stmt)
        return used

    SYMBOLS_TO_IGNORE = ["isdefined"]


def get_local_functions(mod):
    """Get the functions defined in the module"""
    functions = []
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if inspect.isfunction(attr) and attr.__module__ == mod.__name__:
            functions.append(attr)
    return functions


def get_local_classes(mod):
    """Get the functions defined in the module"""
    classes = []
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if inspect.isclass(attr) and attr.__module__ == mod.__name__:
            classes.append(attr)
    return classes


def get_local_constants(mod):
    """
    Get the constants defined in the module
    """
    source_code = inspect.getsource(mod)
    parts = re.split(r"^(\w+) *= *", source_code, flags=re.MULTILINE)
    local_vars = []
    for attr_name, following in zip(parts[1::2], parts[2::2]):
        if "(" in following.splitlines()[0]:
            pre, args, _ = split_parens_contents(following)
            local_vars.append((attr_name, pre + re.sub(r"\n *", "", args) + ")"))
        elif "[" in following.splitlines()[0]:
            pre, args, _ = split_parens_contents(following, brackets=True)
            local_vars.append((attr_name, pre + re.sub(r"\n *", "", args) + "]"))
        else:
            local_vars.append((attr_name, following.splitlines()[0]))
    return local_vars


def cleanup_function_body(function_body: str) -> str:
    """Ensure 4-space indentation and replace isdefined
    with the attrs.NOTHING constant

    Parameters
    ----------
    function_body: str
        The source code of the function to process
    with_signature: bool, optional
        whether the function signature is included in the source code, by default False

    Returns
    -------
    function_body: str
        The processed source code
    """
    if re.match(r"\s*(def|class)\s+", function_body):
        with_signature = True
    else:
        with_signature = False
    # Detect the indentation of the source code in src and reduce it to 4 spaces
    indents = re.findall(r"^( *)[^\s].*\n", function_body, flags=re.MULTILINE)
    min_indent = min(len(i) for i in indents) if indents else 0
    indent_reduction = min_indent - (0 if with_signature else 4)
    assert indent_reduction >= 0, (
        "Indentation reduction cannot be negative, probably need to set "
        "'with_signature' to True"
    )
    if indent_reduction:
        function_body = re.sub(
            r"^" + " " * indent_reduction, "", function_body, flags=re.MULTILINE
        )
    # Other misc replacements
    # function_body = function_body.replace("LOGGER.", "logger.")
    function_body = re.sub(
        r"not isdefined\(([a-zA-Z0-9\_\.]+)\)",
        r"\1 is attrs.NOTHING",
        function_body,
        flags=re.MULTILINE,
    )
    function_body = re.sub(
        r"isdefined\(([a-zA-Z0-9\_\.]+)\)",
        r"\1 is not attrs.NOTHING",
        function_body,
        flags=re.MULTILINE,
    )
    return function_body


def insert_args_in_signature(snippet: str, new_args: ty.Iterable[str]) -> str:
    """Insert the arguments into a function signature

    Parameters
    ----------
    snippet: str
        the function signature to modify
    new_args: list[str]
        the arguments to insert into the signature

    Returns
    -------
    str
        the modified function signature
    """
    # Split out the argstring from the rest of the code snippet
    pre, argstr, post = split_parens_contents(snippet)
    if argstr:
        args = re.split(r" *, *", argstr)
        if "runtime" in args:
            args.remove("runtime")
    else:
        args = []
    return pre + ", ".join(args + new_args) + post
