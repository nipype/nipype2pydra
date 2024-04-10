import traceback
import typing as ty
from types import ModuleType
import sys
import re
import os
from copy import deepcopy
import keyword
import inspect
import builtins
from functools import cached_property
from operator import itemgetter, attrgetter
from contextlib import contextmanager
import attrs
from pathlib import Path
from fileformats.core import FileSet
from .exceptions import (
    UnmatchedParensException,
    UnmatchedQuoteException,
)
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


@attrs.define
class Imported:
    """
    A class to hold a reference to an imported object within an import statement

    Parameters
    ----------
    name : str
        the name of the object being imported
    alias : str, optional
        the alias of the object, by default None
    """

    name: str = attrs.field()
    alias: ty.Optional[str] = attrs.field(default=None)
    statement: "ImportStatement" = attrs.field(eq=False, default=None)

    def __str__(self):
        if self.alias:
            return f"{self.name} as {self.alias}"
        return self.name

    def __hash__(self):
        return hash(str(self))

    @property
    def local_name(self):
        return self.alias if self.alias else self.name

    @cached_property
    def object(self) -> object:
        """Import and return the actual object being imported in the statement"""
        if self.statement.from_:
            try:
                return getattr(self.statement.module, self.name)
            except AttributeError:
                raise ImportError(
                    f"Did not find {self.name} object in {self.statement.module_name} module"
                ) from None
        else:
            return import_module(self.name)

    @property
    def module_name(self) -> str:
        """Get the true module name of the object being imported, i.e. guards against
        chained imports where an object is imported into one module and then re-imported
        into a second

        Returns
        -------
        str
            the true module name of the object being imported
        """
        if inspect.isclass(self.object) or inspect.isfunction(self.object):
            return self.object.__module__
        return self.statement.module_name

    def in_package(self, pkg: str) -> bool:
        """Check if the import is relative to the given package"""
        pkg = pkg + "." if pkg else ""
        return self.module_name.startswith(pkg)

    def as_independent_statement(self) -> "ImportStatement":
        """Return a new import statement that only includes this object as an import"""
        statement_cpy = deepcopy(self.statement)
        statement_cpy.imported = {self.alias: self}
        statement_cpy.from_ = self.module_name
        return statement_cpy


