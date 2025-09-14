"""
Базовые типы и классы для фоновых задач работы с БД.
"""

from __future__ import annotations

import inspect
from typing import Callable, Generic, Optional, TypeVar, cast

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

T = TypeVar("T")


class TaskSignals(QObject):
    """Сигналы для фоновых задач.

    - finished(object): эмитится с результатом при успешном завершении
    - error(object): эмитится с исключением при ошибке
    - progress(int): опциональный прогресс 0..100
    - canceled(): задача была отменена
    """

    finished = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(int)
    canceled = pyqtSignal()


class DatabaseTask(QRunnable, Generic[T]):
    """Обёртка QRunnable для выполнения произвольной функции в пуле потоков.

    Никаких зависимостей от UI. Вся обработка ошибок/локов снаружи.
    """

    def __init__(
        self,
        func: Callable[..., T],
        *,
        description: Optional[str] = None,
        reporter: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__()
        self.func = func
        self.signals = TaskSignals()
        self._canceled = False
        self.description = description
        # Внешний колбэк прогресса; может быть None
        self._external_reporter: Optional[Callable[[int], None]] = reporter

    def report_progress(self, value: int) -> None:
        """Сообщить о прогрессе задачи (0..100).

        Всегда эмитит сигнал `signals.progress`, а затем (если передан)
        вызывает внешний колбэк, переданный через `run_db(..., on_progress=...)`.
        """
        try:
            self.signals.progress.emit(int(value))
        except Exception:
            # Гарантируем, что внешний колбэк вызовется даже при проблемах с сигналом
            pass
        try:
            if self._external_reporter is not None:
                self._external_reporter(int(value))
        except Exception:
            # Не прерываем выполнение задачи из-за ошибок пользовательского колбэка
            pass

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
            # Определяем сигнатуру: поддерживаем функции с 0 или 1 позиционным аргументом
            try:
                sig = inspect.signature(self.func)
                params = list(sig.parameters.values())
                pos_params = [
                    p
                    for p in params
                    if p.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                has_var_pos = any(
                    p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
                )

                if has_var_pos or len(pos_params) == 1:
                    func_with_reporter = cast(Callable[[Callable[[int], None]], T], self.func)
                    result = func_with_reporter(self.report_progress)
                else:
                    func_noargs = cast(Callable[[], T], self.func)
                    result = func_noargs()
            except ValueError:
                # Сигнатура недоступна (встроенная/С-функция): по умолчанию вызываем без аргументов
                func_noargs = cast(Callable[[], T], self.func)
                result = func_noargs()
            if self._canceled:
                self.signals.canceled.emit()
                return
            self.signals.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(e)
