import inspect
import typing as ty
import re
from operator import attrgetter, itemgetter
from pathlib import Path
import black.parsing
import black.report
from .misc import cleanup_function_body, split_source_into_statements, get_source_code
from .imports import ImportStatement, parse_imports, GENERIC_PYDRA_IMPORTS
from .symbols import UsedSymbols


def write_to_module(
    package_root: Path,
    module_name: str,
    used: UsedSymbols,
    converted_code: ty.Optional[str] = None,
    find_replace: ty.Optional[ty.List[ty.Tuple[str, str]]] = None,
    inline_intra_pkg: bool = False,
):
    """Writes the given imports, constants, classes, and functions to the file at the given path,
    merging with existing code if it exists"""
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

    for const_name, const_val in sorted(used.constants):
        if f"\n{const_name} = " not in code_str:
            code_str += f"\n{const_name} = {const_val}\n"

    for klass in used.local_classes:
        if f"\nclass {klass.__name__}(" not in code_str:
            code_str += "\n" + cleanup_function_body(inspect.getsource(klass)) + "\n"

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
            code_str += "\n" + cleanup_function_body(inspect.getsource(func)) + "\n"

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
        + [i for i in used.imports if not i.indent]
        + GENERIC_PYDRA_IMPORTS
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

    code_str = import_str + "\n\n" + code_str

    with open(module_fspath, "w") as f:
        f.write(code_str)

    return module_fspath


def write_pkg_inits(
    package_root: Path,
    module_name: str,
    names: ty.List[str],
    depth: int,
    auto_import_depth: int,
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
        code_str = "\n".join(str(i) for i in import_stmts) + "\n" + code_str
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
