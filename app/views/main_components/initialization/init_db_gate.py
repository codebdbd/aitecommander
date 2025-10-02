"""Модуль для ожидания готовности базы данных.

УЛУЧШЕНИЕ: Использует Protocol для типизации и константы вместо магических чисел.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from PyQt6.QtCore import QTimer

from ..common.constants import Timeout
from ..common.protocols import MainWindowProtocol

logger = logging.getLogger(__name__)


class DbReadyGate:
    """Инкапсулирует ожидание готовности БД по признаку разблокировки окна.

    УЛУЧШЕНИЕ: Использует MainWindowProtocol для строгой типизации.
    
    Считает БД готовой, когда `window.isEnabled()` возвращает True.
    Проверка выполняется периодически таймером (из константы Timeout.DB_POLL_INTERVAL).
    Поддерживает таймаут, конфигурируемый интервал, прямую проверку БД (опционально),
    метрики ожидания и множественные колбэки.
    """

    def __init__(
        self,
        window: MainWindowProtocol,
        poll_interval_ms: int = Timeout.DB_POLL_INTERVAL,
        _logger: Optional[logging.Logger] = None,
    ) -> None:
        self._window = window
        self._logger = _logger or logger
        self._timer: Optional[QTimer] = None
        self._poll_interval_ms: int = poll_interval_ms
        self._pending_callbacks: List[Callable[[], None]] = []
        self._attempts: int = 0
        self._start_time: Optional[float] = None
        self._timeout_remaining: Optional[float] = None  # in seconds

    def ensure_ready_or_wait(
        self,
        on_ready: Callable[[], None],
        on_waiting: Optional[Callable[[], None]] = None,
        timeout_ms: Optional[int] = None,
        db_checker: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Обеспечивает готовность или ждёт, с опциональными параметрами для таймаута, проверки БД и т.д."""
        # Начальная проверка готовности (с опциональной прямой проверкой БД)
        try:
            is_ready = self._is_ready(db_checker)
            if is_ready:
                self._execute_callbacks_and_metrics(on_ready)
                return
        except (RuntimeError, AttributeError, TypeError) as e:
            self._logger.warning(
                "DbReadyGate: ошибка начальной проверки готовности (%s), продолжаем как готовый",
                e,
                exc_info=True,
            )
            self._execute_callbacks_and_metrics(on_ready)
            return

        # Если не готово — оповещаем
        if on_waiting:
            try:
                on_waiting()
            except Exception:
                self._logger.debug(
                    "DbReadyGate: колбэк on_waiting вызвал исключение", exc_info=True
                )

        # Добавляем колбэк в очередь (поддержка множественных)
        self._pending_callbacks.append(on_ready)

        # Инициализируем метрики и таймаут, если это первый вызов
        if self._start_time is None:
            self._start_time = time.time()
            self._attempts = 0
            if timeout_ms is not None:
                self._timeout_remaining = timeout_ms / 1000.0  # Convert to seconds
            else:
                self._timeout_remaining = None

        # Проверяем, не запущен ли уже таймер
        if self._timer is not None:
            self._logger.debug("DbReadyGate: уже опрашиваем; добавляем колбэк в очередь")
            return

        # Запускаем таймер
        self._timer = QTimer(self._window)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._check_and_continue(db_checker))
        self._timer.start(self._poll_interval_ms)

    def _is_ready(self, db_checker: Optional[Callable[[], bool]]) -> bool:
        """Проверяет готовность: сначала прямая проверка БД (если предоставлена), затем окно."""
        if db_checker is not None:
            try:
                if db_checker():
                    return True
            except (RuntimeError, AttributeError, TypeError) as e:
                self._logger.debug(
                    "DbReadyGate: ошибка в прямой проверке БД (%s), продолжаем с проверкой окна",
                    e,
                )

        # Проверка окна
        is_enabled_method = getattr(self._window, "isEnabled", None)
        if callable(is_enabled_method):
            return bool(is_enabled_method())
        return False  # If not callable, assume not ready

    def _check_and_continue(self, db_checker: Optional[Callable[[], bool]]) -> None:
        self._attempts += 1
        current_time = time.time()

        # Проверка таймаута
        if self._timeout_remaining is not None:
            elapsed = current_time - (self._start_time or current_time)
            if elapsed >= self._timeout_remaining:
                self._logger.warning(
                    f"DbReadyGate: таймаут ожидания ({self._timeout_remaining:.2f}с) после {self._attempts} попыток"
                )
                self._dispose_timer()
                self._execute_callbacks_and_metrics()
                return

        # Проверка готовности
        try:
            is_ready = self._is_ready(db_checker)
            if is_ready:
                self._dispose_timer()
                self._execute_callbacks_and_metrics()
            else:
                # Перезапуск таймера
                try:
                    if self._timer is not None:
                        self._timer.start(self._poll_interval_ms)
                except (RuntimeError, AttributeError) as e:
                    self._logger.warning(
                        "DbReadyGate: сбой перезапуска таймера (%s); завершаем ожидание",
                        e,
                        exc_info=True,
                    )
                    self._dispose_timer()
                    self._execute_callbacks_and_metrics()  # Proceed on failure
        except (RuntimeError, AttributeError, TypeError) as e:
            self._logger.error(
                "DbReadyGate: ошибка во время проверки готовности: %s",
                e,
                exc_info=True,
            )
            self._dispose_timer()
            self._logger.warning("DbReadyGate: продолжаем как готовый после сбоя проверки")
            self._execute_callbacks_and_metrics()

    def _execute_callbacks_and_metrics(self, single_callback: Optional[Callable[[], None]] = None) -> None:
        """Выполняет колбэки (всех или указанный) и логирует метрики."""
        callbacks_to_execute = [single_callback] if single_callback else self._pending_callbacks
        for callback in callbacks_to_execute:
            if callback:
                try:
                    callback()
                except (RuntimeError, AttributeError, TypeError, ValueError) as e:
                    self._logger.warning(
                        "DbReadyGate: колбэк on_ready вызвал исключение: %s",
                        e,
                        exc_info=True,
                    )

        if self._start_time is not None:
            wait_time = time.time() - self._start_time
            self._logger.info(
                f"DbReadyGate: готовность достигнута за {wait_time:.2f}с ({self._attempts} попыток)"
            )
            # Сброс метрик
            self._start_time = None
            self._attempts = 0
            self._timeout_remaining = None

        if not single_callback:
            self._pending_callbacks.clear()

    def _dispose_timer(self) -> None:
        """Безопасно останавливает и удаляет таймер."""
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer.deleteLater()
                self._timer = None
        except (RuntimeError, AttributeError) as e:
            self._logger.debug(
                "DbReadyGate: сбой удаления таймера: %s", e, exc_info=True
            )

    def cancel_wait(self, on_cancel: Optional[Callable[[], None]] = None) -> None:
        """Отменяет ожидание, выполняя on_cancel колбэк (если предоставлен)."""
        if self._timer is not None:
            self._dispose_timer()
        self._logger.info("DbReadyGate: ожидание отменено")
        if on_cancel:
            try:
                on_cancel()
            except (RuntimeError, AttributeError, TypeError, ValueError) as e:
                self._logger.warning(
                    "DbReadyGate: колбэк on_cancel вызвал исключение: %s",
                    e,
                    exc_info=True,
                )
        self._pending_callbacks.clear()
        self._start_time = None
        self._attempts = 0
        self._timeout_remaining = None