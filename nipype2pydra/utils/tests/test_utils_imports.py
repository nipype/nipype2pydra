import pytest
from nipype2pydra.utils.symbols import UsedSymbols
from nipype2pydra.statements.imports import ImportStatement, parse_imports
import nipype.interfaces.utility


def test_import_statement1():
    import_stmt = "import attrs"
    assert ImportStatement.matches(import_stmt)
    imports = parse_imports(import_stmt)
    assert len(imports) == 1
    stmt = imports[0]
    assert stmt.module_name == "attrs"


def test_import_statement2():
    import_stmt = "from fileformats.generic import File, Directory"
    assert ImportStatement.matches(import_stmt)
    imports = parse_imports(import_stmt)
    assert len(imports) == 1
    stmt = imports[0]
    assert stmt.module_name == "fileformats.generic"
    assert len(stmt.imported) == 2
    assert stmt.imported["File"].local_name == "File"
    assert stmt.imported["Directory"].local_name == "Directory"


def test_import_statement3():
    import_stmt = "from pydra.engine.specs import MultiInputObj as MIO"
    assert ImportStatement.matches(import_stmt)
    imports = parse_imports(import_stmt)
    assert len(imports) == 1
    stmt = imports[0]
    assert stmt.module_name == "pydra.engine.specs"
    assert stmt.imported["MIO"].name == "MultiInputObj"


def test_import_statement4():
    import_stmt = "from scipy.stats import kurtosis  # pylint: disable=E0611"
    assert ImportStatement.matches(import_stmt)
    imports = parse_imports(import_stmt)
    assert len(imports) == 1
    stmt = imports[0]
    assert stmt.module_name == "scipy.stats"
    assert stmt.imported["kurtosis"].local_name == "kurtosis"


def test_get_imported_object1():
    import_stmts = [
        "import nipype.interfaces.utility as niu",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    assert (
        used.get_imported_object("niu.IdentityInterface")
        is nipype.interfaces.utility.IdentityInterface
    )


def test_get_imported_object2():
    import_stmts = [
        "import nipype.interfaces.utility",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    assert (
        used.get_imported_object("nipype.interfaces.utility")
        is nipype.interfaces.utility
    )


def test_get_imported_object3():
    import_stmts = [
        "from nipype.interfaces.utility import IdentityInterface",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    assert (
        used.get_imported_object("IdentityInterface")
        is nipype.interfaces.utility.IdentityInterface
    )


def test_get_imported_object4():
    import_stmts = [
        "from nipype.interfaces.utility import IdentityInterface",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    assert (
        used.get_imported_object("IdentityInterface.input_spec")
        is nipype.interfaces.utility.IdentityInterface.input_spec
    )


def test_get_imported_object5():
    import_stmts = [
        "import nipype.interfaces.utility",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    assert (
        used.get_imported_object(
            "nipype.interfaces.utility.IdentityInterface.input_spec"
        )
        is nipype.interfaces.utility.IdentityInterface.input_spec
    )


def test_get_imported_object_fail1():
    import_stmts = [
        "import nipype.interfaces.utility",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    with pytest.raises(ImportError, match="Could not find object named"):
        used.get_imported_object("nipype.interfaces.utilityboo")


def test_get_imported_object_fail2():
    import_stmts = [
        "from nipype.interfaces.utility import IdentityInterface",
    ]
    used = UsedSymbols(module_name="test_module", imports=parse_imports(import_stmts))
    with pytest.raises(ImportError, match="Could not find object named"):
        used.get_imported_object("IdentityBoo")
