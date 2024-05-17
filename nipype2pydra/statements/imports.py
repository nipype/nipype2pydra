import typing as ty
from types import ModuleType
import re
from copy import deepcopy
import inspect
from functools import cached_property
from operator import itemgetter, attrgetter
import attrs
from ..utils import from_dict_converter


from importlib import import_module
from logging import getLogger


logger = getLogger("nipype2pydra")


@attrs.define(slots=False)
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

    def __lt__(self, other: "Imported") -> bool:
        return self.name < other.name

    @property
    def local_name(self):
        return self.alias if self.alias else self.name

    @property
    def address(self):
        return f"{self.module_name}.{self.name}"

    @property
    def object(self) -> object:
        """Import and return the actual object being imported in the statement"""
        if self.statement.from_:
            try:
                return getattr(self.statement.module, self.name)
            except AttributeError:
                try:
                    return import_module(self.statement.from_ + "." + self.name)
                except ImportError:
                    pass
                raise ImportError(
                    f"Did not find {self.name} object in {self.statement.module_name} "
                    "module"
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
        elif inspect.ismodule(self.object):
            return self.object.__name__
        return self.statement.module_name

    def in_package(self, pkg: str) -> bool:
        """Check if the import is relative to the given package"""
        return self.module_name == pkg or self.module_name.startswith(pkg + ".")

    def as_independent_statement(self, resolve: bool = False) -> "ImportStatement":
        """Return a new import statement that only includes this object as an import

        Parameters
        ----------
        resolve : bool
        """
        stmt_cpy = deepcopy(self.statement)
        stmt_cpy.imported = {self.local_name: stmt_cpy[self.local_name]}
        if resolve:
            if inspect.ismodule(self.object):
                module_name = self.object.__name__
            else:
                module_name = self.object.__module__
                if inspect.isbuiltin(self.object):
                    module_name = module_name[1:]  # strip preceding '_' from builtins
        if module_name != stmt_cpy.from_:
            stmt_cpy.from_ = module_name
            if (
                stmt_cpy.translation
                and stmt_cpy.from_.split(".")[0] != module_name.split(".")[0]
            ):
                stmt_cpy.translation = None
                logger.warning(
                    "Dropping translation from '%s' to '%s' for %s import",
                    stmt_cpy.translation,
                    stmt_cpy.from_,
                    self.name,
                )
        return stmt_cpy


@attrs.define(slots=False)
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
    relative_to : str, optional
        the module to resolve relative imports against, by default None
    translation : str, optional
        the translation to apply to the import statement, by default None
    """

    indent: str = attrs.field()
    imported: ty.Dict[str, Imported] = attrs.field(
        converter=lambda d: dict(sorted(d.items(), key=itemgetter(0)))
    )
    from_: ty.Optional[str] = attrs.field(default=None)
    relative_to: ty.Optional[str] = attrs.field(default=None)
    translation: ty.Optional[str] = attrs.field(default=None)

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

    def in_global_scope(self) -> "ImportStatement":
        """Return a new import statement that is in the global scope"""
        return ImportStatement(
            indent="",
            imported=self.imported,
            from_=self.from_,
            relative_to=self.relative_to,
            translation=self.translation,
        )

    def absolute(self) -> "ImportStatement":
        """Return a new import statement that is absolute"""
        from_ = (
            self.join_relative_package(self.relative_to, self.from_)
            if self.from_
            else None
        )
        return ImportStatement(
            indent=self.indent,
            imported=self.imported,
            from_=from_,
            relative_to=None,
            translation=self.translation,
        )

    match_re = re.compile(
        r"^(\s*)(from[\w \.]+)?import\b([\w \n\.\,\(\)]+)(?:#.*)?$",
        flags=re.MULTILINE | re.DOTALL,
    )

    def __str__(self):
        if self.from_:
            imported_str = ", ".join(str(i) for i in sorted(self.imported.values()))
            module = self.translation if self.translation else self.from_
            stmt_str = f"{self.indent}from {module} import {imported_str}"
        elif self.translation:
            stmt_str = f"{self.indent}import {self.translation}"
            if self.sole_imported.alias:
                stmt_str += f" as {self.sole_imported.alias}"
        else:
            stmt_str = f"{self.indent}import {self.sole_imported}"
        return stmt_str

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

    @property
    def sole_imported(self) -> Imported:
        """Get the sole imported object in the statement"""
        if self.from_:
            raise ValueError(
                f"'from <module> import ...' statements ('{self!r}') do not "
                "necessarily have a sole import"
            )
        assert len(self.imported) == 1
        return next(iter(self.imported.values()))

    @classmethod
    def from_object(cls, obj) -> "ImportStatement":
        """Create an import statement from an object"""
        if inspect.ismodule(obj):
            return ImportStatement(indent="", imported={}, from_=obj.__name__)
        module_name = obj.__module__
        if module_name.startswith("fileformats."):
            module_name = ".".join(module_name.split(".")[:2])
        return ImportStatement(
            indent="",
            from_=module_name,
            imported={obj.__name__: Imported(name=obj.__name__)},
        )

    @property
    def module_name(self) -> str:
        if not self.from_:
            return self.sole_imported.name
        if self.is_relative:
            return self.join_relative_package(self.relative_to, self.from_)
        return self.from_

    @property
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
            translation=self.translation,
        )

    def in_package(self, pkg: str) -> bool:
        """Check if the import is relative to the given package"""
        return self.module_name == pkg or self.module_name.startswith(pkg + ".")

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
        self.translation = self.join_relative_package(
            to_pkg, self.get_relative_package(self.module_name, from_pkg)
        )

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
        relpath = ".".join([""] * (len(ref_parts) - common) + target_parts[common:])
        if not relpath.startswith("."):
            relpath = "." + relpath
        return relpath

    @classmethod
    def join_relative_package(cls, base_package: str, relative_package: str) -> str:
        """Join a base package with a relative package path

        Parameters
        ----------
        base_package : str
            the base package to join with
        relative_package : str
            the relative package path to join
        base_is_module : bool
            whether the base package is actually module instead of a package

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
        conditional_stmts = []
        for stmt in statements:
            if stmt.conditional:
                conditional_stmts.append(stmt)
            elif stmt.from_:
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
            list(from_stmts.values()) + list(mod_stmts) + conditional_stmts,
            key=attrgetter("module_name"),
        )


