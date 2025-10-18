from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class TreeSnapshotService(QObject):
    """Asynchronous application of structure tree model snapshots."""

    def __init__(self, *, manager, model) -> None:
        parent = manager if isinstance(manager, QObject) else None
        super().__init__(parent=parent)
        self._model = model
        self._pending: list[dict] | None = None
        self._on_success: Callable[[], None] | None = None
        self._on_error: Callable[[], None] | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._apply_pending_snapshot)

    def schedule_snapshot(
        self,
        snapshot: list[dict],
        *,
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        """Defer snapshot application until the next Qt event loop cycle."""
        # Create a copy so changes to the original list won't affect application
        self._pending = list(snapshot or [])
        self._on_success = on_success
        self._on_error = on_error
        if not self._timer.isActive():
            self._timer.start(0)

    def _apply_pending_snapshot(self) -> None:
        snapshot = self._pending or []
        on_success = self._on_success
        on_error = self._on_error
        # Reset references before execution to avoid repeated calls
        self._pending = None
        self._on_success = None
        self._on_error = None

        processed_snapshot = self._preprocess_snapshot(snapshot)

        try:
            self._model.set_snapshot(processed_snapshot)
        except Exception:
            logger.exception(
                "TreeSnapshotService: model failed to accept snapshot",
            )
            if on_error:
                try:
                    on_error()
                except Exception:
                    logger.debug(
                        "TreeSnapshotService: on_error callback failed",
                        exc_info=True,
                    )
        else:
            if on_success:
                try:
                    on_success()
                except Exception:
                    logger.debug(
                        "TreeSnapshotService: on_success callback failed",
                        exc_info=True,
                    )

    @staticmethod
    def _extract_icon_path(payload: dict, field: str = "icon") -> str | None:
        """Return trimmed icon path from payload if available."""
        value = payload.get(field)
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
        return None

    def _preprocess_snapshot(self, snapshot: list[dict]) -> list[dict]:
        """Preserve icon paths without blocking the UI thread."""
        processed: list[dict] = []
        for section in snapshot or []:
            if not isinstance(section, dict):
                processed.append(section)
                continue

            section_copy = dict(section)
            icon_path = self._extract_icon_path(section_copy) or section_copy.get("icon_path")
            section_copy["icon_path"] = icon_path

            categories = section_copy.get("categories")
            if isinstance(categories, list):
                processed_categories: list[dict] = []
                for category in categories:
                    if not isinstance(category, dict):
                        processed_categories.append(category)
                        continue
                    category_copy = dict(category)
                    cat_icon_path = self._extract_icon_path(category_copy) or category_copy.get("icon_path")
                    category_copy["icon_path"] = cat_icon_path
                    processed_categories.append(category_copy)
                section_copy["categories"] = processed_categories

            processed.append(section_copy)

        return processed
