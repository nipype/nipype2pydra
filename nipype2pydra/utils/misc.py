import traceback
import typing as ty
from types import ModuleType
import sys
import types
import re
import os
import inspect
from contextlib import contextmanager
from pathlib import Path
from fileformats.core import FileSet, from_mime
from fileformats.core.mixin import WithClassifiers
from ..exceptions import (
    UnmatchedParensException,
    UnmatchedQuoteException,
)

try:
    from typing import GenericAlias
except ImportError:
    from typing import _GenericAlias as GenericAlias

from importlib import import_module
from logging import getLogger


logger = getLogger("nipype2pydra")


T = ty.TypeVar("T")


INBUILT_NIPYPE_TRAIT_NAMES = [
    "__all__",
    "args",
    "trait_added",
    "trait_modified",
    "environ",
    "output_type",
]


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


def full_address(func_or_class: ty.Union[ty.Type, types.FunctionType]) -> str:
    """Get the location of a function or class in the format `module.object_name`"""
    if not (inspect.isclass(func_or_class) or inspect.isfunction(func_or_class)):
        raise ValueError(f"Input must be a class or function, not {func_or_class}")
    return f"{func_or_class.__module__}.{func_or_class.__name__}"


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
    """Splits the code snippet at the first opening brackets into a 3-tuple
    consisting of the preceding text + opening bracket, the arguments/items
    within the parenthesis/bracket pair, and the closing paren/bracket + trailing text.

    Quotes and escaped characters are handled correctly, and the function can be used
    to split on either parentheses, braces or square brackets. The only limitation is
    that raw strings with special charcters are not supported.

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
        r"(\(|\)|\[|\]|\{|\}|'|\"|\\\(|\\\)|\\\[|\\\]|\\'|\\\")",
        snippet,
        flags=re.MULTILINE | re.DOTALL,
    )
    if len(splits) == 1:
        return splits[0], None, None
    quote_types = ["'", '"']
    pre = splits[0]
    if pre and "#" in pre.splitlines()[-1]:
        lines = pre.splitlines()
        # Quote or bracket in inline comment
        return "\n".join(lines[:-1]) + "\n" + lines[-1].split("#")[0], None, None
    contents = []
    bracket_types = {")": "(", "]": "[", "}": "{"}
    open = list(bracket_types.values())
    close = list(bracket_types.keys())
    depth = {p: 0 for p in open}
    next_item = splits[1]
    first = None
    in_quote = None
    in_tripple_quote = None
    if next_item in quote_types:
        in_quote = next_item
    elif not next_item.startswith("\\"):  # paren/bracket
        first = next_item
        pre += first
        next_item = ""
        depth[first] += 1  # Open the first bracket/parens type
    for i, s in enumerate(splits[2:], start=2):
        if not s:
            continue
        if s[0] == "\\":
            next_item += s
            continue
        if s in quote_types:
            next_item += s
            tripple_quote = (
                next_item[-3:]
                if next_item[-3:] == s * 3
                and not (len(next_item) >= 4 and next_item[-4] == "\\")
                else None
            )
            if in_tripple_quote:
                if in_tripple_quote == tripple_quote:
                    in_tripple_quote = None
            elif tripple_quote:
                in_tripple_quote = tripple_quote
            elif in_quote is None:
                in_quote = s
            elif in_quote == s:
                in_quote = None
            continue
        if in_quote or in_tripple_quote:
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
                matching_open = bracket_types[s]
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
    if in_quote or in_tripple_quote:
        raise UnmatchedQuoteException(
            f"Unmatched quote ({in_quote}) found in '{snippet}'"
        )
    if first is None:
        return pre + next_item, None, None
    raise UnmatchedParensException(
        f"Unmatched brackets ('{first}') found in '{snippet}'"
    )


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
    non_empty_lines = [ln for ln in function_body.splitlines() if ln]
    indent_size = len(re.match(r"^( *)", non_empty_lines[0]).group(1))
    indent_reduction = indent_size - (0 if with_signature else 4)
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
    return replace_undefined(function_body)


def replace_undefined(function_body: str) -> str:
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
    function_body = function_body.replace("Undefined", "type(attrs.NOTHING)")
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


def split_source_into_statements(source_code: str) -> ty.List[str]:
    """Splits a source code string into individual statements

    Parameters
    ----------
    source_code: str
        the source code to split

    Returns
    -------
    list[str]
        the split source code
    """
    source_code = source_code.replace("\\\n", " ")  # strip out line breaks
    lines = source_code.splitlines()
    statements = []
    current_statement = None
    for line in lines:
        if re.match(r"\s*#.*", line):
            if not current_statement:  # drop within-statement comments
                statements.append(line)
        elif current_statement or re.match(r".*[\(\[\{\"'].*", line):
            if current_statement:
                current_statement += "\n" + line
            else:
                current_statement = line
            try:
                _, __, post = extract_args(current_statement)
            except (UnmatchedParensException, UnmatchedQuoteException):
                continue
            else:
                # Handle dictionary assignments where the first open-closing bracket is
                # before the assignment, e.g. outputs["out_file"] = [..."
                if post and re.match(r"\s*=", post[1:]):
                    try:
                        extract_args(post[1:])
                    except (UnmatchedParensException, UnmatchedQuoteException):
                        continue
                statements.append(current_statement)
                current_statement = None
        else:
            statements.append(line)
    return statements


def multiline_comment(comment: str, line_length: int = 100) -> str:
    """Convert a comment string to a multiline comment block of width `line_length`"""
    multiline = ""
    start_of_line = 0
    for end_of_line in range(line_length, len(comment), line_length):
        multiline += "# " + comment[start_of_line:end_of_line] + "\n"
        start_of_line = end_of_line
    multiline += "# " + comment[start_of_line:] + "\n"
    return multiline


def from_dict_converter(
    obj: ty.Union[T, dict], klass: ty.Type[T], allow_none=False
) -> T:
    if obj is None:
        if allow_none:
            converted = None
        else:
            converted = klass()
    elif isinstance(obj, dict):
        converted = klass(**obj)
    elif isinstance(obj, klass):
        converted = obj
    else:
        raise TypeError(
            f"Input must be of type {klass} or dict, not {type(obj)}: {obj}"
        )
    return converted


def from_named_dicts_converter(
    dct: ty.Optional[ty.Dict[str, ty.Union[T, dict]]],
    klass: ty.Type[T],
    allow_none=False,
) -> ty.Dict[str, T]:
    converted = {}
    for name, conv in (dct or {}).items():
        if isinstance(conv, dict):
            conv = klass(name=name, **conv)
        converted[name] = conv
    return converted


def str_to_type(type_str: str) -> type:
    """Resolve a string representation of a type into a valid type"""
    if "/" in type_str:
        tp = from_mime(type_str)
        try:
            # If datatype is a field, use its primitive instead
            tp = tp.primitive  # type: ignore
        except AttributeError:
            pass
    else:

        def resolve_type(type_str: str) -> type:
            if "." in type_str:
                parts = type_str.split(".")
                module = import_module(".".join(parts[:-1]))
                class_str = parts[-1]
            else:
                class_str = type_str
                module = None
            match = re.match(r"(\w+)(\[.*\])?", class_str)
            class_str = match.group(1)
            if module:
                t = getattr(module, match.group(1))
            else:
                if not re.match(r"^\w+$", class_str):
                    raise ValueError(f"Cannot parse {class_str} to a type safely")
                t = eval(class_str)
            if match.group(2):
                args = tuple(
                    resolve_type(arg) for arg in match.group(2)[1:-1].split(",")
                )
                t = t.__getitem__(args)
            return t

        tp = resolve_type(type_str)
        if not inspect.isclass(tp) and type(tp).__module__ != "typing":
            raise TypeError(f"Designated type at {type_str} is not a class {tp}")
    return tp


def types_converter(types: ty.Dict[str, ty.Union[str, type]]) -> ty.Dict[str, type]:
    if types is None:
        return {}
    converted = {}
    for name, tp_or_str in types.items():
        if isinstance(tp_or_str, str):
            tp = str_to_type(tp_or_str)
        converted[name] = tp
    return converted


def unwrap_nested_type(t: type) -> ty.List[type]:
    if issubclass(t, WithClassifiers) and t.is_classified:
        unwrapped = [t.unclassified]
        for c in t.classifiers:
            unwrapped.extend(unwrap_nested_type(c))
        return unwrapped
    return [t]
