import os
from pathlib import Path
import tempfile
import pytest
from click.testing import CliRunner


PKG_DIR = Path(__file__).parent
EXAMPLE_SPECS_DIR = PKG_DIR / "example-specs"
EXAMPLE_INTERFACES_DIR = EXAMPLE_SPECS_DIR / "interface" / "nipype"
EXAMPLE_WORKFLOWS_DIR = EXAMPLE_SPECS_DIR / "workflow"
EXAMPLE_PKG_GEN_DIR = EXAMPLE_SPECS_DIR / "pkg-gen"


@pytest.fixture
def gen_test_conftest():
    return PKG_DIR / "scripts" / "pkg_gen" / "resources" / "conftest.py"


@pytest.fixture
def work_dir():
    work_dir = tempfile.mkdtemp()
    return Path(work_dir)


@pytest.fixture
def outputs_dir():
    outputs_dir = PKG_DIR / "outputs" / "workflows"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return outputs_dir


@pytest.fixture
def cli_runner(catch_cli_exceptions):
    def invoke(*args, catch_exceptions=catch_cli_exceptions, **kwargs):
        runner = CliRunner()
        result = runner.invoke(*args, catch_exceptions=catch_exceptions, **kwargs)
        return result

    return invoke


@pytest.fixture
def tasks_template_args():
    template = os.environ.get("NIPYPE2PYDRA_PYDRA_TASK_TEMPLATE", None)
    if template:
        return ["--task-template", template]
    return []


# For debugging in IDE's don't catch raised exceptions and let the IDE
# break at it
if os.getenv("_PYTEST_RAISE", "0") != "0":

    @pytest.hookimpl(tryfirst=True)
    def pytest_exception_interact(call):
        raise call.excinfo.value

    @pytest.hookimpl(tryfirst=True)
    def pytest_internalerror(excinfo):
        raise excinfo.value

    def pytest_configure(config):
        config.option.capture = "no"  # allow print statements to show up in the console
        config.option.log_cli = True  # show log messages in the console
        config.option.log_level = "INFO"  # set the log level to INFO

    CATCH_CLI_EXCEPTIONS = False
else:
    CATCH_CLI_EXCEPTIONS = True


@pytest.fixture
def catch_cli_exceptions():
    return CATCH_CLI_EXCEPTIONS
