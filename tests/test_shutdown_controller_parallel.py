import time
import pytest

from app.controllers.system.app_shutdown_controller import (
    AppShutdownController,
    ShutdownHandler,
    ShutdownPriority,
    ShutdownTimeoutError,
)


class _DummyWindow:
    pass


def _make_controller():
    return AppShutdownController(_DummyWindow())


def test_parallel_handlers_timeout_noncritical_logs_and_fast_handler_runs(caplog):
    ctrl = _make_controller()
    ctrl.parallel_execution = True

    ran_fast = {"v": False}

    def slow():
        time.sleep(0.2)

    def fast():
        ran_fast["v"] = True

    h_slow = ShutdownHandler(
        name="slow_noncrit",
        handler=slow,
        priority=ShutdownPriority.NORMAL,
        timeout=50,
        critical=False,
    )
    h_fast = ShutdownHandler(
        name="fast_ok",
        handler=fast,
        priority=ShutdownPriority.NORMAL,
        timeout=500,
        critical=False,
    )

    caplog.set_level("ERROR")
    # remaining_ms достаточно небольшой, но больше fast
    ctrl._execute_handlers_parallel([h_slow, h_fast], remaining_ms=300)

    assert ran_fast["v"] is True
    assert any("Timeout waiting for parallel handlers" in r.message or "timed out" in r.message for r in caplog.records)


def test_sequential_critical_timeout_raises(caplog):
    ctrl = _make_controller()

    def slow():
        time.sleep(0.2)

    h = ShutdownHandler(
        name="slow_critical_seq",
        handler=slow,
        priority=ShutdownPriority.HIGH,
        timeout=50,
        critical=True,
    )

    caplog.set_level("CRITICAL")
    with pytest.raises(ShutdownTimeoutError):
        ctrl._execute_handlers_sequential([h], remaining_ms=200)
    assert any("timed out" in r.message for r in caplog.records)