@attrs.define
class ImportStatement:
    """
    A class to hold an import statement

    Parameters
    ----------
    indent : str
        the indentation of the import statement
    imported : list[ImportObject]
        the objects being imported
    from_ : str, optional
        the module being imported from, by default None
    """

    indent: str = attrs.field()
    imported: ty.Dict[str, Imported] = attrs.field(
        converter=lambda d: dict(sorted(d.items(), key=itemgetter(0)))
    )
    relative_to: ty.Optional[str] = attrs.field(default=None)
    from_: ty.Optional[str] = attrs.field(default=None)

    def __hash__(self):
        return hash(str(self))

    @indent.validator
    def _indent_validator(self, _, value):
        if not re.match(r"^\s*$", value):
            raise ValueError("Indentation must be whitespace")

    def __attrs_post_init__(self):
        for imp in self.imported.values():
            imp.statement = self

    def __getitem__(self, key):
        return self.imported[key]

    def __contains__(self, key):
        return key in self.imported

    def __iter__(self):
        return iter(self.imported)

    def __bool__(self):
        return bool(self.imported)

    def keys(self):
        return self.imported.keys()

    def values(self):
        return self.imported.values()

    def items(self):
        return self.imported.items()

    match_re = re.compile(
        r"^(\s*)(from[\w \.]+)?import\b([\w \n\.\,\(\)]+)$",
        flags=re.MULTILINE | re.DOTALL,
    )

    def __str__(self):
        imported_str = ", ".join(str(i) for i in self.imported.values())
        if self.from_:
            return f"{self.indent}from {self.from_} import {imported_str}"
        return f"{self.indent}import {imported_str}"

    def __lt__(self, other: "ImportStatement") -> bool:
        """Used for sorting imports"""
        if self.from_ and other.from_:
            return self.from_ < other.from_
        elif not self.from_ and not other.from_:
            return self.module_name < other.module_name
        elif not self.from_:
            return True
        else:
            assert not other.from_
            return False

    @classmethod
    def parse(
        cls, stmt: str, relative_to: ty.Union[str, ModuleType, None] = None
    ) -> "ImportStatement":
        """Parse an import statement from a string

        Parameters
        ----------
        stmt : str
            the import statement to parse
        relative_to : str | ModuleType
            the module to resolve relative imports against
        """
        if isinstance(relative_to, ModuleType):
            relative_to = relative_to.__name__
        match = cls.match_re.match(stmt.replace("\n", " "))
        import_str = match.group(3).strip()
        if import_str.startswith("("):
            assert import_str.endswith(")")
            import_str = import_str[1:-1].strip()
            if import_str.endswith(","):
                import_str = import_str[:-1]
        imported = {}
        for obj in re.split(r" *, *", import_str):
            parts = [p.strip() for p in re.split(r" +as +", obj)]
            if len(parts) > 1:
                imported[parts[1]] = Imported(name=parts[0], alias=parts[1])
            else:
                imported[obj] = Imported(name=obj)
        if match.group(2):
            from_ = match.group(2)[len("from ") :].strip()
            if from_.startswith(".") and relative_to is None:
                raise ValueError(
                    f"Relative import statement '{stmt}' without relative_to module "
                    "provided"
                )
        else:
            from_ = None
        return ImportStatement(
            indent=match.group(1),
            from_=from_,
            relative_to=relative_to,
            imported=imported,
        )

    @classmethod
    def from_object(cls, obj) -> "ImportStatement":
        """Create an import statement from an object"""
        if inspect.ismodule(obj):
            return ImportStatement(indent="", imported={}, from_=obj.__name__)
        return ImportStatement(
            indent="",
            from_=obj.__module__,
            imported={object.__name__: Imported(name=obj.__name__)},
        )

    @property
    def module_name(self) -> str:
        if not self.from_:
            return next(iter(self.imported.values())).name
        if self.is_relative:
            return self.join_relative_package(self.relative_to, self.from_)
        return self.from_

    @cached_property
    def module(self) -> ModuleType:
        return import_module(self.module_name)

    @property
    def conditional(self) -> bool:
        return len(self.indent) > 0

    @classmethod
    def matches(self, stmt: str) -> bool:
        return bool(self.match_re.match(stmt))

    def drop(self, imported: ty.Union[str, Imported]):
        """Drop an object from the import statement"""
        if isinstance(imported, Imported):
            imported = imported.local_name
        del self.imported[imported]

    @property
    def is_relative(self) -> bool:
        return self.from_ and self.from_.startswith(".")

    def only_include(self, aliases: ty.Iterable[str]) -> ty.Optional["ImportStatement"]:
        """Filter the import statement to only include ones that are present in the
        given aliases

        Parameters
        ----------
        aliases : list[str]
            the aliases to filter by
        """
        objs = {n: o for n, o in self.imported.items() if n in aliases}
        if not objs:
            return None
        return ImportStatement(
            indent=self.indent,
            imported=objs,
            from_=self.from_,
            relative_to=self.relative_to,
        )

    def in_package(self, pkg: str) -> bool:
        """Check if the import is relative to the given package"""
        if not self.from_:
            assert len(self.imported) == 1
            imported = next(iter(self.imported.values()))
            module = imported.name
        else:
            module = self.from_
        pkg = pkg + "." if pkg else ""
        return module.startswith(pkg)

    def translate_to(
        self, from_pkg: ty.Union[str, ModuleType], to_pkg: ty.Union[str, ModuleType]
    ) -> "ImportStatement":
        """Translates the import statement from one package to another

        Parameters
        ----------
        from_pkg : str | ModuleType
            the package to translate from
        to_pkg : str | ModuleType
            the package to translate to

        Returns
        -------
        ImportStatement
            the translated import statement
        """
        cpy = deepcopy(self)
        if not self.from_:
            return cpy
        new_from = self.join_relative_package(
            to_pkg, self.get_relative_package(self.module_name, from_pkg)
        )
        if self.relative_to:
            new_relative_to = self.join_relative_package(
                to_pkg, self.get_relative_package(self.relative_to, from_pkg)
            )
            new_from = self.get_relative_package(new_from, new_relative_to)
        else:
            new_relative_to = None
        cpy.from_ = new_from
        cpy.relative_to = new_relative_to
        return cpy

    @classmethod
    def get_relative_package(
        cls,
        target: ty.Union[ModuleType, str],
        reference: ty.Union[ModuleType, str],
    ) -> str:
        """Get the relative package path from one module to another

        Parameters
        ----------
        target : ModuleType
            the module to get the relative path to
        reference : ModuleType
            the module to get the relative path from

        Returns
        -------
        str
            the relative package path
        """
        if isinstance(target, ModuleType):
            target = target.__name__
        if isinstance(reference, ModuleType):
            reference = reference.__name__
        ref_parts = reference.split(".")
        target_parts = target.split(".")
        common = 0
        for mod, targ in zip(ref_parts, target_parts):
            if mod == targ:
                common += 1
            else:
                break
        if common == 0:
            return target
        return ".".join([""] * (len(ref_parts) - common) + target_parts[common:])

    @classmethod
    def join_relative_package(cls, base_package: str, relative_package: str) -> str:
        """Join a base package with a relative package path

        Parameters
        ----------
        base_package : str
            the base package to join with
        relative_package : str
            the relative package path to join

        Returns
        -------
        str
            the joined package path
        """
        if not relative_package.startswith("."):
            return relative_package
        parts = base_package.split(".")
        rel_pkg_parts = relative_package.split(".")
        if relative_package.endswith("."):
            rel_pkg_parts = rel_pkg_parts[:-1]
        preceding = True
        for part in rel_pkg_parts:
            if part == "":  # preceding "." in relative path
                if not preceding:
                    raise ValueError(
                        f"Invalid relative package path {relative_package}"
                    )
                parts.pop()
            else:
                preceding = False
                parts.append(part)
        return ".".join(parts)

    @classmethod
    def collate(
        cls, statements: ty.Iterable["ImportStatement"]
    ) -> ty.List["ImportStatement"]:
        """Collate a list of import statements into a list of unique import statements

        Parameters
        ----------
        statements : list[ImportStatement]
            the import statements to collate

        Returns
        -------
        list[ImportStatement]
            the collated import statements
        """
        from_stmts: ty.Dict[str, ImportStatement] = {}
        mod_stmts = set()
        for stmt in statements:
            if stmt.from_:
                if stmt.from_ in from_stmts:
                    prev = from_stmts[stmt.from_]
                    for imported in stmt.values():
                        try:
                            prev_imported = prev[imported.local_name]
                        except KeyError:
                            pass
                        else:
                            if prev_imported.name != imported.name:
                                raise ValueError(
                                    f"Conflicting imports from {stmt.from_}: "
                                    f"{prev_imported.name} and {imported.name} both "
                                    f"aliased as {imported.local_name}"
                                )
                        prev.imported[imported.local_name] = imported
                else:
                    from_stmts[stmt.from_] = stmt
            else:
                mod_stmts.add(stmt)
        return sorted(
            list(from_stmts.values()) + list(mod_stmts), key=attrgetter("module_name")
        )


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


