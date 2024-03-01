import os
from pathlib import Path
import traceback
import tempfile
import pytest
from click.testing import CliRunner


PKG_DIR = Path(__file__).parent
EXAMPLE_SPECS_DIR = PKG_DIR / "example-specs"
EXAMPLE_TASKS_DIR = EXAMPLE_SPECS_DIR / "task"
EXAMPLE_WORKFLOWS_DIR = EXAMPLE_SPECS_DIR / "workflow"


@pytest.fixture
def gen_test_conftest():
    return PKG_DIR / "scripts" / "pkg_gen" / "resources" / "conftest.py"


@pytest.fixture(
    params=[
        str(p.relative_to(EXAMPLE_TASKS_DIR)).replace("/", "__")[:-5]
        for p in (EXAMPLE_TASKS_DIR).glob("**/*.yaml")
    ]
)
def task_spec_file(request):
    return EXAMPLE_TASKS_DIR.joinpath(*request.param.split("__")).with_suffix(".yaml")


@pytest.fixture(params=[str(p.stem) for p in EXAMPLE_WORKFLOWS_DIR.glob("*.yaml")])
def workflow_spec_file(request):
    return (EXAMPLE_WORKFLOWS_DIR / request.param).with_suffix(".yaml")


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
        config.option.capture = 'no'  # allow print statements to show up in the console    
        config.option.log_cli = True  # show log messages in the console
        config.option.log_level = "INFO"  # set the log level to INFO

    CATCH_CLI_EXCEPTIONS = False
else:
    CATCH_CLI_EXCEPTIONS = True


@pytest.fixture
def catch_cli_exceptions():
    return CATCH_CLI_EXCEPTIONS


def show_cli_trace(result):
    "Used in testing to show traceback of CLI output"
    return "".join(traceback.format_exception(*result.exc_info))
