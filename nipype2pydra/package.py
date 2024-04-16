from importlib import import_module
import inspect
import re
import typing as ty
from operator import attrgetter
import logging
from functools import cached_property
from collections import defaultdict
from pathlib import Path
import shutil
import black.parsing
from tqdm import tqdm
import attrs
import yaml
from nipype.interfaces.base import BaseInterface
from . import task
from .utils import (
    UsedSymbols,
    cleanup_function_body,
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
        converter=lambda m: import_module(m) if not isinstance(m, ty.ModuleType) else m,
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
        metadata={
            "help": (
                "Mappings between nipype packages and their pydra equivalents. Regular "
                "expressions are supported"
            ),
        },
    )

    @property
    def interface_only_package(self):
        return not self.workflows

    def write(self, package_root: Path, workflows_to_convert: ty.List[str] = None):
        """Writes the package to the specified package root"""

        mod_dir = package_root.joinpath(*self.name.split("."))

        if self.interface_only_package:
            if workflows_to_convert:
                raise ValueError(
                    f"Specified workflows to convert {workflows_to_convert} aren't "
                    "relavent as the package doesn't contain any workflows"
                )

            auto_dir = mod_dir / "auto"
            if auto_dir.exists():
                shutil.rmtree(auto_dir)
            auto_dir.mkdir(parents=True)

            auto_init = f"# Auto-generated by {__file__}, do not edit as it will be overwritten\n\n"
            all_interfaces = []
            for converter in tqdm(
                self.interfaces.values(),
                "converting interfaces from Nipype to Pydra syntax",
            ):
                converter.write(package_root)
                module_name = nipype2pydra.utils.to_snake_case(converter.task_name)
                auto_init += f"from .{module_name} import {converter.task_name}\n"
                all_interfaces.append(converter.task_name)

            auto_init += (
                "\n\n__all__ = [\n"
                + "\n".join(f'    "{i}",' for i in all_interfaces)
                + "\n]\n"
            )

            with open(auto_dir / "__init__.py", "w") as f:
                f.write(auto_init)

            self.write_post_release_file(auto_dir / "_post_release.py")
        else:
            # Treat as a predominantly workflow package, with helper interfaces,
            # and potentially other modules that are pulled in as required
            if not workflows_to_convert:
                workflows_to_convert = list(self.workflows)

            already_converted = set()
            intra_pkg_modules = defaultdict(set)
            for workflow_name in tqdm(
                workflows_to_convert, "converting workflows from Nipype to Pydra syntax"
            ):
                self.workflows[workflow_name].write(
                    package_root,
                    already_converted=already_converted,
                    intra_pkg_modules=intra_pkg_modules,
                )

            # Write any additional functions in other modules in the package
            self.write_intra_pkg_modules(
                package_root, intra_pkg_modules, self.import_translations
            )

            self.write_post_release_file(mod_dir / "_post_release.py")

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
        translations: ty.List[ty.Tuple[str, str]],
    ):
        """Writes the intra-package modules to the package root

        Parameters
        ----------
        package_root : Path
            the root directory of the package to write the module to
        intra_pkg_modules : dict[str, set[str]
            the intra-package modules to write
        """
        for mod_name, objs in tqdm(
            intra_pkg_modules.items(), "writing intra-package modules"
        ):

            if mod_name == self.name:
                raise NotImplementedError(
                    "Cannot write the main package module as an intra-package module"
                )

            mod_path = package_root.joinpath(*mod_name.split("."))
            mod_path.parent.mkdir(parents=True, exist_ok=True)
            mod = import_module(self.untranslate_submodule(mod_name))

            interfaces = [
                o for o in objs if inspect.isclass(o) and issubclass(o, BaseInterface)
            ]
            other_objs = [o for o in objs if o not in interfaces]

            if interfaces:
                mod_path.mkdir(parents=True, exist_ok=True)
                for interface in tqdm(
                    interfaces, "converting interfaces from Nipype to Pydra syntax"
                ):
                    task_converter = self.interfaces[interface.__name__]
                    task_converter.write(package_root)
                with open(mod_path.joinpath("__init__.py"), "w") as f:
                    f.write(
                        "\n".join(
                            f"from .{o.__name__} import {o.__name__}"
                            for o in interfaces
                        )
                    )
                    if other_objs:
                        f.write(
                            "\nfrom .other import ("
                            + ", ".join(o.__name__ for o in other_objs + ")")
                        )

            if other_objs:
                used = UsedSymbols.find(
                    mod,
                    other_objs,
                    pull_out_inline_imports=False,
                    translations=translations,
                )
                code_str = (
                    "\n".join(str(i) for i in used.imports if not i.indent) + "\n\n"
                )
                code_str += (
                    "\n".join(f"{n} = {d}" for n, d in sorted(used.constants)) + "\n\n"
                )
                code_str += "\n\n".join(
                    sorted(cleanup_function_body(inspect.getsource(f)) for f in objs)
                )
                for klass in sorted(used.local_classes, key=attrgetter("__name__")):
                    if klass not in objs:
                        code_str += "\n\n" + cleanup_function_body(
                            inspect.getsource(klass)
                        )
                for func in sorted(used.local_functions, key=attrgetter("__name__")):
                    if func not in objs:
                        code_str += "\n\n" + cleanup_function_body(
                            inspect.getsource(func)
                        )
                try:
                    code_str = black.format_file_contents(
                        code_str, fast=False, mode=black.FileMode()
                    )
                except Exception as e:
                    with open("/Users/tclose/Desktop/gen-code.py", "w") as f:
                        f.write(code_str)
                    raise RuntimeError(
                        f"Black could not parse generated code: {e}\n\n{code_str}"
                    )
                if interfaces:
                    # Write into package with __init__.py
                    with open(mod_path.joinpath("other").with_suffix(".py"), "w") as f:
                        f.write(code_str)
                else:
                    # Write as a standalone module
                    with open(mod_path.with_suffix(".py"), "w") as f:
                        f.write(code_str)

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
