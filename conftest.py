import os
from pathlib import Path
import traceback
import tempfile
import pytest
from click.testing import CliRunner


@pytest.fixture(scope="session")
def pkg_dir():
    return Path(__file__).parent


@pytest.fixture(scope="session")
def example_specs_dir(pkg_dir):
    return pkg_dir / "example-specs"


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
