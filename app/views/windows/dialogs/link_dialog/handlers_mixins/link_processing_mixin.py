"""Mixin handling asynchronous link/path processing in `LinkDialogHandlers`."""

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon

from app.config_data import app_config
from app.models import LinkType
from app.utils.db.api import run_db
from app.utils.links.link_parser import parse_local_link
from app.utils.links.parser.fetcher import fetch_web_link_info
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.ui_helpers import set_icon_to_button

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkProcessingMixin"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class LinkProcessingMixin:
    def _on_path_changed(self, text: str) -> None:
        """Handle path change events."""
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

        # Cancel active job
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                # Log cancellation failure but continue
                logger.debug("Failed to cancel worker: %s", e)

        lt = LinkType.from_value(self.dialog.link_type)
        args_val = self.dialog._get_args_le().text().strip()

        def _emit_if_current(payload: dict[str, Any]) -> None:
            # Emit results only if the task is still current
            if _task_id == self._worker_task_id:
                self.signals.link_info_finished.emit(payload)

        def _emit_error_if_current(message: str) -> None:
            if _task_id == self._worker_task_id:
                self.signals.simple_error.emit(message)

        def _do_work() -> dict[str, Any]:
            if lt == LinkType.WEB:
                # Resolve icon asynchronously to avoid blocking the UI
                info = fetch_web_link_info(
                    path,
                    app_config,
                    force_refresh=False,
                    defer_icon=True,
                    on_icon_ready=lambda icon_path: _emit_if_current(
                        {"title": "", "icon": icon_path}
                    ),
                )
                return {"title": info.get("title"), "icon": info.get("icon")}
            # Local paths
            info = parse_local_link(lt.value, path, app_config, args=args_val)
            return info or {"name": "", "icon": ""}

        handle = run_db(
            _do_work,
            description=f"link_info:{lt.value}",
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
            LinkType.CHROMEAPP,
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
