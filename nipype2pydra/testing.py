def test_line_number_of_function():
    """Test function used to test the detection of a line number of a function."""
    return 1


import logging  # noqa: E402
import asyncio  # noqa: E402
from pydra.engine.core import Result, TaskBase  # noqa: E402
from pydra.engine.workers import ConcurrentFuturesWorker  # noqa: E402


logger = logging.getLogger("pydra")


class PassAfterTimeoutWorker(ConcurrentFuturesWorker):
    """A worker used to test the start-up phase of long running tasks. Tasks are initiated
    and run up until a specified timeout.

    If the task completes before the timeout then results are returned as normal, if not,
    then None is returned instead"""

    def __init__(self, timeout=10, **kwargs):
        """Initialize Worker."""
        super().__init__(n_procs=1)
        self.timeout = timeout
        # self.loop = asyncio.get_event_loop()
        logger.debug("Initialize worker with a timeout of %s seconds", self.timeout)

    def run_el(self, runnable, rerun=False, **kwargs):
        """Run a task."""
        return self.exec_with_timeout(runnable, rerun=rerun)

    async def exec_with_timeout(self, runnable: TaskBase, rerun=False):
        try:
            result = await asyncio.wait_for(
                self.exec_as_coro(runnable, rerun=rerun), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.debug(
                "Killing '%s' task after timeout of %s seconds and assuming it has run successfully",
                runnable.name,
                self.timeout,
            )
            result = Result(output=None, runtime=None, errored=False)
        else:
            logger.debug(
                "'%s' task completed successfully within the timeout period of %s seconds",
                runnable.name,
                self.timeout,
            )
        return result
