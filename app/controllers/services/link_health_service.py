"""Service for managing background local link health checks (Health Radar)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, pyqtSignal

from app.controllers.system.app_shutdown_controller import (
    AppShutdownController,
    ShutdownPriority,
)
from app.core.worker_manager import WorkerManager
from app.models.workers.link_health_worker import (
    LinkHealthWorker,
    propagate_folder_relink,
)

if TYPE_CHECKING:
    from app.models import Database

logger = logging.getLogger(__name__)


class LinkHealthService(QObject):
    """Service for checking local link paths and coordinating relink recovery."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    issue_found = pyqtSignal(dict)  # issue metadata dict
    finished = pyqtSignal(list)  # list of all found issues
    error = pyqtSignal(str)  # error message

    def __init__(
        self,
        db: Database,
        parent: QObject | None = None,
        shutdown_controller: AppShutdownController | None = None,
    ) -> None:
        super().__init__(parent if isinstance(parent, QObject) else None)
        self.db = db
        self.current_worker: LinkHealthWorker | None = None
        self._active_dialog: Any = None
        self._shutdown_controller: AppShutdownController | None = shutdown_controller
        self._shutdown_handler_name = f"link_health_service_cancel_{id(self)}"
        self._parent_ref: Any = parent

    def start_check(
        self,
        *,
        max_search_dirs: int = 120,
        auto_start: bool = True,
    ) -> bool:
        """Start background local path health scan."""
        if self.current_worker is not None:
            logger.warning("[link_health] Check already in progress")
            self.error.emit(
                QCoreApplication.translate(
                    "LinkHealthService",
                    "Local paths check is already in progress. Please wait for completion.",
                )
            )
            return False

        try:
            logger.info("[link_health] Starting local paths health check...")
            worker = LinkHealthWorker(self.db, max_search_dirs=max_search_dirs)
            self.current_worker = worker

            worker.signals.progress.connect(self._on_progress)
            worker.signals.issue_found.connect(self._on_issue_found)
            worker.signals.finished.connect(self._on_finished)
            worker.signals.error.connect(self._on_error)

            self._ensure_shutdown_handler()

            if auto_start:
                WorkerManager.run(worker)
            return True
        except Exception as exc:
            logger.error("[link_health] Failed to start check: %s", exc, exc_info=True)
            self.current_worker = None
            self.error.emit(str(exc))
            return False

    def cancel_check(self) -> bool:
        """Cancel the running health scan if active."""
        worker = self.current_worker
        if worker is None:
            return False
        logger.info("[link_health] Cancelling local paths check...")
        try:
            worker.cancel()
        except Exception as exc:
            logger.debug("[link_health] Cancel worker failed: %s", exc)
        try:
            worker.signals.progress.disconnect(self._on_progress)
            worker.signals.issue_found.disconnect(self._on_issue_found)
            worker.signals.finished.disconnect(self._on_finished)
            worker.signals.error.disconnect(self._on_error)
        except (TypeError, RuntimeError):
            pass
        self.current_worker = None
        self._unregister_shutdown_handler()
        return True

    def is_running(self) -> bool:
        """Return True if a local path check is currently running."""
        return self.current_worker is not None

    def set_dialog(self, dialog: Any) -> None:
        """Store reference to the active HealthRadarDialog."""
        self._active_dialog = dialog

    def show_dialog(self) -> bool:
        """Show and activate the existing dialog if available."""
        if self._active_dialog is None:
            return False
        try:
            if sip.isdeleted(self._active_dialog):
                self._active_dialog = None
                return False
        except Exception:
            try:
                self._active_dialog.objectName()
            except RuntimeError:
                self._active_dialog = None
                return False

        try:
            self._active_dialog.show()
            self._active_dialog.raise_()
            self._active_dialog.activateWindow()
            return True
        except RuntimeError:
            self._active_dialog = None
            return False

    def propagate_relink(
        self,
        items: list[dict[str, Any]],
        old_path_str: str,
        new_path_str: str,
    ) -> list[int]:
        """Propagate a resolved folder relocation across other broken items."""
        existing_keys: set[tuple[int, str, str, str]] = set()
        try:
            rows = self.db.connection.execute(
                "SELECT category_id, name, url, args FROM link"
            ).fetchall()
            for r in rows:
                rd = dict(r)
                existing_keys.add(
                    (
                        int(rd.get("category_id") or 0),
                        str(rd.get("name") or ""),
                        str(rd.get("url") or ""),
                        str(rd.get("args") or ""),
                    )
                )
        except Exception:
            logger.debug(
                "[link_health] Failed to query existing keys for propagation",
                exc_info=True,
            )
        return propagate_folder_relink(
            items,
            old_path_str,
            new_path_str,
            existing_keys=existing_keys or None,
        )

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(current, total, message)

    def _on_issue_found(self, issue_info: dict[str, Any]) -> None:
        self.issue_found.emit(issue_info)

    def _on_finished(self, issues: list[dict[str, Any]]) -> None:
        logger.info("[link_health] Check completed: %d issues found", len(issues))
        self.current_worker = None
        self._unregister_shutdown_handler()
        self.finished.emit(issues)

    def _on_error(self, error_msg: str) -> None:
        logger.error("[link_health] Check failed: %s", error_msg)
        self.current_worker = None
        self._unregister_shutdown_handler()
        self.error.emit(error_msg)

    def _ensure_shutdown_handler(self) -> None:
        """Register shutdown handler with AppShutdownController if available."""
        controller = self._shutdown_controller
        if controller is None:
            parent = self._parent_ref
            try:
                while parent is not None:
                    candidate = getattr(parent, "app_shutdown", None)
                    if isinstance(candidate, AppShutdownController):
                        controller = candidate
                        break
                    parent_fn = getattr(parent, "parent", None)
                    parent = parent_fn() if callable(parent_fn) else None
            except Exception:
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
        except Exception as exc:
            logger.debug(
                "[link_health] Failed to register shutdown handler: %s", exc
            )

    def _unregister_shutdown_handler(self) -> None:
        controller = self._shutdown_controller
        if controller is None:
            return
        try:
            controller.remove_shutdown_handler(self._shutdown_handler_name)
        except Exception as exc:
            logger.debug(
                "[link_health] Failed to unregister shutdown handler: %s", exc
            )

    def _handle_shutdown_request(self, timeout_ms: int | None = None) -> bool:
        if self.is_running():
            try:
                self.cancel_check()
            except Exception:
                pass
            wait_for = max(0, int(timeout_ms or 0))
            if wait_for:
                try:
                    WorkerManager.shutdown(wait_for)
                except Exception:
                    pass
        return True
