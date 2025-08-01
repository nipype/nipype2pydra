import typing as ty
import re
import keyword
import types
import inspect
import builtins
from operator import attrgetter
from collections import defaultdict
from logging import getLogger
from importlib import import_module
import itertools
from functools import cached_property
import attrs
from nipype.interfaces.base import BaseInterface, BaseTraitedSpec, isdefined, Undefined
from nipype.interfaces.base import traits_extension
from .utils.misc import (
    split_source_into_statements,
    extract_args,
    find_super_method,
    get_return_line,
)
from .statements.imports import ImportStatement, parse_imports

if ty.TYPE_CHECKING:
    from .package import PackageConverter


logger = getLogger("nipype2pydra")


@attrs.define
class UsedSymbols:
    """
    A class to hold the used symbols in a module

    Parameters
    ----------
    module_name: str
        the name of the module containing the functions to be converted
    imports : list[str]
        the import statements that need to be included in the converted file
    local_functions: set[callable]
        locally-defined functions used in the function bodies, or nested functions thereof
    local_classes : set[type]
        like local_functions but classes
    constants: set[tuple[str, str]]
        constants used in the function bodies, or nested functions thereof, tuples consist
        of the constant name and its definition
    intra_pkg_funcs: set[tuple[str, callable]]
        list of functions that are defined in neighbouring modules that need to be
        included in the converted file (as opposed of just imported from independent
        packages) along with the name that they were imported as and therefore should
        be named as in the converted module if they are included inline
    intra_pkg_classes: list[tuple[str, callable]]
        like neigh_mod_funcs but classes
    intra_pkg_constants: set[tuple[str, str, str]]
        set of all the constants defined within the package that are referenced by the
        function, (<path of the module>, <constant name>, <local-name>), where
        the local alias and the definition of the constant
    methods: set[callable]
        the names of the methods that are referenced, by default None is a function not
        a method
    class_constants: set[tuple[str, str]]
        the names of the class attributes that are referenced by the method

    class_name: str, optional
        the name of the class that the methods originate from
    """

    module_name: str
    import_stmts: ty.Set[str] = attrs.field(factory=set)
    functions: ty.Set[ty.Callable] = attrs.field(factory=set)
    classes: ty.List[type] = attrs.field(factory=list)
    constants: ty.Set[ty.Tuple[str, str]] = attrs.field(factory=set)
    imported_funcs: ty.Set[ty.Tuple[str, ty.Callable]] = attrs.field(factory=set)
    imported_classes: ty.List[ty.Tuple[str, ty.Callable]] = attrs.field(factory=list)
    imported_constants: ty.Set[ty.Tuple[str, str, str]] = attrs.field(factory=set)
    package: "PackageConverter" = attrs.field(default=None)

    ALWAYS_OMIT_MODULES = [
        "traits.trait_handlers",  # Old traits module, pre v6.0
        "nipype.pipeline",
        "nipype.logging",
        "nipype.config",
        "nipype.interfaces.base",
        "nipype.interfaces.utility",
    ]

    _cache = {}
    _stmts_cache = {}
    _imports_cache = {}
    _funcs_cache = {}
    _classes_cache = {}
    _constants_cache = {}

    symbols_re = re.compile(r"(?<!\"|')\b([a-zA-Z\_][\w\.]*)\b(?!\"|')")

    def update(
        self,
        other: "UsedSymbols",
        absolute_imports: bool = False,
        to_be_inlined: bool = False,
    ):
        if (self.module_name == other.module_name) or to_be_inlined:
            self.import_stmts.update(
                i.absolute() if absolute_imports else i for i in other.import_stmts
            )
        self.imported_funcs.update(other.imported_funcs)
        self.imported_classes.extend(
            c for c in other.imported_classes if c not in self.imported_classes
        )
        self.imported_constants.update(other.imported_constants)
        if self.module_name != other.module_name:
            self.imported_funcs.update((None, f) for f in other.functions)
            self.imported_classes.extend(
                (None, c)
                for c in other.classes
                if (None, c) not in self.imported_classes
            )
            self.imported_constants.update(
                (other.module_name, None, c[0]) for c in other.constants
            )
        else:
            self.functions.update(other.functions)
            self.classes.extend(c for c in other.classes if c not in self.classes)
            self.constants.update(other.constants)

    DEFAULT_FILTERED_CONSTANTS = (
        Undefined,
        traits_extension.File,
        traits_extension.Directory,
    )

    @cached_property
    def module(self):
        return import_module(self.module_name)

    DEFAULT_FILTERED_FUNCTIONS = (isdefined,)

    @classmethod
    def find(
        cls,
        module: types.ModuleType,
        function_bodies: ty.List[ty.Union[str, ty.Callable, ty.Type]],
        package: "PackageConverter",
        collapse_intra_pkg: bool = False,
        pull_out_inline_imports: bool = True,
        always_include: ty.Optional[ty.List[str]] = None,
        absolute_imports: bool = False,
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
        omit_constants : list, optional
            a list of objects to filter out from the used symbols,
            by default (Undefined, traits_extension.File, traits_extension.Directory)
        omit_functions : list[type], optional
            a list of functions to filter out from the used symbols,
            by default [isdefined]
        omit_classes : list[type], optional
            a list of classes (including subclasses) to filter out from the used symbols,
            by default None
        always_include : list[str], optional
            a list of module objects (e.g. functions, classes, etc...) to always include
            in list of used imports, even if they would be normally filtered out by
            one of the `omit` clauses, by default None
        translations : list[tuple[str, str]], optional
            a list of tuples where the first element is the name of the symbol to be
            replaced and the second element is the name of the symbol to replace it with,
            regex supported, by default None
        absolute_imports : bool, optional
            whether to convert relative imports to absolute imports, by default False

        Returns
        -------
        UsedSymbols
            a class containing the used symbols in the module
        """
        if always_include is None:
            always_include = []
        if isinstance(module, str):
            module = import_module(module)
        cache_key = (
            module.__name__,
            tuple(f.__name__ if not isinstance(f, str) else f for f in function_bodies),
            collapse_intra_pkg,
            pull_out_inline_imports,
            tuple(package.all_import_translations),
        )
        try:
            return cls._cache[cache_key]
        except KeyError:
            pass
        used = cls(module_name=module.__name__, package=package)
        cls._cache[cache_key] = used
        used._find_referenced(
            module,
            function_bodies,
            pull_out_inline_imports,
            absolute_imports,
            always_include,
            collapse_intra_pkg,
        )
        return used

    @classmethod
    def clear_cache(cls):
        cls._cache = {}
        cls._cache = {}
        cls._stmts_cache = {}
        cls._imports_cache = {}
        cls._funcs_cache = {}
        cls._classes_cache = {}
        cls._constants_cache = {}

    @classmethod
    def _module_statements(cls, module) -> list:
        try:
            return cls._stmts_cache[module.__name__]
        except KeyError:
            pass
        source_code = inspect.getsource(module)
        cls._stmts_cache[module.__name__] = stmts = split_source_into_statements(
            source_code
        )
        return stmts

    @classmethod
    def _global_imports(
        cls, module, package, absolute_imports, pull_out_inline_imports
    ):
        """Get the global imports in the module"""
        try:
            return cls._imports_cache[module.__name__]
        except KeyError:
            pass
        module_statements = cls._module_statements(module)
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
                    parse_imports(
                        stmt,
                        relative_to=module,
                        translations=package.all_import_translations,
                        absolute=absolute_imports,
                    )
                )
        imports = sorted(imports)
        cls._imports_cache[module.__name__] = imports
        return imports

    def _find_referenced(
        self,
        module,
        function_bodies,
        pull_out_inline_imports,
        absolute_imports,
        always_include,
        collapse_intra_pkg,
    ):

        imports = self._global_imports(
            module, self.package, absolute_imports, pull_out_inline_imports
        )
        # Sort local func/classes/consts so they are iterated in a consistent order to
        # remove stochastic element of traversal and make debugging easier

        used_symbols, all_src = self._get_used_symbols(function_bodies, module)

        base_pkg = module.__name__.split(".")[0]

        module_omit_re = re.compile(
            r"^\b("
            + "|".join(
                self.ALWAYS_OMIT_MODULES + [module.__name__] + self.package.omit_modules
            )
            + r")\b",
        )

        # functions to copy from a relative or nipype module into the output module
        for stmt in imports:
            stmt = stmt.only_include(used_symbols)
            # Skip if no required symbols are in the import statement
            if not stmt:
                continue
            # Filter out Nipype-specific objects that aren't relevant in Pydra
            module_omit = bool(module_omit_re.match(stmt.module_name))
            if (
                module_omit
                or self.package.omit_classes
                or self.package.omit_functions
                or self.package.omit_constants
            ):
                to_include = []
                for imported in stmt.values():
                    if imported.address in always_include:
                        to_include.append(imported.local_name)
                        continue
                    if module_omit:
                        continue
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
                            self.package.omit_classes,
                            self.package.omit_functions,
                        )
                        to_include.append(imported.local_name)
                        continue
                    if inspect.isclass(obj):
                        if self.package.omit_classes and issubclass(
                            obj, tuple(self.package.omit_classes)
                        ):
                            continue
                    elif inspect.isfunction(obj):
                        if (
                            self.package.omit_functions
                            and obj in self.package.omit_functions
                        ):
                            continue
                    elif imported.address in self.package.omit_constants:
                        continue
                    to_include.append(imported.local_name)
                if not to_include:
                    continue
                stmt = stmt.only_include(to_include)
            intra_pkg_objs = defaultdict(set)
            if stmt.in_package(base_pkg) or (
                stmt.in_package("nipype") and not stmt.in_package("nipype.interfaces")
            ):

                for imported in list(stmt.values()):
                    if not (
                        imported.in_package(base_pkg) or imported.in_package("nipype")
                    ) or inspect.isbuiltin(imported.object):
                        # Case where an object is a nested import from a different package
                        # which is imported in a chain from a neighbouring module
                        self.import_stmts.add(
                            imported.as_independent_statement(resolve=True)
                        )
                        stmt.drop(imported)
                    elif inspect.isfunction(imported.object):
                        self.imported_funcs.add((imported.local_name, imported.object))
                        # Recursively include objects imported in the module
                        intra_pkg_objs[import_module(imported.object.__module__)].add(
                            imported.object
                        )
                        if collapse_intra_pkg:
                            stmt.drop(imported)
                    elif inspect.isclass(imported.object):
                        class_def = (imported.local_name, imported.object)
                        # Add the class to the intra_pkg_classes list if it is not
                        # already there. NB: we can't use a set for intra_pkg_classes
                        # like we did for functions here because we need to preserve the
                        # order the classes are defined in the module in case one inherits
                        # from the other
                        if class_def not in self.imported_classes:
                            self.imported_classes.append(class_def)
                        # Recursively include objects imported in the module
                        intra_pkg_objs[import_module(imported.object.__module__)].add(
                            imported.object,
                        )
                        if collapse_intra_pkg:
                            stmt.drop(imported)
                    elif inspect.ismodule(imported.object):
                        # Skip if the module is the same as the module being converted
                        if module_omit_re.match(imported.object.__name__):
                            stmt.drop(imported)
                            continue
                        # Findall references to the module's attributes in the source code
                        # and add them to the list of intra package objects
                        used_attrs = re.findall(
                            r"\b" + imported.local_name + r"\.(\w+)\b", all_src
                        )
                        for attr_name in used_attrs:
                            obj = getattr(imported.object, attr_name)

                            if inspect.isfunction(obj):
                                self.imported_funcs.add((obj.__name__, obj))
                                intra_pkg_objs[imported.object.__name__].add(obj)
                            elif inspect.isclass(obj):
                                class_def = (obj.__name__, obj)
                                if (
                                    class_def
                                    not in self.imported_classes
                                    + self.package.omit_classes
                                ):
                                    self.imported_classes.append(class_def)
                                intra_pkg_objs[imported.object.__name__].add(obj)
                            else:
                                self.imported_constants.add(
                                    (
                                        imported.object.__name__,
                                        attr_name,
                                        attr_name,
                                    )
                                )
                                intra_pkg_objs[imported.object.__name__].add(attr_name)

                        if collapse_intra_pkg:
                            raise NotImplementedError(
                                f"Cannot inline imported module in statement '{stmt}'"
                            )
                    else:
                        self.imported_constants.add(
                            (
                                stmt.module_name,
                                imported.local_name,
                                imported.name,
                            )
                        )
                        intra_pkg_objs[stmt.module].add(imported.local_name)
                        if collapse_intra_pkg:
                            stmt.drop(imported)

            # Recursively include neighbouring objects imported in the module
            for from_mod, inlined_objs in intra_pkg_objs.items():
                used_in_mod = UsedSymbols.find(
                    from_mod,
                    function_bodies=inlined_objs,
                    collapse_intra_pkg=collapse_intra_pkg,
                    package=self.package,
                    always_include=always_include,
                )
                self.update(used_in_mod, to_be_inlined=collapse_intra_pkg)
            if stmt:
                self.import_stmts.add(stmt)

    def _get_used_symbols(self, function_bodies, module):
        """Search the given source code for any symbols that are used in the function bodies"""

        all_src = ""
        used_symbols = set()
        for function_body in function_bodies:
            if not isinstance(function_body, str):
                function_body = inspect.getsource(function_body)
            all_src += "\n\n" + function_body
            self._get_symbols(function_body, used_symbols)

        # Keep stepping into nested referenced local function/class sources until all local
        # functions and constants that are referenced are added to the used symbols
        prev_num_symbols = -1
        while len(used_symbols) > prev_num_symbols:
            prev_num_symbols = len(used_symbols)
            for local_func in self.local_functions(module):
                if (
                    local_func.__name__ in used_symbols
                    and local_func not in self.functions
                ):
                    self.functions.add(local_func)
                    self._get_symbols(local_func, used_symbols)
                    all_src += "\n\n" + inspect.getsource(local_func)
            for local_class in self.local_classes(module):
                if (
                    local_class.__name__ in used_symbols
                    and local_class not in self.classes
                ):
                    if issubclass(local_class, (BaseInterface, BaseTraitedSpec)):
                        continue
                    self.classes.append(local_class)
                    class_body = inspect.getsource(local_class)
                    bases = extract_args(class_body)[1]
                    used_symbols.update(bases)
                    self._get_symbols(class_body, used_symbols)
                    all_src += "\n\n" + class_body
            for const_name, const_def in self.local_constants(module):
                if (
                    const_name in used_symbols
                    and (const_name, const_def) not in self.constants
                ):
                    self.constants.add((const_name, const_def))
                    self._get_symbols(const_def, used_symbols)
                    all_src += "\n\n" + const_def
            used_symbols -= set(self.SYMBOLS_TO_IGNORE)
        return used_symbols, all_src

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

    def get_imported_object(self, name: str) -> ty.Any:
        """Get the object with the given name from used import statements

        Parameters
        ----------
        name : str
            the name of the object to get
        imports : list[ImportStatement], optional
            the import statements to search in (used in tests), by default the imports
            in the used symbols

        Returns
        -------
        Any
            the object with the given name referenced by the given import statements
        """
        # Check to see if it isn't an imported module
        # imported = {
        #     i.sole_imported.local_name: i.sole_imported.object
        #     for i in self.imports
        #     if not i.from_
        # }
        all_imported = {}
        for stmt in self.import_stmts:
            all_imported.update(stmt.imported)
        try:
            return all_imported[name].object
        except KeyError:
            pass
        parts = name.rsplit(".")
        imported_obj = None
        for i in range(1, len(parts)):
            obj_name = ".".join(parts[:-i])
            try:
                imported_obj = all_imported[obj_name].object
            except KeyError:
                continue
            else:
                break
        if imported_obj is None:
            raise ImportError(
                f"Could not find object named {name} in any of the imported modules:\n"
                + "\n".join(str(i) for i in self.import_stmts)
            )
        for part in parts[-i:]:
            imported_obj = getattr(imported_obj, part)
        return imported_obj

    @classmethod
    def local_functions(cls, mod) -> ty.List[ty.Callable]:
        """Get the functions defined in the module"""
        try:
            return cls._funcs_cache[mod.__name__]
        except KeyError:
            pass
        functions = []
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if inspect.isfunction(attr) and attr.__module__ == mod.__name__:
                functions.append(attr)
        functions = sorted(functions, key=attrgetter("__name__"))
        cls._funcs_cache[mod.__name__] = functions
        return functions

    @classmethod
    def local_classes(cls, mod) -> ty.List[type]:
        """Get the functions defined in the module"""
        try:
            return cls._classes_cache[mod.__name__]
        except KeyError:
            pass
        classes = []
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if inspect.isclass(attr) and attr.__module__ == mod.__name__:
                classes.append(attr)
        classes = sorted(classes, key=attrgetter("__name__"))
        cls._classes_cache[mod.__name__] = classes
        return classes

    @classmethod
    def local_constants(cls, mod) -> ty.List[ty.Tuple[str, str]]:
        """
        Get the constants defined in the module
        """
        try:
            return cls._constants_cache[mod.__name__]
        except KeyError:
            pass
        source_code = inspect.getsource(mod)
        source_code = source_code.replace("\\\n", " ")
        constants = []
        for stmt in split_source_into_statements(source_code):
            match = re.match(r"^(\w+) *= *(.*)", stmt, flags=re.MULTILINE | re.DOTALL)
            if match:
                constants.append(tuple(match.groups()))
        constants = sorted(constants)
        cls._constants_cache[mod.__name__] = constants
        return constants


@attrs.define(kw_only=True)
class UsedClassSymbols(UsedSymbols):
    """Class to detect/hold symbols that are used in class methods"""

    klass: type
    methods: ty.Set[ty.Callable] = attrs.field(factory=set)
    class_attrs: ty.Set[ty.Tuple[str, str]] = attrs.field(factory=set)
    supers: ty.Dict[str, ty.Tuple[ty.Callable, type]] = attrs.field(factory=dict)
    method_args: ty.Dict[str, ty.Set[str]] = attrs.field(
        factory=lambda: defaultdict(set)
    )
    method_returns: ty.Dict[str, ty.Set[str]] = attrs.field(
        factory=lambda: defaultdict(set)
    )
    method_stacks: ty.Dict[str, ty.Set[ty.Tuple[str, ...]]] = attrs.field(
        factory=lambda: defaultdict(set)
    )
    super_func_names: ty.Dict[type, ty.Dict[str, str]] = attrs.field(
        factory=lambda: defaultdict(dict)
    )
    outputs: ty.Set[str] = attrs.field(factory=set)
    inputs: ty.Set[str] = attrs.field(factory=set)

    _class_attrs_cache = {}

    @classmethod
    def clear_cache(cls):
        """Clear the cache for the class attributes"""
        cls._class_attrs_cache = {}
        super().clear_cache()

    @classmethod
    def find(
        cls,
        klass: type,
        method_names: ty.List[str],
        package: "PackageConverter",
        collapse_intra_pkg: bool = False,
        pull_out_inline_imports: bool = True,
        always_include: ty.Optional[ty.List[str]] = None,
        absolute_imports: bool = False,
    ) -> "UsedSymbols":
        """Get the imports and local functions/classes/constants referenced in the
        provided function bodies, and those nested within them

        Parameters
        ----------
        klass: type
            the klass the methods belong to
        method_names: list[str]
            the source of all functions/classes (or the functions/classes themselves)
            that need to be checked for used imports
        collapse_intra_pkg : bool
            whether functions and classes defined within the same package, but not the
            same module, are to be included in the output module or not, i.e. whether
            the local funcs/classes/constants they referenced need to be included also
        pull_out_inline_imports : bool, optional
            whether to pull out imports that are inline in the function bodies
            or not, by default True
        always_include : list[str], optional
            a list of module objects (e.g. functions, classes, etc...) to always include
            in list of used imports, even if they would be normally filtered out by
            one of the `omit` clauses, by default None
        translations : list[tuple[str, str]], optional
            a list of tuples where the first element is the name of the symbol to be
            replaced and the second element is the name of the symbol to replace it with,
            regex supported, by default None
        absolute_imports : bool, optional
            whether to convert relative imports to absolute imports, by default False

        Returns
        -------
        UsedSymbols
            a class containing the used symbols in the module
        """
        if always_include is None:
            always_include = []
        cache_key = (
            klass.__name__,
            klass.__module__,
            tuple(method_names),
            collapse_intra_pkg,
            pull_out_inline_imports,
            absolute_imports,
            tuple(always_include),
            tuple(package.all_import_translations),
        )
        try:
            return cls._cache[cache_key]
        except KeyError:
            pass
        used = cls(klass=klass, module_name=klass.__module__, package=package)
        cls._cache[cache_key] = used

        for method_name in method_names:
            used._find_referenced_by_method(
                method_name=method_name,
                pull_out_inline_imports=pull_out_inline_imports,
                absolute_imports=absolute_imports,
                always_include=always_include,
                collapse_intra_pkg=collapse_intra_pkg,
            )

        return used

    def _find_referenced_by_method(
        self,
        method_name,
        pull_out_inline_imports,
        absolute_imports,
        always_include,
        collapse_intra_pkg,
        already_processed=None,
        method_stack=(),
        super_base=None,
    ):
        if super_base:
            method = getattr(super_base, method_name)
        else:
            method, super_base = find_super_method(
                self.klass, method_name, include_class=True
            )
        module = import_module(super_base.__module__)
        if already_processed:
            already_processed.add(method)
        else:
            already_processed = {method}

        if self.package.is_omitted(super_base):
            return
        self.methods.add(method)
        method_stack += (method,)
        method_body = inspect.getsource(method)
        method_body = re.sub(r"\s*#.*", "", method_body)  # Strip out comments

        meth_ref_inputs = set(re.findall(r"(?<=self\.inputs\.)(\w+)", method_body))
        meth_ref_outputs = set(re.findall(r"self\.(\w+) *=", method_body))

        self._find_referenced(
            module,
            [method],
            pull_out_inline_imports=pull_out_inline_imports,
            absolute_imports=absolute_imports,
            always_include=always_include,
            collapse_intra_pkg=collapse_intra_pkg,
        )
        # Find all referenced methods
        ref_method_names = re.findall(r"(?<=self\.)(\w+)\(", method_body)
        # Filter methods in omitted common base-classes like BaseInterface & CommandLine
        ref_method_names = [
            m
            for m in ref_method_names
            if (
                m != "output_spec"
                and not self.package.is_omitted(
                    find_super_method(super_base, m, include_class=True)[1]
                )
            )
        ]
        ref_methods = set(getattr(self.klass, m) for m in ref_method_names)
        for meth in ref_methods:
            if meth in already_processed:
                continue
            if inspect.isclass(meth):
                logger.warning(
                    "Found %s type, that is instantiated as a method, "
                    "should be treated as a nested type, skipping for now",
                    meth,
                )
                continue
            ref_inputs, ref_outputs = self._find_referenced_by_method(
                meth.__name__,
                pull_out_inline_imports=pull_out_inline_imports,
                absolute_imports=absolute_imports,
                always_include=always_include,
                collapse_intra_pkg=collapse_intra_pkg,
                already_processed=already_processed,
                method_stack=method_stack,
            )
            self.method_args[meth.__name__].update(ref_inputs)
            self.method_returns[meth.__name__].update(ref_outputs)
            self.method_stacks[meth.__name__].add(method_stack)
            self.inputs.update(ref_inputs)
            self.outputs.update(ref_outputs)
            meth_ref_inputs.update(ref_inputs)
            meth_ref_outputs.update(ref_outputs)

        # Find all referenced supers
        for match in re.findall(r"super\([^\)]*\)\.(\w+)\(", method_body):
            super_method, base = find_super_method(super_base, match)
            if self.package.is_omitted(base):
                continue
            func_name = self._different_parent_pkg_prefix(base) + match
            if func_name not in self.supers:
                self.supers[func_name] = (super_method, base)
                self.super_func_names[super_base][match] = func_name
                self.method_stacks[func_name].add(method_stack)
                ref_inputs, ref_outputs = self._find_referenced_by_method(
                    super_method.__name__,
                    pull_out_inline_imports=pull_out_inline_imports,
                    absolute_imports=absolute_imports,
                    always_include=always_include,
                    collapse_intra_pkg=collapse_intra_pkg,
                    already_processed=already_processed,
                    method_stack=method_stack,
                    super_base=base,
                )
                self.inputs.update(ref_inputs)
                self.outputs.update(ref_outputs)
                self.method_args[func_name].update(ref_inputs)
                self.method_returns[func_name].update(ref_outputs)
                meth_ref_inputs.update(ref_inputs)
                meth_ref_outputs.update(ref_outputs)

        # Find all referenced constants/class attributes
        local_class_attrs = self.local_class_attrs(super_base)
        for match in re.findall(r"self\.(\w+)\b(?! =|\(.)", method_body):
            try:
                value = local_class_attrs[match]
            except KeyError:
                continue
            base = find_super_method(super_base, match, include_class=True)[1]
            if self.package.is_omitted(base):
                base = self.klass
            self.class_attrs.add((match, value))

        return_value = get_return_line(method_body)
        if return_value and return_value.startswith("self."):
            self.outputs.update(
                re.findall(
                    return_value + r"\[(?:'|\")(\w+)(?:'|\")\] *=",
                    method_body,
                )
            )

        return sorted(meth_ref_inputs), sorted(meth_ref_outputs)

    # def _find_referenced(
    #     self,
    #     klass: type,
    #     method_names: ty.List[str],
    #     package: "PackageConverter",
    #     collapse_intra_pkg: bool = False,
    #     pull_out_inline_imports: bool = True,
    #     always_include: ty.Optional[ty.List[str]] = None,
    #     absolute_imports: bool = False,
    #     method_stack: ty.Tuple[ty.Callable] = (),
    #     already_processed: ty.Optional[ty.Set[ty.Callable]] = None,
    # ) -> "UsedClassSymbols":

    #     module = import_module(klass.__module__)

    #     for method_name in method_names:
    #         self._find_referenced_by_method(
    #             method_name=method_name,
    #             already_processed=already_processed,
    #             method_stack=method_stack,
    #         )

    def _different_parent_pkg_prefix(self, base: type) -> str:
        """Return the common part of two package names"""
        ref_parts = self.klass.__module__.split(".")
        mod_parts = base.__module__.split(".")
        different = []
        is_common = True
        for r_part, m_part in zip(
            itertools.chain(ref_parts, itertools.repeat(None)), mod_parts
        ):
            if r_part != m_part:
                is_common = False
            if not is_common:
                different.append(m_part)
        if not different:
            return ""
        return "_".join(different) + "__" + base.__name__ + "__"

    @classmethod
    def local_class_attrs(cls, klass) -> ty.Dict[str, str]:
        """
        Get the constant attrs defined in the klass
        """
        cache_key = klass.__module__ + "__" + klass.__name__
        try:
            return cls._class_attrs_cache[cache_key]
        except KeyError:
            pass
        source_code = inspect.getsource(klass)
        source_code = source_code.replace("\\\n", " ")
        class_attrs = []
        for stmt in split_source_into_statements(source_code):
            match = re.match(
                r"^    (\w+) *= *(.*)", stmt, flags=re.MULTILINE | re.DOTALL
            )
            if match:
                class_attrs.append(tuple(match.groups()))
        class_attrs = dict(class_attrs)
        cls._constants_cache[cache_key] = class_attrs
        return class_attrs


def clear_caches():
    UsedSymbols.clear_cache()
    UsedClassSymbols.clear_cache()
