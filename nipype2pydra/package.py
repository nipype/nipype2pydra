from importlib import import_module
import inspect
import re
import typing as ty
import types
import logging
from functools import cached_property
from collections import defaultdict
from pathlib import Path
from tqdm import tqdm
import attrs
import yaml
from . import task
from .utils import (
    UsedSymbols,
    full_address,
    write_to_module,
    ImportStatement,
)
import nipype2pydra.workflow

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


@attrs.define
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
        metadata={
            "help": (
                "workflow specifications of other workflow functions in the package, which "
                "could be potentially nested within the workflow"
            ),
        },
    )
    interfaces: ty.Dict[str, task.base.BaseTaskConverter] = attrs.field(
        factory=dict,
        metadata={
            "help": (
                "interface specifications for the tasks defined within the workflow package"
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
                "Generic regular expression substitutions to be run over the code before "
                "it is processed"
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
    omit_objects: ty.List[str] = attrs.field(
        factory=list,
        converter=resolve_objects,
        metadata={
            "help": (
                "Addresses of objects (untranslated) that shouldn't be included in the "
                "converted package"
            ),
        },
    )

    @property
    def interface_only_package(self):
        return not self.workflows

    @property
    def all_import_translations(self) -> ty.List[ty.Tuple[str, str]]:
        return self.import_translations + [
            (r"nipype\.interfaces\.(?!base)(\w+)\b", r"pydra.tasks.\1.auto"),
            (r"nipype\.(.*)", self.name + r".nipype_ports.\1"),
            (self.nipype_name, self.name),
        ]

    def write(self, package_root: Path, to_include: ty.List[str] = None):
        """Writes the package to the specified package root"""

        mod_dir = package_root.joinpath(*self.name.split("."))

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

        def collect_intra_pkg_objects(used: UsedSymbols):
            for _, klass in used.intra_pkg_classes:
                if full_address(klass) not in list(self.interfaces):
                    intra_pkg_modules[klass.__module__].add(klass)
            for _, func in used.intra_pkg_funcs:
                if full_address(func) not in list(self.workflows):
                    intra_pkg_modules[func.__module__].add(func)
            for const_mod_address, _, const_name in used.intra_pkg_constants:
                intra_pkg_modules[const_mod_address].add(const_name)
            1 + 1

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
            "converting interfaces from Nipype to Pydra syntax",
        ):
            converter.write(
                package_root,
                already_converted=already_converted,
            )
            collect_intra_pkg_objects(converter.used_symbols)

        # # FIXME: hack to remove nipype-specific functions from intra-package
        # #        these should be mapped into a separate module,
        # #        maybe pydra.tasks.<pkg>.nipype_ports or something
        for mod_name in list(intra_pkg_modules):
            if re.match(r"^nipype\.pipeline\b", mod_name):
                intra_pkg_modules.pop(mod_name)

        # Write any additional functions in other modules in the package
        self.write_intra_pkg_modules(package_root, intra_pkg_modules)

        post_release_dir = mod_dir
        if self.interface_only_package:
            post_release_dir /= "auto"
        self.write_post_release_file(post_release_dir / "_post_release.py")

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

            out_mod_name = self.to_output_module_path(mod_name)

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
                omit_objs=self.omit_objects,
            )

            classes = used.local_classes + [
                o for o in objs if inspect.isclass(o) and o not in used.local_classes
            ]

            functions = list(used.local_functions) + [
                o
                for o in objs
                if inspect.isfunction(o) and o not in used.local_functions
            ]

            write_to_module(
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

    def to_output_module_path(self, nipype_module_path: str) -> str:
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
        if re.match(r"^nipype\b", nipype_module_path):
            return ImportStatement.join_relative_package(
                self.name + ".nipype_ports.__init__",
                ImportStatement.get_relative_package(nipype_module_path, "nipype"),
            )
        return ImportStatement.join_relative_package(
            self.name + ".__init__",
            ImportStatement.get_relative_package(nipype_module_path, self.nipype_name),
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
