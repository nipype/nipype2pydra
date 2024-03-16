import traceback
import typing as ty
from types import ModuleType
import sys
import re
import os
import inspect
import builtins
from contextlib import contextmanager
import attrs
from pathlib import Path
from fileformats.core import FileSet
from .exceptions import UnmatchedParensException
from nipype.interfaces.base import BaseInterface, TraitedSpec, isdefined, Undefined
from nipype.interfaces.base import traits_extension

try:
    from typing import GenericAlias
except ImportError:
    from typing import _GenericAlias as GenericAlias

from importlib import import_module
from logging import getLogger


logger = getLogger("nipype2pydra")


INBUILT_NIPYPE_TRAIT_NAMES = [
    "__all__",
    "args",
    "trait_added",
    "trait_modified",
    "environ",
    "output_type",
]


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


def extract_args(snippet) -> ty.Tuple[str, ty.List[str], str]:
    """Splits the code snippet at the first opening parenthesis/bracket into a 3-tuple
    consisting of the preceding text + opening paren/bracket, the arguments/items
    within the parenthesis/bracket pair, and the closing paren/bracket + trailing text.

    Quotes and escaped characters are handled correctly, and the function can be used
    to split on either parentheses or brackets. The only limitation is that raw strings
    are not supported.

    Parameters
    ----------
    snippet: str
        the code snippet to split on the first opening parenthesis/bracket to its matching
        closing parenthesis/bracket

    Returns
    -------
    pre: str
        the opening parenthesis/bracket and preceding text
    args: list[str]
        the arguments supplied to the callable/signature
    post: str
        the closing parenthesis/bracket and trailing text

    Raises
    ------
    UnmatchedParensException
        if the first parenthesis/bracket in the snippet is unmatched
    """
    splits = re.split(
        r"(\(|\)|\[|\]|'|\"|\\\(|\\\)|\\\[|\\\]|\\'|\\\")",
        snippet,
        flags=re.MULTILINE | re.DOTALL,
    )
    quote_types = ["'", '"']
    pre = "".join(splits[:2])
    contents = []
    matching = {")": "(", "]": "["}
    open = ["(", "["]
    close = [")", "]"]
    depth = {p: 0 for p in open}
    next_item = ""
    if splits[1] in quote_types:
        first = None  # which bracket/parens type was opened initially (and signifies)
        inquote = splits[1]
    else:
        first = splits[1]
        depth[first] += 1  # Open the first bracket/parens type
        inquote = None
    for i, s in enumerate(splits[2:], start=2):
        if not s:
            continue
        if s[0] == "\\":
            next_item += s
            continue
        if s in quote_types:
            if inquote is None:
                inquote = s
            elif inquote == s:
                inquote = None
            next_item += s
            continue
        if inquote:
            next_item += s
            continue
        if s in open:
            depth[s] += 1
            next_item += s
            if first is None:
                first = s
                pre += next_item
                next_item = ""
        else:
            if s in close:
                matching_open = matching[s]
                depth[matching_open] -= 1
                if matching_open == first and depth[matching_open] == 0:
                    if next_item:
                        contents.append(next_item)
                    return pre, contents, "".join(splits[i:])
            if (
                first
                and depth[first] == 1
                and "," in s
                and all(d == 0 for b, d in depth.items() if b != first)
            ):
                parts = [p.strip() for p in s.split(",")]
                if parts:
                    next_item += parts[0]
                    next_item = next_item.strip()
                    if next_item:
                        contents.append(next_item)
                    contents.extend(parts[1:-1])
                    next_item = parts[-1] if len(parts) > 1 else ""
                else:
                    next_item = ""
            else:
                next_item += s
    raise UnmatchedParensException(f"Unmatched parenthesis found in '{snippet}'")


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
    classes_to_include: ty.List[ty.Tuple[str, ty.Callable]] = attrs.field(factory=list)
    local_functions: ty.Set[ty.Callable] = attrs.field(factory=set)
    local_classes: ty.List[type] = attrs.field(factory=list)
    constants: ty.Set[ty.Tuple[str, str]] = attrs.field(factory=set)

    IGNORE_MODULES = [
        "traits.trait_handlers",  # Old traits module, pre v6.0
    ]

    def update(self, other: "UsedSymbols"):
        self.imports.update(other.imports)
        self.funcs_to_include.update(other.funcs_to_include)
        self.funcs_to_include.update((f.__name__, f) for f in other.local_functions)
        self.classes_to_include.extend(
            c for c in other.classes_to_include if c not in self.classes_to_include
        )
        self.classes_to_include.extend(
            (c.__name__, c)
            for c in other.local_classes
            if (c.__name__, c) not in self.classes_to_include
        )
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
        ]  # attrs is included in imports in case we reference attrs.NOTHING
        block = ""
        source_code = inspect.getsource(module)
        local_functions = get_local_functions(module)
        local_constants = get_local_constants(module)
        local_classes = get_local_classes(module)
        for line in source_code.split("\n"):
            if block:
                block += line.strip()
                if ")" in line:
                    imports.append(block)
                    block = ""
            elif re.match(r"^\s*(from[\w \.]+)?import\b[\w \.\,\(\)]+$", line):
                if "(" in line and ")" not in line:
                    block = line.strip()
                else:
                    imports.append(line.strip())
        # extract imported symbols from import statements
        symbols_re = re.compile(r"(?<!\"|')\b(\w+)\b(?!\"|')")
        comments_re = re.compile(r"\s*#.*")
        used_symbols = set()
        for function_body in function_bodies:
            # Strip comments from function body
            function_body = comments_re.sub("", function_body)
            used_symbols.update(symbols_re.findall(function_body))
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
                    func_body = comments_re.sub("", func_body)
                    local_func_symbols = symbols_re.findall(func_body)
                    used_symbols.update(local_func_symbols)
                    new_symbols = True
            for local_class in local_classes:
                if (
                    local_class.__name__ in used_symbols
                    and local_class not in used.local_classes
                ):
                    if issubclass(local_class, (BaseInterface, TraitedSpec)):
                        continue
                    used.local_classes.append(local_class)
                    class_body = inspect.getsource(local_class)
                    bases = extract_args(class_body)[1]
                    used_symbols.update(bases)
                    class_body = comments_re.sub("", class_body)
                    local_class_symbols = symbols_re.findall(class_body)
                    used_symbols.update(local_class_symbols)
                    new_symbols = True
            for const_name, const_def in local_constants:
                if (
                    const_name in used_symbols
                    and (const_name, const_def) not in used.constants
                ):
                    used.constants.add((const_name, const_def))
                    const_def_symbols = symbols_re.findall(const_def)
                    used_symbols.update(const_def_symbols)
                    new_symbols = True
        used_symbols -= set(cls.SYMBOLS_TO_IGNORE)

        pkg_name = module.__name__.split(".", 1)[0]

        def is_pkg_import(mod_name: str) -> bool:
            return mod_name.startswith(".") or mod_name.startswith(f"{pkg_name}.")

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
                match = re.match(r"\s*from ([\w\.]+)", base_stmt)
                import_mod = match.group(1) if match else ""
                if import_mod in cls.IGNORE_MODULES:
                    continue
                if import_mod:
                    if is_pkg_import(import_mod):
                        to_include = True
                        if import_mod.startswith("."):
                            match = re.match(r"(\.*)(.*)", import_mod)
                            mod_parts = module.__name__.split(".")
                            nparents = len(match.group(1))
                            if Path(module.__file__).stem == "__init__":
                                nparents -= 1
                            if nparents:
                                mod_parts = mod_parts[:-nparents]
                            mod_name = ".".join(mod_parts)
                            if match.group(2):
                                mod_name += "." + match.group(2)
                        elif import_mod.startswith("nipype."):
                            mod_name = import_mod
                        else:
                            assert False
                    else:
                        to_include = False
                        mod_name = import_mod
                    mod = import_module(mod_name)
                    # Filter out any interfaces that have been dragged in
                    used_parts = [
                        p
                        for p in used_parts
                        if not (
                            (
                                inspect.isclass(getattr(mod, p[0]))
                                and issubclass(
                                    getattr(mod, p[0]), (BaseInterface, TraitedSpec)
                                )
                            )
                            or getattr(mod, p[0])
                            in (
                                Undefined,
                                isdefined,
                                traits_extension.File,
                                traits_extension.Directory,
                            )
                        )
                    ]
                    if not used_parts:
                        continue
                    if to_include:
                        mod_func_bodies = []
                        for used_part in used_parts:
                            atr = getattr(mod, used_part[0])
                            # Check that it is actually a local import
                            if (
                                inspect.isfunction(atr) or inspect.isclass(atr)
                            ) and not is_pkg_import(atr.__module__):
                                used.imports.add(
                                    f"from {atr.__module__} import "
                                    + " as ".join(used_part)
                                )
                            elif inspect.isfunction(atr):
                                used.funcs_to_include.add((used_part[-1], atr))
                                mod_func_bodies.append(inspect.getsource(atr))
                            elif inspect.isclass(atr):
                                if issubclass(atr, BaseInterface):
                                    # TODO: add warning here
                                    continue  # Don't include nipype interfaces as it gets silly
                                # We can't use a set here because we need to preserve the order
                                class_def = (used_part[-1], atr)
                                if class_def not in used.classes_to_include:
                                    used.classes_to_include.append(class_def)
                                class_body = extract_args(inspect.getsource(atr))[
                                    2
                                ].split("\n", 1)[1]
                                mod_func_bodies.append(class_body)
                        # Recursively include neighbouring objects imported in the module
                        if mod is not builtins:
                            used_in_mod = cls.find(
                                mod,
                                function_bodies=mod_func_bodies,
                            )
                            used.update(used_in_mod)
                    else:
                        used.imports.add(required_stmt)
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
    source_code = source_code.replace("\\\n", " ")
    parts = re.split(r"^(\w+) *= *", source_code, flags=re.MULTILINE)
    local_vars = []
    for attr_name, following in zip(parts[1::2], parts[2::2]):
        first_line = following.splitlines()[0]
        if ("(" in first_line and ")" not in first_line) or (
            "[" in first_line and "]" not in first_line
        ):
            pre, args, post = extract_args(following)
            local_vars.append(
                (attr_name, pre + re.sub(r"\n *", "", ", ".join(args)) + post[0])
            )
        else:
            local_vars.append((attr_name, first_line))
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
    if re.match(r"(\s*#.*\n)?(\s*@.*\n)*\s*(def|class)\s+", function_body):
        with_signature = True
    else:
        with_signature = False
    # Detect the indentation of the source code in src and reduce it to 4 spaces
    indents = re.findall(r"^( *)[^\s].*\n", function_body, flags=re.MULTILINE)
    min_indent = min(len(i) for i in indents) if indents else 0
    indent_reduction = min_indent - (0 if with_signature else 4)
    assert indent_reduction >= 0, (
        "Indentation reduction cannot be negative, probably didn't detect signature of "
        f"method correctly:\n{function_body}"
    )
    if indent_reduction:
        function_body = re.sub(
            r"^" + " " * indent_reduction, "", function_body, flags=re.MULTILINE
        )
    # Other misc replacements
    # function_body = function_body.replace("LOGGER.", "logger.")
    parts = re.split(r"not isdefined\b", function_body, flags=re.MULTILINE)
    new_function_body = parts[0]
    for part in parts[1:]:
        pre, args, post = extract_args(part)
        new_function_body += pre + f"{args[0]} is attrs.NOTHING" + post
    function_body = new_function_body
    parts = re.split(r"isdefined\b", function_body, flags=re.MULTILINE)
    new_function_body = parts[0]
    for part in parts[1:]:
        pre, args, post = extract_args(part)
        assert len(args) == 1, f"Unexpected number of arguments in isdefined: {args}"
        new_function_body += pre + f"{args[0]} is not attrs.NOTHING" + post
    function_body = new_function_body
    function_body = function_body.replace("_Undefined", "attrs.NOTHING")
    function_body = function_body.replace("Undefined", "attrs.NOTHING")
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
    pre, args, post = extract_args(snippet)
    if "runtime" in args:
        args.remove("runtime")
    return pre + ", ".join(args + new_args) + post


def get_source_code(func_or_klass: ty.Union[ty.Callable, ty.Type]) -> str:
    """Get the source code of a function or class, including a comment with the
    original source location
    """
    src = inspect.getsource(func_or_klass)
    line_number = inspect.getsourcelines(func_or_klass)[1]
    module = inspect.getmodule(func_or_klass)
    rel_module_path = os.path.sep.join(
        module.__name__.split(".")[1:-1] + [Path(module.__file__).name]
    )
    install_placeholder = f"<{module.__name__.split('.', 1)[0]}-install>"
    indent = re.match(r"^(\s*)", src).group(1)
    comment = (
        f"{indent}# Original source at L{line_number} of "
        f"{install_placeholder}{os.path.sep}{rel_module_path}\n"
    )
    return comment + src
