import os
import time
import logging
from pathlib import Path
from traceback import format_exc
import tempfile
import threading
from dataclasses import dataclass
import pytest
from _pytest.runner import TestReport


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


def pass_after_timout(seconds, poll_interval=0.1):
    """Cancel the test after a certain period, after which it is assumed that the arguments
    passed to the underying command have passed its internal validation (so we don't have
    to wait until the tool completes)

    Parameters
    ----------
    seconds : int
        the number of seconds to wait until cancelling the test (and marking it as passed)
    """

    def decorator(test_func):
        def wrapper(*args, **kwargs):
            @dataclass
            class TestState:
                """A way of passing a reference to the result that can be updated by
                the test thread"""

                result = None
                exception = None

            state = TestState()

            def test_runner():
                try:
                    state.result = test_func(*args, **kwargs)
                except Exception as e:
                    state.exception = e
                    # raise
                    # state.trace_back = format_exc()
                    # raise

            thread = threading.Thread(target=test_runner)
            thread.start()

            # Calculate the end time for the timeout
            end_time = time.time() + seconds

            while thread.is_alive() and time.time() < end_time:
                time.sleep(poll_interval)

            if thread.is_alive():
                thread.join()
                return state.result

            if state.trace_back:
                raise state.exception

            outcome = "passed after timeout"
            rep = TestReport.from_item_and_call(
                item=args[0],
                when="call",
                excinfo=None,
                outcome=outcome,
                sections=None,
                duration=0,
                keywords=None,
            )
            args[0].ihook.pytest_runtest_logreport(report=rep)

            return state.result

        return wrapper

    return decorator
