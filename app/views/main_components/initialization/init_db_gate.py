"""Utilities for waiting until the database becomes ready.

Improvement note: relies on Protocol-based typing and shared constants instead of
magic numbers.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from PyQt6.QtCore import QTimer

from ..common.constants import Timeout
from ..common.protocols import MainWindowProtocol

logger = logging.getLogger(__name__)


class DbReadyGate:
    """Encapsulate waiting for database readiness via window state.

    Improvement note: uses `MainWindowProtocol` for strict typing.

    The database is considered ready when ``window.isEnabled()`` returns ``True``.
    Polling occurs via a timer (``Timeout.DB_POLL_INTERVAL``). Supports timeouts,
    configurable intervals, optional direct DB checks, wait metrics, and multiple
    callbacks.
    """

    def __init__(
        self,
        window: MainWindowProtocol,
        poll_interval_ms: int = Timeout.DB_POLL_INTERVAL,
        _logger: logging.Logger | None = None,
    ) -> None:
        self._window = window
        self._logger = _logger or logger
        self._timer: QTimer | None = None
        self._poll_interval_ms: int = poll_interval_ms
        self._pending_callbacks: list[Callable[[], None]] = []
        self._attempts: int = 0
        self._start_time: float | None = None
        self._timeout_remaining: float | None = None  # in seconds

    def ensure_ready_or_wait(
        self,
        on_ready: Callable[[], None],
        on_waiting: Callable[[], None] | None = None,
        timeout_ms: int | None = None,
        db_checker: Callable[[], bool] | None = None,
    ) -> None:
        """Ensure readiness or keep waiting with optional timeout and DB checks."""
        # Initial readiness probe (optionally using direct DB checks)
        try:
            is_ready = self._is_ready(db_checker)
            if is_ready:
                self._execute_callbacks_and_metrics(on_ready)
                return
        except (RuntimeError, AttributeError, TypeError) as e:
            self._logger.warning(
                "DbReadyGate: initial readiness check failed (%s); falling back to ready",
                e,
                exc_info=True,
            )
            self._execute_callbacks_and_metrics(on_ready)
            return

        # Notify when the database is not ready yet
        if on_waiting:
            try:
                on_waiting()
            except Exception:
                self._logger.debug(
                    "DbReadyGate: on_waiting callback raised", exc_info=True
                )

        # Queue callback (support multiple callbacks)
        self._pending_callbacks.append(on_ready)

        # Initialize metrics and timeout for the first invocation
        if self._start_time is None:
            self._start_time = time.time()
            self._attempts = 0
            if timeout_ms is not None:
                self._timeout_remaining = timeout_ms / 1000.0  # Convert to seconds
            else:
                self._timeout_remaining = None

        # Skip setup if a timer is already running
        if self._timer is not None:
            self._logger.debug("DbReadyGate: polling already in progress; callback queued")
            return

        # Start timer polling
        self._timer = QTimer(self._window)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._check_and_continue(db_checker))
        self._timer.start(self._poll_interval_ms)

    def _is_ready(self, db_checker: Callable[[], bool] | None) -> bool:
        """Check readiness using DB callback first, then window state."""
        if db_checker is not None:
            try:
                if db_checker():
                    return True
            except (RuntimeError, AttributeError, TypeError) as e:
                self._logger.debug(
                    "DbReadyGate: direct DB check failed (%s); falling back to window state",
                    e,
                )

        # Window `isEnabled` check
        is_enabled_method = getattr(self._window, "isEnabled", None)
        if callable(is_enabled_method):
            return bool(is_enabled_method())
        return False  # If not callable, assume not ready

    def _check_and_continue(self, db_checker: Callable[[], bool] | None) -> None:
        self._attempts += 1
        current_time = time.time()

        # Timeout handling
        if self._timeout_remaining is not None:
            elapsed = current_time - (self._start_time or current_time)
            if elapsed >= self._timeout_remaining:
                self._logger.warning(
                    "DbReadyGate: wait timeout %.2fs after %s attempts",
                    self._timeout_remaining,
                    self._attempts,
                )
                self._dispose_timer()
                self._execute_callbacks_and_metrics()
                return

        # Evaluate readiness
        try:
            is_ready = self._is_ready(db_checker)
            if is_ready:
                self._dispose_timer()
                self._execute_callbacks_and_metrics()
            else:
                # Restart timer for the next poll
                try:
                    if self._timer is not None:
                        self._timer.start(self._poll_interval_ms)
                except (RuntimeError, AttributeError) as e:
                    self._logger.warning(
                        "DbReadyGate: failed to restart timer (%s); finishing wait",
                        e,
                        exc_info=True,
                    )
                    self._dispose_timer()
                    self._execute_callbacks_and_metrics()  # Proceed on failure
        except (RuntimeError, AttributeError, TypeError) as e:
            self._logger.error(
                "DbReadyGate: readiness check raised: %s",
                e,
                exc_info=True,
            )
            self._dispose_timer()
            self._logger.warning("DbReadyGate: proceeding as ready after check failure")
            self._execute_callbacks_and_metrics()

    def _execute_callbacks_and_metrics(self, single_callback: Callable[[], None] | None = None) -> None:
        """Execute callbacks (all or the provided one) and log wait metrics."""
        callbacks_to_execute = [single_callback] if single_callback else self._pending_callbacks
        for callback in callbacks_to_execute:
            if callback:
                try:
                    callback()
                except (RuntimeError, AttributeError, TypeError, ValueError) as e:
                    self._logger.warning(
                        "DbReadyGate: on_ready callback raised: %s",
                        e,
                        exc_info=True,
                    )

        if self._start_time is not None:
            wait_time = time.time() - self._start_time
            self._logger.info(
                "DbReadyGate: readiness reached in %.2fs (%s attempts)",
                wait_time,
                self._attempts,
            )
            # Reset metrics
            self._start_time = None
            self._attempts = 0
            self._timeout_remaining = None

        if not single_callback:
            self._pending_callbacks.clear()

    def _dispose_timer(self) -> None:
        """Safely stop and dispose of the timer."""
        try:
            if self._timer is not None:
                self._timer.stop()
                self._timer.deleteLater()
                self._timer = None
        except (RuntimeError, AttributeError) as e:
            self._logger.debug(
                "DbReadyGate: timer disposal failed: %s", e, exc_info=True
            )

    def cancel_wait(self, on_cancel: Callable[[], None] | None = None) -> None:
        """Cancel waiting and run ``on_cancel`` if provided."""
        if self._timer is not None:
            self._dispose_timer()
        self._logger.info("DbReadyGate: waiting cancelled")
        if on_cancel:
            try:
                on_cancel()
            except (RuntimeError, AttributeError, TypeError, ValueError) as e:
                self._logger.warning(
                    "DbReadyGate: on_cancel callback raised: %s",
                    e,
                    exc_info=True,
                )
        self._pending_callbacks.clear()
        self._start_time = None
        self._attempts = 0
        self._timeout_remaining = None