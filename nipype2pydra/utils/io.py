import inspect
import typing as ty
import re
from operator import attrgetter, itemgetter
from pathlib import Path
import black.parsing
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
    module_fspath = package_root.joinpath(*module_name.split(".")).with_suffix(".py")
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

    for const_name, const_val in sorted(used.local_constants):
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

    for find, replace in find_replace or []:
        code_str = re.sub(find, replace, code_str, flags=re.MULTILINE | re.DOTALL)

    code_str += "\n\n# Intra-package imports that have been inlined in this module\n\n"

    if inline_intra_pkg:
        for func_name, func in sorted(used.intra_pkg_funcs, key=itemgetter(0)):
            func_src = get_source_code(func)
            func_src = re.sub(
                r"^(#[^\n]+\ndef) (\w+)(?=\()",
                r"\1 " + func_name,
                func_src,
                flags=re.MULTILINE,
            )
            code_str += "\n\n" + cleanup_function_body(func_src)

        for klass_name, klass in sorted(used.intra_pkg_classes, key=itemgetter(0)):
            klass_src = get_source_code(klass)
            klass_src = re.sub(
                r"^(#[^\n]+\nclass) (\w+)(?=\()",
                r"\1 " + klass_name,
                klass_src,
                flags=re.MULTILINE,
            )
            code_str += "\n\n" + cleanup_function_body(klass_src)

    filtered_imports = UsedSymbols.filter_imports(
        ImportStatement.collate(
            existing_imports
            + [i for i in used.imports if not i.indent]
            + GENERIC_PYDRA_IMPORTS
        ),
        code_str,
    )

    code_str = "\n".join(str(i) for i in filtered_imports) + "\n\n" + code_str

    try:
        code_str = black.format_file_contents(
            code_str, fast=False, mode=black.FileMode()
        )
    except Exception as e:
        # Write to file for debugging
        debug_file = "~/unparsable-nipype2pydra-output.py"
        with open(Path(debug_file).expanduser(), "w") as f:
            f.write(code_str)
        raise RuntimeError(
            f"Black could not parse generated code (written to {debug_file}): {e}\n\n{code_str}"
        )

    with open(module_fspath, "w") as f:
        f.write(code_str)

    return module_fspath
