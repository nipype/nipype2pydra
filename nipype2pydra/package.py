from importlib import import_module
import inspect
import re
import typing as ty
import types
import logging
from copy import copy
import shutil
from functools import cached_property
from collections import defaultdict
from pathlib import Path
from operator import attrgetter, itemgetter
import attrs
import black.parsing
import black.report
from tqdm import tqdm
import yaml
from . import interface
from .utils import (
    UsedSymbols,
    full_address,
    to_snake_case,
    cleanup_function_body,
    split_source_into_statements,
    get_source_code,
)
from .statements import ImportStatement, parse_imports, GENERIC_PYDRA_IMPORTS
import nipype2pydra.workflow
import nipype2pydra.helpers


logger = logging.getLogger(__name__)


@attrs.define
class ConfigParamsConverter:

    varname: str = attrs.field(
        metadata={
            "help": (
                "name dict/struct that contains the workflow inputs, e.g. config.workflow.*"
            ),
        }
    )
    type: str = attrs.field(
        metadata={
            "help": (
                "name of the nipype module the function is found within, "
                "e.g. mriqc.workflows.anatomical.base"
            ),
        },
        validator=attrs.validators.in_(["dict", "struct"]),
    )

    module: str = attrs.field(
        converter=lambda m: (
            import_module(m) if not isinstance(m, types.ModuleType) else m
        ),
        metadata={
            "help": (
                "name of the nipype module the function is found within, "
                "e.g. mriqc.workflows.anatomical.base"
            ),
        },
    )

    defaults: ty.Dict[str, str] = attrs.field(
        factory=dict,
        metadata={
            "help": "default values for the config parameters",
        },
    )


def resolve_objects(addresses: ty.Optional[ty.List[str]]) -> list:
    if not addresses:
        return []
    objs = []
    for address in addresses:
        parts = address.split(".")
        mod = import_module(".".join(parts[:-1]))
        objs.append(getattr(mod, parts[-1]))
    return objs


