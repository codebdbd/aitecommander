import time
import logging

from app.controllers.system.app_shutdown_controller import (
    AppShutdownController,
    ShutdownHandler,
    ShutdownPriority,
)


class _DummyWindow:
    pass


def _make_controller():
    return AppShutdownController(_DummyWindow())


def test_global_deadline_exceeded_before_any_handler(caplog):
    ctrl = _make_controller()
    # Очищаем дефолтные обработчики, чтобы тест был детерминированным
    ctrl.shutdown_handlers = []

    called = []

    def will_not_run():
        called.append(True)

    # Регистрируем пару обработчиков одной приоритетной группы
    ctrl.shutdown_handlers.extend(
        [
            ShutdownHandler("h1", will_not_run, ShutdownPriority.HIGH, timeout=100, critical=False),
            ShutdownHandler("h2", will_not_run, ShutdownPriority.HIGH, timeout=100, critical=False),
        ]
    )

    # Смоделируем истёкший общий дедлайн: max_total_time маленький, старт был давно
    ctrl.max_shutdown_time = 1  # 1 ms общий дедлайн
    ctrl._shutdown_started_ts = time.monotonic() - 1.0  # прошло уже ~1000 мс

    caplog.set_level(logging.ERROR)
    ctrl._execute_shutdown_sequence()

    # Проверяем, что зафиксирован факт превышения дедлайна и обработчики не запускались
    assert any(
        "Global shutdown deadline exceeded before priority" in r.message for r in caplog.records
    )
    assert called == []


def test_sequential_deadline_exceeded_during_handlers(caplog):
    ctrl = _make_controller()

    called = []

    def h():
        called.append(True)

    caplog.set_level(logging.ERROR)
    # remaining_ms <= 0 означает немедленное превышение дедлайна
    ctrl._execute_handlers_sequential([
        ShutdownHandler("h1", h, ShutdownPriority.NORMAL, timeout=100, critical=False),
        ShutdownHandler("h2", h, ShutdownPriority.NORMAL, timeout=100, critical=False),
    ], remaining_ms=0)

    assert any(
        "Global shutdown deadline exceeded during sequential handlers" in r.message
        for r in caplog.records
    )
    # Ни один handler не должен был вызваться
    assert called == []
