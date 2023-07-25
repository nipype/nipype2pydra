import os
import typing as ty
import time
import logging
from pathlib import Path
import tempfile
import pytest


try:
    from pydra import set_input_validator

    set_input_validator(True)
except ImportError:
    pass
from fileformats.core.utils import include_testing_package

include_testing_package(True)

# Set DEBUG logging for unittests

log_level = logging.WARNING

logger = logging.getLogger("fileformats")
logger.setLevel(log_level)

sch = logging.StreamHandler()
sch.setLevel(log_level)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
sch.setFormatter(formatter)
logger.addHandler(sch)


# For debugging in IDE's don't catch raised exceptions and let the IDE
# break at it
if os.getenv("_PYTEST_RAISE", "0") != "0":

    @pytest.hookimpl(tryfirst=True)
    def pytest_exception_interact(call):
        raise call.excinfo.value

    @pytest.hookimpl(tryfirst=True)
    def pytest_internalerror(excinfo):
        raise excinfo.value


@pytest.fixture
def work_dir():
    work_dir = tempfile.mkdtemp()
    return Path(work_dir)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "timeout_pass: mark test as passing if it runs until timeout"
    )


def pytest_runtest_protocol(item, nextitem):
    marker = item.get_closest_marker("timeout_pass")
    if marker is not None:
        timeout = marker.kwargs.get("timeout", None)
        if timeout is not None:
            start_time = time.time()
            timeout_duration = timeout

            while time.time() - start_time < timeout_duration:
                nextitem()
            pytest.xpass(f"Test passed by running through the timeout of {timeout_duration} seconds.")

    return None
