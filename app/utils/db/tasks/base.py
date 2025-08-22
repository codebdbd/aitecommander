"""
Базовые типы и классы для фоновых задач работы с БД.
"""
from __future__ import annotations

from typing import Callable, Generic, Optional, TypeVar

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

T = TypeVar("T")


class TaskSignals(QObject):
    """Сигналы для фоновых задач.

    - finished(object): эмитится с результатом при успешном завершении
    - error(Exception): эмитится с исключением при ошибке
    - progress(int): опциональный прогресс 0..100
    - canceled(): задача была отменена
    """

    finished = pyqtSignal(object)
    error = pyqtSignal(Exception)
    progress = pyqtSignal(int)
    canceled = pyqtSignal()


class DatabaseTask(QRunnable, Generic[T]):
    """Обёртка QRunnable для выполнения произвольной функции в пуле потоков.

    Никаких зависимостей от UI. Вся обработка ошибок/локов снаружи.
    """

    def __init__(
        self,
        func: Callable[[], T],
        *,
        description: Optional[str] = None,
        reporter: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__()
        self.func = func
        self.signals = TaskSignals()
        self._canceled = False
        self.description = description
        # Если передан репортёр прогресса — прокидываем в него сигнал
        self._reporter = reporter or (lambda value: self.signals.progress.emit(int(value)))

    def cancel(self) -> None:
        self._canceled = True

    def is_canceled(self) -> bool:
        return self._canceled

    # QRunnable
    def run(self) -> None:  # pragma: no cover (Qt thread)
        if self._canceled:
            self.signals.canceled.emit()
            return
        try:
            result = self.func()
            if self._canceled:
                self.signals.canceled.emit()
                return
            self.signals.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(e)
