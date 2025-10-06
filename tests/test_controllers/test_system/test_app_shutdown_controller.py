"""
Тесты для AppShutdownController.

✅ НОВЫЙ ФАЙЛ: Полное покрытие shutdown логики.
"""

import logging
import time
from typing import List
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtGui import QCloseEvent

from app.controllers.system.app_shutdown_controller import (
    AppShutdownController,
    ShutdownHandler,
    ShutdownPriority,
    create_shutdown_controller,
)


@pytest.fixture
def main_window():
    """Создаёт mock главного окна."""
    window = Mock()
    window.db = Mock()
    window.db.close = Mock()
    window.db.backup = Mock()
    return window


@pytest.fixture
def shutdown_controller(main_window):
    """Создаёт контроллер shutdown."""
    return AppShutdownController(main_window)


@pytest.fixture
def close_event():
    """Создаёт mock события закрытия."""
    event = Mock(spec=QCloseEvent)
    event.accept = Mock()
    event.ignore = Mock()
    return event


class TestShutdownPriority:
    """Тесты приоритизации операций."""

    def test_handlers_execute_in_priority_order(self, shutdown_controller, close_event):
        """Handlers выполняются в порядке приоритетов."""
        # Arrange
        call_order: List[str] = []

        def critical_handler():
            call_order.append("critical")

        def high_handler():
            call_order.append("high")

        def low_handler():
            call_order.append("low")

        shutdown_controller.add_shutdown_handler(
            "low", low_handler, ShutdownPriority.LOW
        )
        shutdown_controller.add_shutdown_handler(
            "critical", critical_handler, ShutdownPriority.CRITICAL
        )
        shutdown_controller.add_shutdown_handler(
            "high", high_handler, ShutdownPriority.HIGH
        )

        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        assert call_order == ["critical", "high", "low"]

    def test_critical_handler_failure_stops_shutdown(
        self, shutdown_controller, close_event
    ):
        """Ошибка в critical handler останавливает shutdown."""
        # Arrange
        executed = []

        def critical_failing():
            executed.append("critical")
            raise RuntimeError("Critical failure")

        def low_handler():
            executed.append("low")

        shutdown_controller.add_shutdown_handler(
            "critical", critical_failing, ShutdownPriority.CRITICAL, critical=True
        )
        shutdown_controller.add_shutdown_handler(
            "low", low_handler, ShutdownPriority.LOW
        )

        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        assert "critical" in executed
        assert "low" not in executed  # Не должен выполниться

    def test_non_critical_handler_failure_continues(
        self, shutdown_controller, close_event
    ):
        """Ошибка в некритичном handler не останавливает shutdown."""
        # Arrange
        executed = []

        def high_failing():
            executed.append("high")
            raise RuntimeError("Non-critical failure")

        def low_handler():
            executed.append("low")

        shutdown_controller.add_shutdown_handler(
            "high", high_failing, ShutdownPriority.HIGH, critical=False
        )
        shutdown_controller.add_shutdown_handler(
            "low", low_handler, ShutdownPriority.LOW
        )

        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        assert executed == ["high", "low"]


class TestTimeouts:
    """Тесты таймаутов."""

    def test_handler_timeout_is_enforced(self, shutdown_controller, close_event):
        """Handler прерывается по таймауту."""
        # Arrange
        def slow_handler():
            time.sleep(2)  # 2 секунды

        shutdown_controller.add_shutdown_handler(
            "slow",
            slow_handler,
            ShutdownPriority.NORMAL,
            timeout=100,  # 100ms таймаут
        )

        # Act
        start = time.monotonic()
        shutdown_controller.perform_shutdown(close_event)
        duration = (time.monotonic() - start) * 1000

        # Assert
        # Должно завершиться быстро (не ждать 2 секунды)
        assert duration < 500  # Не более 500ms

    def test_global_shutdown_timeout(self, shutdown_controller, close_event):
        """Глобальный таймаут shutdown соблюдается."""
        # Arrange
        shutdown_controller.max_shutdown_time = 500  # 500ms

        def slow_handler():
            time.sleep(1)

        for i in range(5):
            shutdown_controller.add_shutdown_handler(
                f"slow_{i}", slow_handler, ShutdownPriority.NORMAL, timeout=300
            )

        # Act
        start = time.monotonic()
        shutdown_controller.perform_shutdown(close_event)
        duration = (time.monotonic() - start) * 1000

        # Assert
        # Должно прерваться по глобальному таймауту
        assert duration < 1000  # Не более 1 секунды


