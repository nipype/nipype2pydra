import typing as ty
import re
import keyword
import types
import inspect
import builtins
from logging import getLogger
from importlib import import_module
import attrs
from nipype.interfaces.base import BaseInterface, TraitedSpec, isdefined, Undefined
from nipype.interfaces.base import traits_extension
from .misc import split_source_into_statements, extract_args
from .imports import ImportStatement, parse_imports


logger = getLogger("nipype2pydra")


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

    _cache = {}

    symbols_re = re.compile(r"(?<!\"|')\b([a-zA-Z\_][\w\.]*)\b(?!\"|')")

    def update(self, other: "UsedSymbols", absolute_imports: bool = False):
        self.imports.update(
            i.absolute() if absolute_imports else i for i in other.imports
        )
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
        module: types.ModuleType,
        function_bodies: ty.List[ty.Union[str, ty.Callable, ty.Type]],
        collapse_intra_pkg: bool = True,
        pull_out_inline_imports: bool = True,
        filter_objs: ty.Sequence = DEFAULT_FILTERED_OBJECTS,
        filter_classes: ty.Optional[ty.List[ty.Type]] = None,
        translations: ty.Sequence[ty.Tuple[str, str]] = None,
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
        translations : list[tuple[str, str]], optional
            a list of tuples where the first element is the name of the symbol to be
            replaced and the second element is the name of the symbol to replace it with,
            regex supported, by default None

        Returns
        -------
        UsedSymbols
            a class containing the used symbols in the module
        """
        cache_key = (
            module.__name__,
            tuple(f.__name__ if not isinstance(f, str) else f for f in function_bodies),
            collapse_intra_pkg,
            pull_out_inline_imports,
            tuple(filter_objs) if filter_objs else None,
            tuple(filter_classes) if filter_classes else None,
            tuple(translations) if translations else None,
        )
        try:
            return cls._cache[cache_key]
        except KeyError:
            pass

        used = cls()
        source_code = inspect.getsource(module)
        local_functions = get_local_functions(module)
        local_constants = get_local_constants(module)
        local_classes = get_local_classes(module)
        module_statements = split_source_into_statements(source_code)
        imports: ty.List[ImportStatement] = []
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
                imports.extend(
                    parse_imports(stmt, relative_to=module, translations=translations)
                )

        used_symbols = set()
        for function_body in function_bodies:
            cls._get_symbols(function_body, used_symbols)

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
                    cls._get_symbols(local_func, used_symbols)
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
                    cls._get_symbols(class_body, used_symbols)
            for const_name, const_def in local_constants:
                if (
                    const_name in used_symbols
                    and (const_name, const_def) not in used.constants
                ):
                    used.constants.add((const_name, const_def))
                    cls._get_symbols(const_def, used_symbols)
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
                        to_include.append(imported.local_name)
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
            inlined_objects = []
            if stmt.in_package(base_pkg) or (
                stmt.in_package("nipype") and not stmt.translation
            ):
                for imported in list(stmt.values()):
                    if not (
                        imported.in_package(base_pkg) or imported.in_package("nipype")
                    ) or inspect.isbuiltin(imported.object):
                        # Case where an object is a nested import from a different package
                        # which is imported from a neighbouring module
                        used.imports.add(
                            imported.as_independent_statement(resolve=True)
                        )
                        stmt.drop(imported)
                    elif inspect.isfunction(imported.object):
                        used.intra_pkg_funcs.add((imported.local_name, imported.object))
                        if collapse_intra_pkg or stmt.in_package("nipype"):
                            # Recursively include objects imported in the module
                            # by the inlined function
                            inlined_objects.append(
                                (
                                    import_module(imported.object.__module__),
                                    imported.object,
                                )
                            )
                            stmt.drop(imported)
                    elif inspect.isclass(imported.object):
                        class_def = (imported.local_name, imported.object)
                        # Add the class to the intra_pkg_classes list if it is not
                        # already there. NB: we can't use a set for intra_pkg_classes
                        # like we did for functions here because we need to preserve the
                        # order the classes are defined in the module in case one inherits
                        # from the other
                        if class_def not in used.intra_pkg_classes:
                            used.intra_pkg_classes.append(class_def)
                        if collapse_intra_pkg or stmt.in_package("nipype"):
                            # Recursively include objects imported in the module
                            # by the inlined class
                            inlined_objects.append(
                                (
                                    import_module(imported.object.__module__),
                                    imported.object,
                                )
                            )
                            stmt.drop(imported)
                    elif not inspect.ismodule(imported.object) and (
                        collapse_intra_pkg or stmt.in_package("nipype")
                    ):

                        inlined_objects.append((stmt.module, imported.local_name))
                        stmt.drop(imported)

            # Recursively include neighbouring objects imported in the module
            for from_mod, inlined_obj in inlined_objects:
                used_in_mod = cls.find(
                    from_mod,
                    function_bodies=[inlined_obj],
                    translations=translations,
                )
                used.update(used_in_mod)
            if stmt:
                used.imports.add(stmt)
        cls._cache[cache_key] = used
        return used

    @classmethod
    def filter_imports(
        cls, imports: ty.List[ImportStatement], source_code: str
    ) -> ty.List[ImportStatement]:
        """Filter out the imports that are not used in the function bodies"""
        symbols = set()
        cls._get_symbols(source_code, symbols)
        symbols -= set(cls.SYMBOLS_TO_IGNORE)
        filtered = []
        for stmt in imports:
            if stmt.from_:
                stmt = stmt.only_include(symbols)
                if stmt:
                    filtered.append(stmt)
            elif stmt.sole_imported.local_name in symbols:
                filtered.append(stmt)
        return filtered

    def copy(self) -> "UsedSymbols":
        return attrs.evolve(self)

    @classmethod
    def _get_symbols(
        cls, func: ty.Union[str, ty.Callable, ty.Type], symbols: ty.Set[str]
    ):
        """Get the symbols used in a function body"""
        try:
            fbody = inspect.getsource(func)
        except TypeError:
            fbody = func
        for stmt in split_source_into_statements(fbody):
            if stmt and not re.match(
                r"\s*(#|\"|'|from |import |r'|r\"|f'|f\")", stmt
            ):  # skip comments/docs
                for sym in cls.symbols_re.findall(stmt):
                    if "." in sym:
                        parts = sym.split(".")
                        symbols.update(
                            ".".join(parts[: i + 1]) for i in range(len(parts))
                        )
                    else:
                        symbols.add(sym)

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
    local_vars = []
    for stmt in split_source_into_statements(source_code):
        match = re.match(r"^(\w+) *= *(.*)", stmt, flags=re.MULTILINE | re.DOTALL)
        if match:
            local_vars.append(tuple(match.groups()))
    return local_vars
