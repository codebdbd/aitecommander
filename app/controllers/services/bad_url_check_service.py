"""Background service for running bad URL checks in a worker thread."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from app.controllers.system.app_shutdown_controller import (
    AppShutdownController,
    ShutdownPriority,
)
from app.core.worker_manager import WorkerManager
from app.models.workers.bad_url_check_worker import BadUrlCheckWorker

if TYPE_CHECKING:
    from app.models.database import Database

logger = logging.getLogger(__name__)


class BadUrlCheckService(QObject):
    """Background service for running bad URL checks in a worker thread."""

    progress = pyqtSignal(int, int, str)
    bad_url_found = pyqtSignal(dict)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, db: Database, parent: QObject | None = None) -> None:
        """Create the service with database access and optional parent."""

        super().__init__(parent)
        self.db = db
        self._current_worker: BadUrlCheckWorker | None = None
        self._dialog: QObject | None = None
        self._shutdown_controller: AppShutdownController | None = None
        self._shutdown_handler_name = f"bad_url_check_service_cancel_{id(self)}"
        self._parent_ref: QObject | None = parent

    def is_running(self) -> bool:
        """Return True when a worker is currently processing."""

        return self._current_worker is not None

    def set_dialog(self, dialog: QObject | None) -> None:
        """Store dialog reference for activation from background thread."""

        self._dialog = dialog

    def show_dialog(self) -> None:
        """Show dialog if it is hidden while the check is running."""

        if self._dialog and not self._dialog.isVisible():
            self._dialog.show()
            self._dialog.raise_()
            self._dialog.activateWindow()

    def start_check(
        self,
        max_workers: int = 10,
        timeout: int = 3,
        *,
        check_ssl: bool = True,
        auto_start: bool = True,
    ) -> bool:
        """Start background URL checking if not already running."""

        if self.is_running():
            logger.warning("[bad_url_check_service] Check already running")
            return False

        try:
            worker = BadUrlCheckWorker(
                db=self.db,
                max_workers=max_workers,
                timeout=timeout,
                check_ssl=check_ssl,
            )
            worker.signals.progress.connect(self._on_progress)
            worker.signals.bad_url_found.connect(self._on_bad_url_found)
            worker.signals.finished.connect(self._on_finished)
            worker.signals.error.connect(self._on_error)

            self._current_worker = worker
            self._ensure_shutdown_handler()

            if auto_start:
                WorkerManager.run(worker)
                logger.info("[bad_url_check_service] Bad URL check started")

            return True
        except Exception as exc:
            logger.error(
                "[bad_url_check_service] Failed to start check: %s", exc, exc_info=True
            )
            self._current_worker = None
            self.error.emit(
                self.tr("Failed to start URL check: {error}").format(error=exc)
            )
            return False

    def cancel_check(self) -> bool:
        """Cancel currently running URL check if any."""

        if not self.is_running():
            logger.warning("[bad_url_check_service] No check running to cancel")
            return False
        try:
            if self._current_worker:
                self._current_worker.cancel()
                logger.info("[bad_url_check_service] Cancellation requested")
            return True
        except Exception as exc:
            logger.error("[bad_url_check_service] Failed to cancel check: %s", exc)
            return False

    def _on_progress(self, current: int, total: int, message: str) -> None:
        """Emit progress updates from the worker."""

        self.progress.emit(current, total, message)

    def _on_bad_url_found(self, bad_url_info: dict) -> None:
        """Forward newly discovered bad URL information."""

        self.bad_url_found.emit(bad_url_info)

    def _on_finished(self, bad_urls: list) -> None:
        """Handle successful completion of the worker."""

        self._current_worker = None
        self._unregister_shutdown_handler()
        self.finished.emit(bad_urls)
        logger.info(
            "[bad_url_check_service] Check completed: %s bad URLs found",
            len(bad_urls),
        )

    def _on_error(self, error_message: str) -> None:
        """Handle worker failure."""

        self._current_worker = None
        self._unregister_shutdown_handler()
        self.error.emit(error_message)
        logger.error("[bad_url_check_service] Check error: %s", error_message)

    def _ensure_shutdown_handler(self) -> None:
        """Register shutdown handler so checks are cancelled gracefully."""

        if self._shutdown_controller is not None:
            return
        parent = self._parent_ref
        controller: AppShutdownController | None = None
        try:
            while parent is not None:
                candidate = getattr(parent, "app_shutdown", None)
                if isinstance(candidate, AppShutdownController):
                    controller = candidate
                    break
                parent = parent.parent()
        except Exception:  # pragma: no cover - defensive
            controller = None

        if controller is None:
            return
        try:
            controller.add_shutdown_handler(
                self._shutdown_handler_name,
                self._handle_shutdown_request,
                priority=ShutdownPriority.HIGH,
                timeout=5000,
                critical=False,
            )
            self._shutdown_controller = controller
            logger.debug("[bad_url_check_service] Shutdown handler registered")
        except Exception as exc:  # pragma: no cover
            logger.debug(
                "[bad_url_check_service] Failed to register shutdown handler: %s",
                exc,
            )

    def _unregister_shutdown_handler(self) -> None:
        """Remove shutdown handler after work completes."""

        controller = self._shutdown_controller
        if controller is None:
            return
        try:
            removed = controller.remove_shutdown_handler(self._shutdown_handler_name)
            if removed:
                logger.debug("[bad_url_check_service] Shutdown handler unregistered")
        except Exception as exc:  # pragma: no cover
            logger.debug(
                "[bad_url_check_service] Failed to unregister shutdown handler: %s",
                exc,
            )
        finally:
            self._shutdown_controller = None

    def _handle_shutdown_request(self, timeout_ms: int | None = None) -> bool:
        """Cancel worker during application shutdown and wait for teardown."""

        if self.is_running():
            try:
                self.cancel_check()
            except Exception as exc:  # pragma: no cover
                logger.debug(
                    "[bad_url_check_service] Cancel during shutdown failed: %s", exc
                )
            wait_for = max(0, int(timeout_ms or 0))
            if wait_for:
                try:
                    WorkerManager.shutdown(wait_for)
                except Exception as exc:  # pragma: no cover
                    logger.debug(
                        "[bad_url_check_service] WorkerManager shutdown failed: %s",
                        exc,
                    )
        return True


__all__ = ["BadUrlCheckService"]
