import typing as ty
import re
import keyword
import inspect
import builtins
from logging import getLogger
import attrs
from nipype.interfaces.base import BaseInterface, TraitedSpec, isdefined, Undefined
from nipype.interfaces.base import traits_extension
from .misc import split_source_into_statements, extract_args
from .imports import ImportStatement


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