class TestDefaultHandlers:
    """Тесты дефолтных handlers."""

    def test_database_close_handler_registered(self, shutdown_controller):
        """Handler закрытия БД зарегистрирован."""
        # Assert
        handler_names = [h.name for h in shutdown_controller.shutdown_handlers]
        assert "close_database" in handler_names

    def test_database_backup_handler_registered(self, shutdown_controller):
        """Handler бэкапа БД зарегистрирован."""
        # Assert
        handler_names = [h.name for h in shutdown_controller.shutdown_handlers]
        assert "backup_database" in handler_names

    def test_database_close_is_called(self, main_window, shutdown_controller, close_event):
        """db.close() вызывается при shutdown."""
        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        main_window.db.close.assert_called_once()

    def test_database_backup_is_called(
        self, main_window, shutdown_controller, close_event
    ):
        """db.backup() вызывается при shutdown."""
        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        main_window.db.backup.assert_called_once()


class TestCleanup:
    """Тесты cleanup ресурсов."""

    def test_cleanup_is_called_after_shutdown(
        self, shutdown_controller, close_event
    ):
        """cleanup() вызывается после shutdown."""
        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        assert shutdown_controller._cleaned_up is True

    def test_cleanup_is_idempotent(self, shutdown_controller):
        """cleanup() можно вызывать многократно."""
        # Act
        shutdown_controller.cleanup()
        shutdown_controller.cleanup()
        shutdown_controller.cleanup()

        # Assert
        assert shutdown_controller._cleaned_up is True

    def test_cleanup_clears_handlers(self, shutdown_controller):
        """cleanup() очищает список handlers."""
        # Arrange
        shutdown_controller.add_shutdown_handler(
            "test", lambda: None, ShutdownPriority.NORMAL
        )
        assert len(shutdown_controller.shutdown_handlers) > 0

        # Act
        shutdown_controller.cleanup()

        # Assert
        assert len(shutdown_controller.shutdown_handlers) == 0


class TestThreadSafety:
    """Тесты потокобезопасности."""

    def test_duplicate_shutdown_is_ignored(self, shutdown_controller, close_event):
        """Повторный вызов shutdown игнорируется."""
        # Arrange
        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1

        shutdown_controller.add_shutdown_handler(
            "test", handler, ShutdownPriority.NORMAL
        )

        # Act
        shutdown_controller.perform_shutdown(close_event)
        shutdown_controller.perform_shutdown(close_event)  # Повторный вызов

        # Assert
        assert call_count == 1  # Handler вызван только один раз


class TestFactoryFunction:
    """Тесты фабричной функции."""

    def test_create_shutdown_controller_returns_instance(self, main_window):
        """create_shutdown_controller() возвращает экземпляр."""
        # Act
        controller = create_shutdown_controller(main_window)

        # Assert
        assert isinstance(controller, AppShutdownController)
        assert controller.window is main_window

    def test_created_controller_has_default_handlers(self, main_window):
        """Созданный контроллер имеет дефолтные handlers."""
        # Act
        controller = create_shutdown_controller(main_window)

        # Assert
        assert len(controller.shutdown_handlers) > 0
        handler_names = [h.name for h in controller.shutdown_handlers]
        assert "close_database" in handler_names


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_empty_handlers_list(self, main_window, close_event):
        """Shutdown работает с пустым списком handlers."""
        # Arrange
        controller = AppShutdownController(main_window)
        controller.shutdown_handlers.clear()

        # Act & Assert (не должно быть исключений)
        controller.perform_shutdown(close_event)

    def test_handler_with_none_timeout(self, shutdown_controller, close_event):
        """Handler с timeout=None использует дефолтный таймаут."""
        # Arrange
        executed = []

        def handler():
            executed.append("done")

        shutdown_controller.add_shutdown_handler(
            "test", handler, ShutdownPriority.NORMAL, timeout=None
        )

        # Act
        shutdown_controller.perform_shutdown(close_event)

        # Assert
        assert "done" in executed

    def test_handler_exception_is_logged(
        self, shutdown_controller, close_event, caplog
    ):
        """Исключение в handler логируется."""
        # Arrange
        def failing_handler():
            raise ValueError("Test error")

        shutdown_controller.add_shutdown_handler(
            "failing", failing_handler, ShutdownPriority.NORMAL, critical=False
        )

        # Act
        with caplog.at_level(logging.ERROR):
            shutdown_controller.perform_shutdown(close_event)

        # Assert
        assert "Test error" in caplog.text or "Handler 'failing' failed" in caplog.text
