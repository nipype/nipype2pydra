from nipype2pydra.utils.imports import ImportStatement, parse_imports


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