def parse_imports(
    stmts: ty.Union[str, ty.Sequence[str]],
    relative_to: ty.Union[str, ModuleType, None] = None,
    translations: ty.Sequence[ty.Tuple[str, str]] = (),
    absolute: bool = False,
) -> ty.List["ImportStatement"]:
    """Parse an import statement from a string

    Parameters
    ----------
    stmt : str
        the import statement to parse
    relative_to : str | ModuleType
        the module to resolve relative imports against
    translations : list[tuple[str, str]]
        the package translations to apply to the imports
    absolute: bool, optional
        whether to make the imports absolute, by default False

    Returns
    -------

    """
    if translations is None:
        translations = []
    if isinstance(stmts, str):
        stmts = [stmts]
    if isinstance(relative_to, ModuleType):
        relative_to = relative_to.__name__ + (
            ".__init__" if relative_to.__file__.endswith("__init__.py") else ""
        )

    def translate(module_name: str) -> ty.Optional[str]:
        for from_pkg, to_pkg in translations:
            if re.match(from_pkg, module_name):
                return re.sub(
                    from_pkg,
                    to_pkg,
                    module_name,
                    count=1,
                    flags=re.MULTILINE | re.DOTALL,
                )
        return None

    parsed = []
    for stmt in stmts:
        if isinstance(stmt, ImportStatement):
            parsed.append(stmt)
            continue
        match = ImportStatement.match_re.match(stmt.replace("\n", " "))
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
            import_stmt = ImportStatement(
                indent=match.group(1),
                from_=from_,
                relative_to=relative_to,
                imported=imported,
            )
            if absolute:
                import_stmt = import_stmt.absolute()
            import_stmt.translation = translate(import_stmt.module_name)
            parsed.append(import_stmt)

        else:
            # Break up multiple comma separate imports into separate statements if not
            # in "from <module> import..." syntax
            for imp in imported.values():
                parsed.append(
                    ImportStatement(
                        indent=match.group(1),
                        imported={imp.local_name: imp},
                        translation=translate(imp.name),
                    )
                )
    return parsed


GENERIC_PYDRA_IMPORTS = parse_imports(
    [
        "import attrs",  # attrs is included in imports in case we reference attrs.NOTHING
        "from fileformats.generic import File, Directory",
        "from pydra.engine.specs import MultiInputObj",
        "from pathlib import Path",
        "import logging",
        "import pydra.mark",
        "import typing as ty",
        "from pydra.engine import Workflow",
        "from pydra.engine.task import FunctionTask",
        "from pydra.engine.specs import SpecInfo, BaseSpec",
    ]
)


@attrs.define
class ExplicitImport:
    module: str
    name: ty.Optional[str] = None
    alias: ty.Optional[str] = None

    def to_statement(self):
        if self.name:
            stmt = f"from {self.module} import {self.name}"
        else:
            stmt = f"import {self.module}"
        if self.alias:
            stmt += f" as {self.alias}"
        return parse_imports(stmt)[0]


def from_list_to_imports(
    obj: ty.Union[ty.List[ExplicitImport], list]
) -> ty.List[ExplicitImport]:
    if obj is None:
        return []
    return [from_dict_converter(t, ExplicitImport) for t in obj]
