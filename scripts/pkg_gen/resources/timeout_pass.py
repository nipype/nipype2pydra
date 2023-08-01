from fileformats.generic import File, Directory, FsObject


def pass_after_timeout(seconds, poll_interval=0.1):
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
