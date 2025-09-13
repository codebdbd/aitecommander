import time
import types
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
    # Используем минимальное окно; не вызываем perform_shutdown в тестах
    return AppShutdownController(_DummyWindow())


def test_single_handler_completes(monkeypatch, caplog):
    ctrl = _make_controller()

    called = []

    def handler():
        called.append(True)

    sh = ShutdownHandler(
        name="ok",
        handler=handler,
        priority=ShutdownPriority.NORMAL,
        timeout=500,
        critical=False,
    )

    caplog.set_level("DEBUG")
    ctrl._execute_single_handler(sh)
    assert called
    assert any("completed successfully" in r.message for r in caplog.records)


def test_single_handler_timeout_noncritical_logs_and_returns(caplog):
    ctrl = _make_controller()

    def handler():
        time.sleep(0.2)

    sh = ShutdownHandler(
        name="slow",
        handler=handler,
        priority=ShutdownPriority.NORMAL,
        timeout=50,  # 50 ms
        critical=False,
    )

    caplog.set_level("ERROR")
    ctrl._execute_single_handler(sh)
    assert any("timed out" in r.message for r in caplog.records)


def test_single_handler_timeout_critical_raises(caplog):
    ctrl = _make_controller()

    def handler():
        time.sleep(0.2)

    sh = ShutdownHandler(
        name="slow_critical",
        handler=handler,
        priority=ShutdownPriority.HIGH,
        timeout=50,
        critical=True,
    )

    caplog.set_level("CRITICAL")
    with pytest.raises(ShutdownTimeoutError):
        ctrl._execute_single_handler(sh)
    assert any("timed out" in r.message for r in caplog.records)


def test_single_handler_exception_noncritical_logs_error(caplog):
    ctrl = _make_controller()

    def handler():
        raise ValueError("boom")

    sh = ShutdownHandler(
        name="fail",
        handler=handler,
        priority=ShutdownPriority.NORMAL,
        timeout=500,
        critical=False,
    )

    caplog.set_level("ERROR")
    ctrl._execute_single_handler(sh)
    assert any("failed" in r.message for r in caplog.records)


def test_single_handler_exception_critical_raises(caplog):
    ctrl = _make_controller()

    def handler():
        raise RuntimeError("boom critical")

    sh = ShutdownHandler(
        name="fail_critical",
        handler=handler,
        priority=ShutdownPriority.CRITICAL,
        timeout=500,
        critical=True,
    )

    caplog.set_level("CRITICAL")
    with pytest.raises(RuntimeError):
        ctrl._execute_single_handler(sh)
    assert any("failed" in r.message for r in caplog.records)
