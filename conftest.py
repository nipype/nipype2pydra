import os
from pathlib import Path
import traceback
import tempfile
import pytest
from click.testing import CliRunner
from fileformats.generic import File


PKG_DIR = Path(__file__).parent
EXAMPLE_SPECS_DIR = PKG_DIR / "example-specs"
EXAMPLE_TASKS_DIR = EXAMPLE_SPECS_DIR / "task"
EXAMPLE_WORKFLOWS_DIR = EXAMPLE_SPECS_DIR / "workflow"


@File.generate_sample_data.register
def file_generate_sample_data(file: File, dest_dir: Path):
    a_file = dest_dir / "a_file.x"
    a_file.write_text("a sample file")
    return [a_file]


@pytest.fixture
def gen_test_conftest():
    return PKG_DIR / "scripts" / "pkg_gen" / "resources" / "conftest.py"


@pytest.fixture(params=[str(p.stem) for p in (EXAMPLE_TASKS_DIR).glob("*.yaml")])
def task_spec_file(request):
    return (EXAMPLE_TASKS_DIR / request.param).with_suffix(".yaml")


@pytest.fixture(params=[str(p.stem) for p in EXAMPLE_WORKFLOWS_DIR.glob("*.yaml")])
def workflow_spec_file(request):
    return (EXAMPLE_WORKFLOWS_DIR / request.param).with_suffix(".yaml")


@pytest.fixture
def work_dir():
    work_dir = tempfile.mkdtemp()
    return Path(work_dir)


@pytest.fixture
def cli_runner(catch_cli_exceptions):
    def invoke(*args, catch_exceptions=catch_cli_exceptions, **kwargs):
        runner = CliRunner()
        result = runner.invoke(*args, catch_exceptions=catch_exceptions, **kwargs)
        return result

    return invoke


# For debugging in IDE's don't catch raised exceptions and let the IDE
# break at it
if os.getenv("_PYTEST_RAISE", "0") != "0":

    @pytest.hookimpl(tryfirst=True)
    def pytest_exception_interact(call):
        raise call.excinfo.value

    @pytest.hookimpl(tryfirst=True)
    def pytest_internalerror(excinfo):
        raise excinfo.value

    CATCH_CLI_EXCEPTIONS = False
else:
    CATCH_CLI_EXCEPTIONS = True


@pytest.fixture
def catch_cli_exceptions():
    return CATCH_CLI_EXCEPTIONS


def show_cli_trace(result):
    "Used in testing to show traceback of CLI output"
    return "".join(traceback.format_exception(*result.exc_info))