@attrs.define(slots=False)
class PackageConverter:
    """
    workflows : dict[str, WorkflowConverter]
        The specs of potentially nested workflows functions that may be called within
        the workflow function
    import_translations : list[tuple[str, str]]
        packages that should be mapped to a new location (typically Nipype based deps
        such as niworkflows). Regular expressions are supported
    """

    name: str = attrs.field(
        metadata={
            "help": ("name of the package to generate, e.g. pydra.tasks.mriqc"),
        },
    )
    nipype_name: str = attrs.field(
        metadata={
            "help": ("name of the nipype package to generate from (e.g. mriqc)"),
        },
    )
    interface_only: bool = attrs.field(
        default=False,
        metadata={
            "help": (
                "Whether the package is an interface-only package (i.e. only contains "
                "interfaces and not workflows)"
            )
        },
    )
    config_params: ty.Dict[str, ConfigParamsConverter] = attrs.field(
        converter=lambda dct: (
            {
                n: (
                    ConfigParamsConverter(**c)
                    if not isinstance(c, ConfigParamsConverter)
                    else c
                )
                for n, c in dct.items()
            }
            if dct is not None
            else {}
        ),
        factory=dict,
        metadata={
            "help": (
                "The name of the global struct/dict that contains workflow inputs "
                "that are to be converted to inputs of the function along with the type "
                'of the struct, either "dict" or "class"'
            ),
        },
    )
    workflows: ty.Dict[str, "nipype2pydra.workflow.WorkflowConverter"] = attrs.field(
        factory=dict,
        converter=attrs.converters.default_if_none(factory=dict),
        metadata={
            "help": (
                "workflow specifications of other workflow functions in the package, which "
                "could be potentially nested within the workflow"
            ),
        },
    )
    interfaces: ty.Dict[str, interface.base.BaseInterfaceConverter] = attrs.field(
        factory=dict,
        converter=attrs.converters.default_if_none(factory=dict),
        metadata={
            "help": (
                "interface specifications for the tasks defined within the workflow package"
            ),
        },
    )
    functions: ty.Dict[str, nipype2pydra.helpers.FunctionConverter] = attrs.field(
        factory=dict,
        converter=attrs.converters.default_if_none(factory=dict),
        metadata={
            "help": (
                "specifications for helper functions defined within the workflow package"
            ),
        },
    )
    classes: ty.Dict[str, nipype2pydra.helpers.ClassConverter] = attrs.field(
        factory=dict,
        converter=attrs.converters.default_if_none(factory=dict),
        metadata={
            "help": (
                "specifications for helper class defined within the workflow package"
            ),
        },
    )
    import_translations: ty.List[ty.Tuple[str, str]] = attrs.field(
        factory=list,
        converter=lambda lst: [tuple(i) for i in lst] if lst else [],
        metadata={
            "help": (
                "Mappings between nipype packages and their pydra equivalents. Regular "
                "expressions are supported"
            ),
        },
    )
    find_replace: ty.List[ty.Tuple[str, str]] = attrs.field(
        factory=list,
        converter=lambda lst: [tuple(i) for i in lst] if lst else [],
        metadata={
            "help": (
                "Generic regular expression substitutions to be run over the code after "
                "it is processed"
            ),
        },
    )
    import_find_replace: ty.List[ty.Tuple[str, str]] = attrs.field(
        factory=list,
        converter=lambda lst: [tuple(i) for i in lst] if lst else [],
        metadata={
            "help": (
                "Generic regular expression substitutions to be run over the code after "
                "it is processed and the imports have been prepended"
            ),
        },
    )
    omit_modules: ty.List[str] = attrs.field(
        factory=list,
        converter=lambda lst: list(lst) if lst else [],
        metadata={
            "help": (
                "Names of modules (untranslated) that shouldn't be included in the "
                "converted package"
            ),
        },
    )
    omit_classes: ty.List[str] = attrs.field(
        factory=list,
        converter=resolve_objects,
        metadata={
            "help": (
                "Addresses of classes (untranslated) that shouldn't be included in the "
                "converted package"
            ),
        },
    )
    omit_functions: ty.List[str] = attrs.field(
        factory=list,
        converter=resolve_objects,
        metadata={
            "help": (
                "Addresses of functions (untranslated) that shouldn't be included in the "
                "converted package"
            ),
        },
    )
    omit_constants: ty.List[str] = attrs.field(
        factory=list,
        converter=lambda lst: list(lst) if lst else [],
        metadata={
            "help": (
                "Addresses of constants (untranslated) that shouldn't be included in the "
                "converted package"
            ),
        },
    )

    init_depth: int = attrs.field(
        metadata={
            "help": (
                "The depth at which __init__ files should include imports from sub-modules "
                "by default"
            )
        }
    )

    auto_import_init_depth: int = attrs.field(
        metadata={
            "help": (
                "The depth at which __init__ files should include imports from sub-modules "
                "by default"
            )
        }
    )
    copy_packages: ty.List[str] = attrs.field(
        factory=list,
        metadata={
            "help": (
                "Packages that should be copied directly into the new package without "
                "modification"
            )
        },
    )

    @init_depth.default
    def _init_depth_default(self) -> int:
        if self.name.startswith("pydra.tasks."):
            depth = 3
        else:
            depth = 1
        return depth + int(self.interface_only)

    @auto_import_init_depth.default
    def _auto_import_init_depth_default(self) -> int:
        return self.init_depth + int(not self.interface_only)

    @cached_property
    def nipype_module(self):
        return import_module(self.nipype_name)

    @property
    def all_import_translations(self) -> ty.List[ty.Tuple[str, str]]:
        all_translations = self.import_translations + [
            (r"nipype\.interfaces\.mrtrix3.\w+\b", r"pydra.tasks.mrtrix3.v3_0"),
            (r"nipype\.interfaces\.(?!base)(\w+)\b", r"pydra.tasks.\1.auto"),
        ]
        if self.interface_only:
            all_translations.extend(
                [
                    (r"nipype\.(.*)", self.name + r".auto.nipype_ports.\1"),
                    (self.nipype_name, self.name + ".auto"),
                ]
            )
        else:
            all_translations.extend(
                [
                    (r"nipype\.(.*)", self.name + r".nipype_ports.\1"),
                    (self.nipype_name, self.name),
                ]
            )
        return all_translations

    @property
    def all_omit_modules(self) -> ty.List[str]:
        return self.omit_modules + ["nipype.interfaces.utility"]

    @property
    def all_explicit(self):
        return (
            list(self.interfaces)
            + list(self.workflows)
            + list(self.functions)
            + list(self.classes)
        )

    @cached_property
    def config_defaults(self) -> ty.Dict[str, ty.Dict[str, str]]:
        all_defaults = {}
        for name, config_params in self.config_params.items():
            params = config_params.module
            all_defaults[name] = {}
            for part in config_params.varname.split("."):
                params = getattr(params, part)
            if config_params.type == "struct":
                defaults = {
                    a: getattr(params, a)
                    for a in dir(params)
                    if not inspect.isfunction(getattr(params, a))
                    and not a.startswith("_")
                }
            elif config_params.type == "dict":
                defaults = copy(params)
            else:
                assert False, f"Unrecognised config_params type {config_params.type}"
            defaults.update(config_params.defaults)
            all_defaults[name] = defaults
        return all_defaults

    def write(self, package_root: Path, to_include: ty.List[str] = None):
        """Writes the package to the specified package root"""

        mod_dir = self.to_fspath(package_root, self.name)

        already_converted = set()
        intra_pkg_modules = defaultdict(set)

        interfaces_to_include = []
        workflows_to_include = []

        if to_include:
            for address in to_include:
                if address in self.interfaces:
                    interfaces_to_include.append(self.interfaces[address])
                elif address in self.workflows:
                    workflows_to_include.append(self.workflows[address])
                else:
                    address_parts = address.split(".")
                    mod_name = ".".join(address_parts[:-1])
                    try:
                        mod = import_module(mod_name)
                        intra_pkg_modules[mod_name].add(getattr(mod, address_parts[-1]))
                    except (ImportError, AttributeError):
                        raise ValueError(
                            f"Could not import {mod_name} to include {address}"
                        )
        if not interfaces_to_include and not workflows_to_include:
            if to_include:
                logger.info(
                    "No interfaces or workflows were explicitly included, assuming all "
                    "are to be included"
                )
            interfaces_to_include = list(self.interfaces.values())
            workflows_to_include = list(self.workflows.values())

        nipype_ports = []

        for workflow in tqdm(workflows_to_include, "parsing workflow statements"):
            workflow.prepare()

        for workflow in tqdm(workflows_to_include, "processing workflow connections"):
            workflow.prepare_connections()

        def collect_intra_pkg_objects(used: UsedSymbols, port_nipype: bool = True):
            for _, klass in used.intra_pkg_classes:
                address = full_address(klass)
                if address in self.nipype_port_converters:
                    if port_nipype:
                        nipype_ports.append(self.nipype_port_converters[address])
                    else:
                        raise NotImplementedError(
                            f"Cannot port {address} as it is referenced from another "
                            "nipype interface to be ported"
                        )
                elif full_address(klass) not in self.interfaces:
                    intra_pkg_modules[klass.__module__].add(klass)
            for _, func in used.intra_pkg_funcs:
                if full_address(func) not in list(self.workflows):
                    intra_pkg_modules[func.__module__].add(func)
            for const_mod_address, _, const_name in used.intra_pkg_constants:
                intra_pkg_modules[const_mod_address].add(const_name)

        for conv in list(self.functions.values()) + list(self.classes.values()):
            intra_pkg_modules[conv.nipype_module_name].add(conv.nipype_object)
            collect_intra_pkg_objects(conv.used_symbols)

        for converter in tqdm(
            workflows_to_include, "converting workflows from Nipype to Pydra syntax"
        ):
            all_used = converter.write(
                package_root,
                already_converted=already_converted,
            )
            class_addrs = [full_address(c) for _, c in all_used.intra_pkg_classes]
            included_addrs = [c.full_address for c in interfaces_to_include]
            interfaces_to_include.extend(
                self.interfaces[a]
                for a in class_addrs
                if a in self.interfaces and a not in included_addrs
            )

            collect_intra_pkg_objects(all_used)

        for converter in tqdm(
            interfaces_to_include,
            "Converting interfaces from Nipype to Pydra syntax",
        ):
            converter.write(
                package_root,
                already_converted=already_converted,
            )
            collect_intra_pkg_objects(converter.used_symbols)

        for converter in tqdm(
            nipype_ports, "Porting interfaces from the core nipype package"
        ):
            converter.write(
                package_root,
                already_converted=already_converted,
            )
            collect_intra_pkg_objects(converter.used_symbols, port_nipype=False)

        # Write any additional functions in other modules in the package
        self.write_intra_pkg_modules(package_root, intra_pkg_modules)

        post_release_dir = mod_dir
        if self.interface_only:
            post_release_dir /= "auto"
        self.write_post_release_file(post_release_dir / "_post_release.py")

        if self.copy_packages:
            for cp_pkg in tqdm(self.copy_packages, "copying packages to output dir"):
                input_pkg_fspath = self.to_fspath(
                    Path(self.nipype_module.__file__).parent,
                    ".".join(cp_pkg.split(".")[1:]),
                )
                output_pkg_fspath = self.to_fspath(
                    package_root, self.nipype2pydra_module_name(cp_pkg)
                )
                output_pkg_fspath.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    input_pkg_fspath,
                    output_pkg_fspath,
                )

    def translate_submodule(
        self, nipype_module_name: str, sub_pkg: ty.Optional[str] = None
    ) -> str:
        """Translates a module name from the Nipype package to the Pydra package"""
        relpath = ImportStatement.get_relative_package(
            nipype_module_name, self.nipype_name
        )
        if relpath == self.nipype_name:
            raise ValueError(
                f"Module {nipype_module_name} is not in the nipype package {self.nipype_name}"
            )
        if sub_pkg:
            relpath = "." + sub_pkg + relpath
        return ImportStatement.join_relative_package(self.name + ".__init__", relpath)

    def untranslate_submodule(self, pydra_module_name: str) -> str:
        """Translates a module name from the Nipype package to the Pydra package"""
        relpath = ImportStatement.get_relative_package(pydra_module_name, self.name)
        if relpath == self.nipype_name:
            raise ValueError(
                f"Module {pydra_module_name} is not in the nipype package {self.name}"
            )
        return ImportStatement.join_relative_package(
            self.nipype_name + ".__init__", relpath
        )

    def write_intra_pkg_modules(
        self,
        package_root: Path,
        intra_pkg_modules: ty.Dict[str, ty.Set[str]],
        already_converted: ty.Set[str] = None,
    ):
        """Writes the intra-package modules to the package root

        Parameters
        ----------
        package_root : Path
            the root directory of the package to write the module to
        intra_pkg_modules : dict[str, set[str]
            the intra-package modules to write
        already_converted : set[str]
            the set of modules that have already been converted
        """
        for mod_name, objs in tqdm(
            intra_pkg_modules.items(), "writing intra-package modules"
        ):

            if not objs:
                continue

            out_mod_name = self.nipype2pydra_module_name(mod_name)

            if mod_name == self.name:
                raise NotImplementedError(
                    "Cannot write the main package module as an intra-package module"
                )

            out_mod_path = package_root.joinpath(*out_mod_name.split("."))
            mod = import_module(mod_name)

            if out_mod_path.is_dir():
                mod_name += ".__init__"
            used = UsedSymbols.find(
                mod,
                objs,
                pull_out_inline_imports=False,
                translations=self.all_import_translations,
                omit_classes=self.omit_classes,
                omit_modules=self.omit_modules,
                omit_functions=self.omit_functions,
                omit_constants=self.omit_constants,
                always_include=self.all_explicit,
            )

            classes = used.local_classes + [
                o for o in objs if inspect.isclass(o) and o not in used.local_classes
            ]

            functions = list(used.local_functions) + [
                o
                for o in objs
                if inspect.isfunction(o) and o not in used.local_functions
            ]

            self.write_to_module(
                package_root=package_root,
                module_name=out_mod_name,
                used=UsedSymbols(
                    module_name=mod_name,
                    imports=used.imports,
                    constants=used.constants,
                    local_classes=classes,
                    local_functions=functions,
                ),
                find_replace=self.find_replace,
                inline_intra_pkg=False,
            )

            self.write_pkg_inits(
                package_root,
                out_mod_name,
                names=(
                    [o.__name__ for o in classes + functions]
                    + [c[0] for c in used.constants]
                ),
                depth=self.init_depth,
                auto_import_depth=self.auto_import_init_depth,
                import_find_replace=self.import_find_replace,
            )

    def nipype2pydra_module_name(self, nipype_name: str) -> str:
        """Converts an original Nipype module path to a Pydra module path

        Parameters
        ----------
        nipype_module_path : str
            the original Nipype module path

        Returns
        -------
        str
            the Pydra module path
        """
        if self.interface_only:
            base_pkg = self.name + ".auto"
        else:
            base_pkg = self.name
        if re.match(self.nipype_module.__name__ + r"\b", nipype_name):
            relative_to = self.nipype_name
        elif re.match(r"^nipype\b", nipype_name):
            base_pkg += ".nipype_ports"
            relative_to = "nipype"
        else:
            return nipype_name
        return ImportStatement.join_relative_package(
            base_pkg + ".__init__",
            ImportStatement.get_relative_package(nipype_name, relative_to),
        )

    @classmethod
    def default_spec(
        cls, name: str, nipype_name: str, defaults: ty.Dict[str, ty.Any]
    ) -> str:
        """Generates a spec for the package converter from the given function"""
        conv = PackageConverter(
            name=name,
            nipype_name=nipype_name,
            **{n: eval(v) for n, v in defaults},
        )
        dct = attrs.asdict(conv)
        for k in dct:
            if not dct[k]:
                dct[k] = None
        del dct["workflows"]
        del dct["interfaces"]
        yaml_str = yaml.dump(dct, sort_keys=False)
        for k in dct:
            fld = getattr(attrs.fields(PackageConverter), k)
            hlp = fld.metadata.get("help")
            if hlp:
                yaml_str = re.sub(
                    r"^(" + k + r"):",
                    "# " + hlp + r"\n\1:",
                    yaml_str,
                    flags=re.MULTILINE,
                )
        return yaml_str

    @cached_property
    def nipype_package(self):
        return import_module(self.nipype_name.split(".")[0])

    def package_dir(self, package_root: Path) -> Path:
        return package_root.joinpath(*self.name.split("."))

    def write_post_release_file(self, fspath: Path):

        if ".dev" in self.nipype_package.__version__:
            logger.warning(
                (
                    "using development version of nipype2pydra (%s), "
                    "development component will be dropped in %s package version"
                ),
                self.nipype_name,
                self.nipype_package.__version__,
            )

        if ".dev" in nipype2pydra.__version__:
            logger.warning(
                (
                    "using development version of nipype2pydra (%s), "
                    "development component will be dropped in %s package version"
                ),
                nipype2pydra.__version__,
                self.name,
            )

        src_pkg_version = self.nipype_package.__version__.split(".dev")[0]
        nipype2pydra_version = nipype2pydra.__version__.split(".dev")[0]
        post_release = (src_pkg_version + nipype2pydra_version).replace(".", "")

        with open(fspath, "w") as f:
            f.write(
                f"""# Auto-generated by {__file__}, do not edit as it will be overwritten

src_pkg_version = "{src_pkg_version}"
nipype2pydra_version = "{nipype2pydra_version}"
post_release = "{post_release}"
        """
            )

    @classmethod
    def to_fspath(cls, package_root: Path, module_name: str) -> Path:
        """Converts a module name to a file path in the package directory"""
        return package_root.joinpath(*module_name.split("."))

    @cached_property
    def nipype_port_converters(self) -> ty.Dict[str, interface.BaseInterfaceConverter]:
        if not self.NIPYPE_PORT_CONVERTER_SPEC_DIR.exists():
            raise RuntimeError(
                f"Nipype port specs dir '{self.NIPYPE_PORT_CONVERTER_SPEC_DIR}' does "
                "not exist, cannot create Nipype port converters"
            )
        converters = {}
        spec_files = list(self.NIPYPE_PORT_CONVERTER_SPEC_DIR.glob("*.yaml"))
        for spec_file in spec_files:
            with open(spec_file, "r") as f:
                spec = yaml.safe_load(f)
            callables_file = spec_file.parent / (spec_file.stem + "_callables.py")
            if self.interface_only:
                mod_base = [self.name, "auto", "nipype_ports"]
            else:
                mod_base = [self.name, "nipype_ports"]
            module_name = ".".join(mod_base + spec["nipype_module"].split(".")[1:])
            task_name = spec["task_name"]
            output_module = (
                self.translate_submodule(
                    module_name,
                    sub_pkg="auto" if self.interface_only else None,
                )
                + "."
                + to_snake_case(task_name)
            )
            converter = interface.get_converter(
                output_module=output_module, callables_module=callables_file, **spec
            )
            converter.package = self
            converters[converter.full_address] = converter

        return converters

    NIPYPE_PORT_CONVERTER_SPEC_DIR = (
        Path(__file__).parent / "interface" / "nipype-ports"
    )

    def add_interface_from_spec(
        self, spec: ty.Dict[str, ty.Any], callables_file: Path
    ) -> interface.BaseInterfaceConverter:
        output_module = self.translate_submodule(
            spec["nipype_module"], sub_pkg="auto" if self.interface_only else None
        )
        output_module += "." + to_snake_case(spec["task_name"])
        converter = self.interfaces[f"{spec['nipype_module']}.{spec['task_name']}"] = (
            interface.get_converter(
                output_module=output_module,
                callables_module=callables_file,
                package=self,
                **spec,
            )
        )
        return converter

    def add_workflow_from_spec(
        self, spec: ty.Dict[str, ty.Any]
    ) -> "nipype2pydra.workflow.WorkflowConverter":
        converter = self.workflows[f"{spec['nipype_module']}.{spec['name']}"] = (
            nipype2pydra.workflow.WorkflowConverter(package=self, **spec)
        )
        return converter

    def add_function_from_spec(
        self, spec: ty.Dict[str, ty.Any]
    ) -> "nipype2pydra.helpers.FunctionConverter":
        converter = self.functions[f"{spec['nipype_module']}.{spec['name']}"] = (
            nipype2pydra.helpers.FunctionConverter(package=self, **spec)
        )
        return converter

    def add_class_from_spec(
        self, spec: ty.Dict[str, ty.Any]
    ) -> "nipype2pydra.helpers.ClassConverter":
        converter = self.classes[f"{spec['nipype_module']}.{spec['name']}"] = (
            nipype2pydra.helpers.ClassConverter(package=self, **spec)
        )
        return converter

    def find_and_replace_config_params(
        self, code_str, nested_configs: ty.Optional[ty.Set[str]] = None
    ) -> ty.Tuple[str, ty.List[str], ty.Set[str]]:
        """Finds and replaces configuration parameters in the code string and returns
        the modified code string along with the set of replaced parameters

        Parameters
        ----------
        code_str : str
            the code string to find and replace configuration parameters in
        nested_configs : set[str], optional
            the set of nested configuration parameters to replace

        Returns
        -------
        str
            the modified code string
        list[str]
            the signature of the configuration parameters
        set[str]
            the set of replaced parameters
        """
        used_configs = set() if nested_configs is None else copy(nested_configs)
        for config_name, config_param in self.config_params.items():
            if config_param.type == "dict":
                config_regex = re.compile(
                    r"\b" + config_name + r"\[(?:'|\")([^\]]+)(?:'|\")\]\b"
                )
            else:
                config_regex = re.compile(r"\b" + config_param.varname + r"\.(\w+)\b")
            used_configs.update(
                (config_name, m) for m in config_regex.findall(code_str)
            )
            code_str = config_regex.sub(config_name + r"_\1", code_str)

        config_sig = []
        param_init = ""
        for scope_prefix, config_name in used_configs:
            param_name = f"{scope_prefix}_{config_name}"
            param_default = self.config_defaults[scope_prefix][config_name]
            if isinstance(param_default, str) and "(" in param_default:
                # delay init of default value to function body
                param_init += (
                    f"    if {param_name} is None:\n"
                    f"        {param_name} = {param_default}\n\n"
                )
                param_default = None
            config_sig.append(f"{param_name}={param_default!r}")

        return param_init + code_str, config_sig, used_configs

    def write_to_module(
        self,
        package_root: Path,
        module_name: str,
        used: UsedSymbols,
        converted_code: ty.Optional[str] = None,
        find_replace: ty.Optional[ty.List[ty.Tuple[str, str]]] = None,
        inline_intra_pkg: bool = False,
        additional_imports: ty.Optional[ty.List[ImportStatement]] = None,
    ):
        """Writes the given imports, constants, classes, and functions to the file at the given path,
        merging with existing code if it exists"""
        from .helpers import FunctionConverter, ClassConverter

        if additional_imports is None:
            additional_imports = []

        if find_replace is None:
            find_replace = self.find_replace
        else:
            find_replace = copy(find_replace)
            find_replace.extend(self.find_replace)

        existing_import_strs = []
        code_str = ""
        module_fspath = package_root.joinpath(*module_name.split("."))
        if module_fspath.is_dir():
            module_fspath = module_fspath.joinpath("__init__.py")
        else:
            module_fspath = module_fspath.with_suffix(".py")
        module_fspath.parent.mkdir(parents=True, exist_ok=True)
        if module_fspath.exists():
            with open(module_fspath, "r") as f:
                existing_code = f.read()

            for stmt in split_source_into_statements(existing_code):
                if not stmt.startswith(" ") and ImportStatement.matches(stmt):
                    existing_import_strs.append(stmt)
                else:
                    code_str += "\n" + stmt
        existing_imports = parse_imports(existing_import_strs, relative_to=module_name)
        converter_imports = []

        for const_name, const_val in sorted(used.constants):
            if f"\n{const_name} = " not in code_str:
                code_str += f"\n{const_name} = {const_val}\n"

        for klass in used.local_classes:
            if f"\nclass {klass.__name__}(" not in code_str:
                try:
                    class_converter = self.classes[full_address(klass)]
                    converter_imports.extend(class_converter.used_symbols.imports)
                except KeyError:
                    class_converter = ClassConverter.from_object(klass, self)
                code_str += "\n" + class_converter.converted_code + "\n"

        if converted_code is not None:
            # We need to format the converted code so we can check whether it's already in the file
            # or not
            try:
                converted_code = black.format_file_contents(
                    converted_code, fast=False, mode=black.FileMode()
                )
            except black.report.NothingChanged:
                pass
            except Exception as e:
                # Write to file for debugging
                debug_file = "~/unparsable-nipype2pydra-output.py"
                with open(Path(debug_file).expanduser(), "w") as f:
                    f.write(converted_code)
                raise RuntimeError(
                    f"Black could not parse generated code (written to {debug_file}): "
                    f"{e}\n\n{converted_code}"
                )

            if converted_code.strip() not in code_str:
                code_str += "\n" + converted_code + "\n"

        for func in sorted(used.local_functions, key=attrgetter("__name__")):
            if f"\ndef {func.__name__}(" not in code_str:
                if func.__name__ in self.functions:
                    function_converter = self.functions[full_address(func)]
                    converter_imports.extend(function_converter.used_symbols.imports)
                else:
                    function_converter = FunctionConverter.from_object(func, self)
                code_str += "\n" + function_converter.converted_code + "\n"

        # Add logger
        logger_stmt = "logger = logging.getLogger(__name__)\n\n"
        if logger_stmt not in code_str:
            code_str = logger_stmt + code_str

        inlined_symbols = []
        if inline_intra_pkg:

            code_str += (
                "\n\n# Intra-package imports that have been inlined in this module\n\n"
            )
            for func_name, func in sorted(used.intra_pkg_funcs, key=itemgetter(0)):
                func_src = get_source_code(func)
                func_src = re.sub(
                    r"^(#[^\n]+\ndef) (\w+)(?=\()",
                    r"\1 " + func_name,
                    func_src,
                    flags=re.MULTILINE,
                )
                code_str += "\n\n" + cleanup_function_body(func_src)
                inlined_symbols.append(func_name)

            for klass_name, klass in sorted(used.intra_pkg_classes, key=itemgetter(0)):
                klass_src = get_source_code(klass)
                klass_src = re.sub(
                    r"^(#[^\n]+\nclass) (\w+)(?=\()",
                    r"\1 " + klass_name,
                    klass_src,
                    flags=re.MULTILINE,
                )
                code_str += "\n\n" + cleanup_function_body(klass_src)
                inlined_symbols.append(klass_name)

        # We run the formatter before the find/replace so that the find/replace can be more
        # predictable
        try:
            code_str = black.format_file_contents(
                code_str, fast=False, mode=black.FileMode()
            )
        except black.report.NothingChanged:
            pass
        except Exception as e:
            # Write to file for debugging
            debug_file = "~/unparsable-nipype2pydra-output.py"
            with open(Path(debug_file).expanduser(), "w") as f:
                f.write(code_str)
            raise RuntimeError(
                f"Black could not parse generated code (written to {debug_file}): {e}\n\n{code_str}"
            )

        for find, replace in find_replace or []:
            code_str = re.sub(find, replace, code_str, flags=re.MULTILINE | re.DOTALL)

        imports = ImportStatement.collate(
            existing_imports
            + converter_imports
            + [i for i in used.imports if not i.indent]
            + GENERIC_PYDRA_IMPORTS
            + additional_imports
        )

        if module_fspath.name != "__init__.py":
            imports = UsedSymbols.filter_imports(imports, code_str)

        # Strip out inlined imports
        for inlined_symbol in inlined_symbols:
            for stmt in imports:
                if inlined_symbol in stmt:
                    stmt.drop(inlined_symbol)

        import_str = "\n".join(str(i) for i in imports if i)

        try:
            import_str = black.format_file_contents(
                import_str,
                fast=True,
                mode=black.FileMode(),
            )
        except black.report.NothingChanged:
            pass

        # Rerun find-replace to allow us to catch any imports we want to alter
        for find, replace in self.import_find_replace or []:
            import_str = re.sub(
                find, replace, import_str, flags=re.MULTILINE | re.DOTALL
            )

        code_str = import_str + "\n\n" + code_str

        with open(module_fspath, "w") as f:
            f.write(code_str)

        return module_fspath

    def write_pkg_inits(
        self,
        package_root: Path,
        module_name: str,
        names: ty.List[str],
        depth: int,
        auto_import_depth: int,
        import_find_replace: ty.Optional[ty.List[str]] = None,
    ):
        """Writes __init__.py files to all directories in the given package path

        Parameters
        ----------
        package_root : Path
            The root directory of the package
        module_name : str
            The name of the module to write the imports to
        depth : int
            The depth of the package from the root up to which to generate __init__.py files
            for
        auto_import_depth: int
            the depth below which the init files should contain cascading imports from
        names : List[str]
            The names to import in the __init__.py files
        """
        # Write base init path that imports __version__ from the auto-generated _version
        # file
        parts = module_name.split(".")
        for i, part in enumerate(reversed(parts[depth:]), start=1):
            mod_parts = parts[:-i]
            parent_mod = ".".join(mod_parts)
            init_fspath = package_root.joinpath(*mod_parts, "__init__.py")
            if i > len(parts) - auto_import_depth:
                # Write empty __init__.py if it doesn't exist
                init_fspath.touch()
                continue
            code_str = ""
            import_stmts = []
            if init_fspath.exists():
                with open(init_fspath, "r") as f:
                    existing_code = f.read()
                stmts = split_source_into_statements(existing_code)
                for stmt in stmts:
                    if ImportStatement.matches(stmt):
                        import_stmt = parse_imports(stmt, relative_to=parent_mod)[0]
                        if import_stmt.conditional:
                            code_str += f"\n{stmt}"
                        else:
                            import_stmts.append(import_stmt)
                    else:
                        code_str += f"\n{stmt}"
            import_stmts.append(
                parse_imports(
                    f"from .{part} import ({', '.join(names)})", relative_to=parent_mod
                )[0]
            )
            import_stmts = sorted(ImportStatement.collate(import_stmts))
            import_str = "\n".join(str(i) for i in import_stmts)

            # Format import str to make the find-replace target consistent
            try:
                import_str = black.format_file_contents(
                    import_str, fast=False, mode=black.FileMode()
                )
            except black.report.NothingChanged:
                pass
            except Exception as e:
                # Write to file for debugging
                debug_file = "~/unparsable-nipype2pydra-output.py"
                with open(Path(debug_file).expanduser(), "w") as f:
                    f.write(code_str)
                raise RuntimeError(
                    f"Black could not parse generated code (written to {debug_file}): "
                    f"{e}\n\n{code_str}"
                )

            # Rerun find-replace to allow us to catch any imports we want to alter
            for find, replace in import_find_replace or []:
                import_str = re.sub(
                    find, replace, import_str, flags=re.MULTILINE | re.DOTALL
                )

            code_str = import_str + "\n" + code_str

            try:
                code_str = black.format_file_contents(
                    code_str, fast=False, mode=black.FileMode()
                )
            except black.report.NothingChanged:
                pass
            except Exception as e:
                # Write to file for debugging
                debug_file = "~/unparsable-nipype2pydra-output.py"
                with open(Path(debug_file).expanduser(), "w") as f:
                    f.write(code_str)
                raise RuntimeError(
                    f"Black could not parse generated code (written to {debug_file}): "
                    f"{e}\n\n{code_str}"
                )

            with open(init_fspath, "w") as f:
                f.write(code_str)

    BASE_INIT_TEMPLATE = """\"\"\"
This is a basic doctest demonstrating that the package and pydra can both be successfully
imported.

>>> import pydra.engine
>>> import pydra.tasks.{pkg}
\"\"\"

from warnings import warn
from pathlib import Path

pkg_path = Path(__file__).parent.parent

try:
    from ._version import __version__
except ImportError:
    raise RuntimeError(
        "pydra-{pkg} has not been properly installed, please run "
        f"`pip install -e {str(pkg_path)}` to install a development version"
    )
if "nipype" not in __version__:
    try:
        from ._post_release import src_pkg_version, nipype2pydra_version
    except ImportError:
        warn(
            "Nipype interfaces haven't been automatically converted from their specs in "
            f"`nipype-auto-conv`. Please run `{str(pkg_path / 'nipype-auto-conv' / 'generate')}` "
            "to generated the converted Nipype interfaces in pydra.tasks.{pkg}.auto"
        )
    else:
        n_ver = src_pkg_version.replace(".", "_")
        n2p_ver = nipype2pydra_version.replace(".", "_")
        __version__ += (
            "_" if "+" in __version__ else "+"
        ) + f"nipype{n_ver}_nipype2pydra{n2p_ver}"


__all__ = ["__version__"]
"""
