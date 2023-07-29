import os
import typing as ty
import time
import logging
from pathlib import Path
import tempfile
import threading
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


def timeout_pass(timeout):
    """Cancel the test after a certain period, after which it is assumed that the arguments
    passed to the underying command have passed its internal validation (so we don't have
    to wait until the tool completes)

    Parameters
    ----------
    timeout : int
        the number of seconds to wait until cancelling the test
    """
    def decorator(test_func):
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [False]
            timeout_event = threading.Event()

            def test_runner():
                try:
                    result[0] = test_func(*args, **kwargs)
                except Exception:
                    exception[0] = True

            thread = threading.Thread(target=test_runner)
            thread.start()
            timeout_event.wait(timeout)

            if thread.is_alive():
                timeout_event.set()
                thread.join()
                return result[0]

            if exception[0]:
                raise Exception("Test raised an exception during execution.")

            return result[0]

        return wrapper

    return decorator
