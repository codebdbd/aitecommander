"""Mixin handling asynchronous link/path processing in `LinkDialogHandlers`."""

import logging
import threading
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon

from app.config_data.runtime_config import runtime_app_config as app_config
from app.models import LinkType
from app.utils.links.parser.fetcher import fetch_web_link_info
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.utils.ui.db_tasks import run_db

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkProcessingMixin"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class LinkProcessingMixin:
    def _on_path_changed(self, text: str) -> None:
        """Handle path change events."""
        if getattr(self.dialog, "_suspend_auto_processing", False):
            return
        self.dialog._processing_timer.stop()
        # Use configurable debounce delay from the dialog (fallback to 300 ms)
        try:
            debounce_ms = getattr(self.dialog, "PATH_DEBOUNCE_MS", 300)
        except (AttributeError, TypeError):
            debounce_ms = 300
        self.dialog._processing_timer.start(int(debounce_ms) if debounce_ms else 300)

    def trigger_link_processing(self, path: str) -> None:
        """Start link info processing."""
        if not path or self._is_processing:
            return

        if path == self._last_processed_path:
            return

        self._last_processed_path = path
        self._is_processing = True

        # Prevent race conditions
        self._worker_task_id += 1
        _task_id = self._worker_task_id
        task_created_ts = time.perf_counter()
        logger.info(
            "[Trace] link_info task_created id=%s type=%s path=%s processing=%s",
            _task_id,
            lt.value if 'lt' in locals() else getattr(self.dialog, "link_type", "<unknown>"),
            path,
            self._is_processing,
        )

        # Cancel active job
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                # Log cancellation failure but continue
                logger.debug("Failed to cancel worker: %s", e)
        try:
            active_cancel_event = getattr(self, "_active_cancel_event", None)
            if active_cancel_event is not None:
                active_cancel_event.set()
        except Exception:
            logger.debug("Failed to signal active cancel event", exc_info=True)

        cancel_event = threading.Event()
        self._active_cancel_event = cancel_event

        lt = LinkType.from_value(self.dialog.link_type)
        args_val = self.dialog._get_args_le().text().strip()

        def _emit_if_current(payload: dict[str, Any]) -> None:
            # Emit results only if the task is still current AND dialog still exists
            try:
                if _task_id == self._worker_task_id and not getattr(self.dialog, '_is_closing', False):
                    logger.info(
                        "[Trace] link_info emit_current id=%s age=%.2f ms keys=%s",
                        _task_id,
                        (time.perf_counter() - task_created_ts) * 1000.0,
                        sorted(payload.keys()),
                    )
                    self.signals.link_info_finished.emit(payload)
                else:
                    logger.info(
                        "[Trace] link_info emit_stale id=%s current_id=%s closing=%s age=%.2f ms",
                        _task_id,
                        getattr(self, "_worker_task_id", None),
                        getattr(self.dialog, "_is_closing", False),
                        (time.perf_counter() - task_created_ts) * 1000.0,
                    )
            except (AttributeError, RuntimeError):
                # Dialog was deleted, ignore
                pass

        def _emit_error_if_current(message: str) -> None:
            try:
                if _task_id == self._worker_task_id and not getattr(self.dialog, '_is_closing', False):
                    logger.info(
                        "[Trace] link_info error_current id=%s age=%.2f ms message=%s",
                        _task_id,
                        (time.perf_counter() - task_created_ts) * 1000.0,
                        message,
                    )
                    self.signals.simple_error.emit(message)
                else:
                    logger.info(
                        "[Trace] link_info error_stale id=%s current_id=%s closing=%s age=%.2f ms",
                        _task_id,
                        getattr(self, "_worker_task_id", None),
                        getattr(self.dialog, "_is_closing", False),
                        (time.perf_counter() - task_created_ts) * 1000.0,
                    )
            except (AttributeError, RuntimeError):
                # Dialog was deleted, ignore
                pass

        def _do_work() -> dict[str, Any]:
            work_t0 = time.perf_counter()
            logger.info(
                "[Trace] link_info do_work_enter id=%s age=%.2f ms cancelled=%s",
                _task_id,
                (work_t0 - task_created_ts) * 1000.0,
                cancel_event.is_set(),
            )
            if lt == LinkType.WEB:
                # Resolve icon asynchronously to avoid blocking the UI
                fetch_t0 = time.perf_counter()
                logger.info(
                    "[Trace] link_info fetch_start id=%s age=%.2f ms path=%s",
                    _task_id,
                    (fetch_t0 - task_created_ts) * 1000.0,
                    path,
                )
                info = fetch_web_link_info(
                    path,
                    app_config,
                    force_refresh=False,
                    defer_icon=True,
                    schedule_deferred_icon=False,
                    cancel_event=cancel_event,
                )
                fetch_ms = (time.perf_counter() - fetch_t0) * 1000.0
                logger.info(
                    "[Trace] link_info fetch_done id=%s age=%.2f ms fetch=%.2f ms cancelled=%s",
                    _task_id,
                    (time.perf_counter() - task_created_ts) * 1000.0,
                    fetch_ms,
                    cancel_event.is_set(),
                )
                payload_t0 = time.perf_counter()
                payload = {"title": info.get("title"), "icon": info.get("icon")}
                payload_ms = (time.perf_counter() - payload_t0) * 1000.0
                total_ms = (time.perf_counter() - work_t0) * 1000.0
                logger.info(
                    "[Perf] link_info_web id=%s path=%s fetch=%.2f ms payload=%.2f ms total=%.2f ms task_age=%.2f ms",
                    _task_id,
                    path,
                    fetch_ms,
                    payload_ms,
                    total_ms,
                    (time.perf_counter() - task_created_ts) * 1000.0,
                )
                return payload
            # Local paths
            from app.utils.links.link_parser import parse_local_link

            info = parse_local_link(lt.value, path, app_config, args=args_val)
            payload = info or {"name": "", "icon": ""}
            logger.debug(
                "[Perf] link_info_local path=%s total=%.2f ms",
                path,
                (time.perf_counter() - work_t0) * 1000.0,
            )
            return payload

        handle = run_db(
            _do_work,
            description=f"link_info:{lt.value}",
            use_lock=False,  # CRITICAL: Don't hold DB lock during HTTP requests
            on_finished=lambda info: _emit_if_current(info),
            on_error=lambda e: _emit_error_if_current(str(e)),
        )

        # Track active worker handle
        self._active_worker = handle

    def _trigger_link_processing(self) -> None:
        """Internal helper to start link processing from timer."""
        url = self.dialog._get_url_le().text().strip()
        self.trigger_link_processing(url)

    def _on_link_info_fetched(self, info: dict) -> None:
        """Handle fetched link information."""
        self._is_processing = False
        self._active_worker = None
        try:
            self._active_cancel_event = None
        except Exception:
            pass

        # CRITICAL: Don't update UI if dialog is closing/closed
        try:
            if getattr(self.dialog, '_is_closing', False):
                return
        except (AttributeError, RuntimeError):
            # Dialog was deleted
            return

        title = info.get("title") or info.get("name")
        if title and not self.dialog._get_name_le().text().strip():
            self.dialog.ui.set_widget_value("name_le", title)

        icon_path_str = info.get("icon")
        if icon_path_str and Path(icon_path_str).exists():
            self.dialog.icon_name = Path(icon_path_str).name
            set_icon_to_button(self.dialog._get_icon_btn(), icon_path_str)
        else:
            # Fallback using centralized resolver
            try:
                resolved_icon_path = resolve_icon_for_link(
                    {
                        "type": self.dialog.link_type,
                        "icon_path": self.dialog.icon_name or "",
                    }
                )
            except (AttributeError, KeyError, ValueError) as e:
                logger.warning("Failed to resolve icon for link: %s", e)
                resolved_icon_path = ""
            if resolved_icon_path and Path(resolved_icon_path).exists():
                set_icon_to_button(self.dialog._get_icon_btn(), resolved_icon_path)
            else:
                self.dialog._get_icon_btn().setIcon(QIcon())

        if LinkType.from_value(self.dialog.link_type) in (
            LinkType.PROGRAM,
            LinkType.SCRIPT,
        ):
            args = info.get("args", "")
            if not self.dialog._get_args_le().text().strip():
                self.dialog.ui.set_widget_value("args_le", args)

        self._is_processing = False

    def _on_link_info_error(self, error_message: str) -> None:
        """Handle errors raised while fetching link info."""
        # Reset internal processing state
        self._is_processing = False
        self._active_worker = None
        self._last_processed_path = ""
        try:
            self._active_cancel_event = None
        except Exception:
            pass

        # Diagnostic logging
        try:
            link_type = getattr(self.dialog, "link_type", None) or "<unknown>"
            last_path = self._last_processed_path or (
                getattr(self.dialog, "link", {}) or {}
            ).get("url", "")
        except (AttributeError, TypeError, RuntimeError):
            link_type = "<unknown>"
            last_path = ""

        logger.error(
            "Failed to obtain link information (type=%s, path=%s): %s",
            link_type,
            last_path,
            error_message,
        )

        # User-facing error message with diagnostics details
        try:
            self.dialog.show_error(
                self.dialog.tr("Failed to fetch link information."),
                self.dialog.tr("Link processing error"),
                informative_text=self.dialog.tr(
                    "Verify the path/URL is valid and the resource is reachable."
                ),
                details=str(error_message),
                silent=True,
            )
        except (AttributeError, RuntimeError) as e:
            # Log inability to show user-facing error dialog
            logger.warning(
                "Failed to show error dialog to user: %s",
                e,
            )
