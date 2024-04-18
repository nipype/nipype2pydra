import inspect
import typing as ty
import re
from operator import attrgetter
from pathlib import Path
import black.parsing
from .misc import cleanup_function_body, split_source_into_statements
from .imports import ImportStatement, parse_imports, GENERIC_PYDRA_IMPORTS
from .symbols import UsedSymbols


def write_to_module(
    module_fspath: Path,
    imports: ty.List[ImportStatement],
    constants: ty.List[ty.Tuple[str, str]],
    classes: ty.List[ty.Type],
    functions: ty.List[ty.Callable],
    converted_code: ty.Optional[str] = None,
    find_replace: ty.Optional[ty.List[ty.Tuple[str, str]]] = None,
):
    """Writes the given imports, constants, classes, and functions to the file at the given path,
    merging with existing code if it exists"""
    existing_import_strs = []
    code_str = ""
    if module_fspath.exists():
        with open(module_fspath, "r") as f:
            existing_code = f.read()

        for stmt in split_source_into_statements(existing_code):
            if not stmt.startswith(" ") and ImportStatement.matches(stmt):
                existing_import_strs.append(stmt)
            else:
                code_str += "\n" + stmt
    existing_imports = parse_imports(existing_import_strs)

    for const_name, const_val in sorted(constants):
        if f"\n{const_name} = " not in code_str:
            code_str += f"\n{const_name} = {const_val}\n"

    for klass in classes:
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

    for func in sorted(functions, key=attrgetter("__name__")):
        if f"\ndef {func.__name__}(" not in code_str:
            code_str += "\n" + cleanup_function_body(inspect.getsource(func)) + "\n"

    # Add logger
    logger_stmt = "logger = logging.getLogger(__name__)\n\n"
    if logger_stmt not in code_str:
        code_str = logger_stmt + code_str

    for find, replace in find_replace or []:
        code_str = re.sub(find, replace, code_str, flags=re.MULTILINE | re.DOTALL)

    filtered_imports = UsedSymbols.filter_imports(
        ImportStatement.collate(
            existing_imports
            + [i for i in imports if not i.indent]
            + GENERIC_PYDRA_IMPORTS
        ),
        code_str,
    )

    1 + 1  # Breakpoint
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