@attrs.define
class UsedSymbols:
    """
    A class to hold the used symbols in a module

    Parameters
    -------
    imports : list[str]
        the import statements that need to be included in the converted file
    intra_pkg_funcs: list[tuple[str, callable]]
        list of functions that are defined in neighbouring modules that need to be
        included in the converted file (as opposed of just imported from independent
        packages) along with the name that they were imported as and therefore should
        be named as in the converted module if they are included inline
    intra_pkg_classes
        like neigh_mod_funcs but classes
    local_functions: set[callable]
        locally-defined functions used in the function bodies, or nested functions thereof
    local_classes : set[type]
        like local_functions but classes
    constants: set[tuple[str, str]]
        constants used in the function bodies, or nested functions thereof, tuples consist
        of the constant name and its definition
    """

    imports: ty.Set[str] = attrs.field(factory=set)
    intra_pkg_funcs: ty.Set[ty.Tuple[str, ty.Callable]] = attrs.field(factory=set)
    intra_pkg_classes: ty.List[ty.Tuple[str, ty.Callable]] = attrs.field(factory=list)
    local_functions: ty.Set[ty.Callable] = attrs.field(factory=set)
    local_classes: ty.List[type] = attrs.field(factory=list)
    constants: ty.Set[ty.Tuple[str, str]] = attrs.field(factory=set)

    IGNORE_MODULES = [
        "traits.trait_handlers",  # Old traits module, pre v6.0
    ]

    def update(self, other: "UsedSymbols"):
        self.imports.update(other.imports)
        self.intra_pkg_funcs.update(other.intra_pkg_funcs)
        self.intra_pkg_funcs.update((f.__name__, f) for f in other.local_functions)
        self.intra_pkg_classes.extend(
            c for c in other.intra_pkg_classes if c not in self.intra_pkg_classes
        )
        self.intra_pkg_classes.extend(
            (c.__name__, c)
            for c in other.local_classes
            if (c.__name__, c) not in self.intra_pkg_classes
        )
        self.constants.update(other.constants)

    DEFAULT_FILTERED_OBJECTS = (
        Undefined,
        isdefined,
        traits_extension.File,
        traits_extension.Directory,
    )

    @classmethod
    def find(
        cls,
        module,
        function_bodies: ty.List[ty.Union[str, ty.Callable, ty.Type]],
        collapse_intra_pkg: bool = True,
        pull_out_inline_imports: bool = True,
        filter_objs: ty.Sequence = DEFAULT_FILTERED_OBJECTS,
        filter_classes: ty.Optional[ty.List[ty.Type]] = None,
    ) -> "UsedSymbols":
        """Get the imports and local functions/classes/constants referenced in the
        provided function bodies, and those nested within them

        Parameters
        ----------
        module: ModuleType
            the module containing the functions to be converted
        function_bodies: list[str | callable | type]
            the source of all functions/classes (or the functions/classes themselves)
            that need to be checked for used imports
        collapse_intra_pkg : bool
            whether functions and classes defined within the same package, but not the
            same module, are to be included in the output module or not, i.e. whether
            the local funcs/classes/constants they referenced need to be included also
        pull_out_inline_imports : bool, optional
            whether to pull out imports that are inline in the function bodies
            or not, by default True
        filtered_classes : list[type], optional
            a list of classes (including subclasses) to filter out from the used symbols,
            by default None
        filtered_objs : list[type], optional
            a list of objects (including subclasses) to filter out from the used symbols,
            by default (Undefined,
                            isdefined,
                            traits_extension.File,
                            traits_extension.Directory,
                        )

        Returns
        -------
        UsedSymbols
            a class containing the used symbols in the module
        """
        used = cls()
        source_code = inspect.getsource(module)
        local_functions = get_local_functions(module)
        local_constants = get_local_constants(module)
        local_classes = get_local_classes(module)
        module_statements = split_source_into_statements(source_code)
        imports: ty.List[ImportStatement] = [
            ImportStatement.parse("import attrs"),
            ImportStatement.parse("from fileformats.generic import File, Directory"),
            ImportStatement.parse("import logging"),
        ]  # attrs is included in imports in case we reference attrs.NOTHING
        global_scope = True
        for stmt in module_statements:
            if not pull_out_inline_imports:
                if stmt.startswith("def ") or stmt.startswith("class "):
                    global_scope = False
                    continue
                if not global_scope:
                    if stmt and not stmt.startswith(" "):
                        global_scope = True
                    else:
                        continue
            if ImportStatement.matches(stmt):
                imports.append(ImportStatement.parse(stmt, relative_to=module))
        symbols_re = re.compile(r"(?<!\"|')\b(\w+)\b(?!\"|')")

        def get_symbols(func: ty.Union[str, ty.Callable, ty.Type]):
            """Get the symbols used in a function body"""
            try:
                fbody = inspect.getsource(func)
            except TypeError:
                fbody = func
            for stmt in split_source_into_statements(fbody):
                if stmt and not re.match(r"\s*(#|\"|')", stmt):  # skip comments/docs
                    used_symbols.update(symbols_re.findall(stmt))

        used_symbols = set()
        for function_body in function_bodies:
            get_symbols(function_body)

        # Keep stepping into nested referenced local function/class sources until all local
        # functions and constants that are referenced are added to the used symbols
        prev_num_symbols = -1
        while len(used_symbols) > prev_num_symbols:
            prev_num_symbols = len(used_symbols)
            for local_func in local_functions:
                if (
                    local_func.__name__ in used_symbols
                    and local_func not in used.local_functions
                ):
                    used.local_functions.add(local_func)
                    get_symbols(local_func)
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
                    get_symbols(class_body)
            for const_name, const_def in local_constants:
                if (
                    const_name in used_symbols
                    and (const_name, const_def) not in used.constants
                ):
                    used.constants.add((const_name, const_def))
                    get_symbols(const_def)
            used_symbols -= set(cls.SYMBOLS_TO_IGNORE)

        base_pkg = module.__name__.split(".")[0]

        # functions to copy from a relative or nipype module into the output module
        for stmt in imports:
            stmt = stmt.only_include(used_symbols)
            # Skip if no required symbols are in the import statement
            if not stmt:
                continue
            # Filter out Nipype specific modules and the module itself
            if stmt.module_name in cls.IGNORE_MODULES + [module.__name__]:
                continue
            # Filter out Nipype specific classes that are relevant in Pydra
            if filter_classes or filter_objs:
                to_include = []
                for imported in stmt.values():
                    try:
                        obj = imported.object
                    except ImportError:
                        logger.warning(
                            (
                                "Could not import %s from %s, unable to check whether "
                                "it is is present in list of classes %s or objects %s "
                                "to be filtered out"
                            ),
                            imported.name,
                            imported.statement.module_name,
                            filter_classes,
                            filter_objs,
                        )
                        continue
                    if filter_classes and inspect.isclass(obj):
                        if issubclass(obj, filter_classes):
                            continue
                    elif filter_objs and obj in filter_objs:
                        continue
                    to_include.append(imported.local_name)
                if not to_include:
                    continue
                stmt = stmt.only_include(to_include)
            if stmt.in_package(base_pkg):
                inlined_objects = []
                for imported in list(stmt.values()):
                    if not imported.in_package(base_pkg):
                        # Case where an object is a nested import from a different package
                        # which is imported from a neighbouring module
                        used.imports.add(imported.as_independent_statement())
                        stmt.drop(imported)
                    elif inspect.isfunction(imported.object):
                        used.intra_pkg_funcs.add((imported.local_name, imported.object))
                        if collapse_intra_pkg:
                            # Recursively include objects imported in the module
                            # by the inlined function
                            inlined_objects.append(imported.object)
                    elif inspect.isclass(imported.object):
                        class_def = (imported.local_name, imported.object)
                        # Add the class to the intra_pkg_classes list if it is not
                        # already there. NB: we can't use a set for intra_pkg_classes
                        # like we did for functions here because we need to preserve the
                        # order the classes are defined in the module in case one inherits
                        # from the other
                        if class_def not in used.intra_pkg_classes:
                            used.intra_pkg_classes.append(class_def)
                        if collapse_intra_pkg:
                            # Recursively include objects imported in the module
                            # by the inlined class
                            inlined_objects.append(
                                extract_args(inspect.getsource(imported.object))[
                                    2
                                ].split("\n", 1)[1]
                            )

                # Recursively include neighbouring objects imported in the module
                if inlined_objects:
                    used_in_mod = cls.find(
                        stmt.module,
                        function_bodies=inlined_objects,
                    )
                    used.update(used_in_mod)
            used.imports.add(stmt)
        return used

    # Nipype-specific names and Python keywords
    SYMBOLS_TO_IGNORE = ["isdefined"] + keyword.kwlist + list(builtins.__dict__.keys())


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
        if re.match(r".*(\[|\(|\{)", first_line):
            pre, args, post = extract_args(following)
            if args:
                local_vars.append(
                    (attr_name, pre + re.sub(r"\n *", "", ", ".join(args)) + post[0])
                )
            else:
                local_vars.append((attr_name, first_line))
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
        elif current_statement or re.match(r".*[\(\[\"'].*", line):
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
