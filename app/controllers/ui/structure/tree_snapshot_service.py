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
        self._warmup_icons(processed_snapshot)

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

    def _warmup_icons(self, snapshot: list[dict]) -> None:
        """Warm icon cache so tree icons appear without delayed loading."""
        if not snapshot:
            return

        try:
            from PyQt6.QtWidgets import QApplication
            from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
            from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
            from app.utils.ui.qt.gui_exec import is_gui_thread, run_in_gui_thread_sync
        except Exception as exc:  # noqa: BLE001 - defensive import guard
            logger.debug(
                "TreeSnapshotService: icon warmup skipped (imports failed): %s",
                exc,
            )
            setattr(self._model, "_tree_snapshot_icons_ready", False)
            setattr(self._model, "_tree_snapshot_icons_expected", 0)
            setattr(self._model, "_tree_snapshot_icons_warmed", 0)
            return

        app = QApplication.instance()
        if app is None:
            logger.debug("TreeSnapshotService: icon warmup skipped (no QApplication)")
            setattr(self._model, "_tree_snapshot_icons_ready", False)
            setattr(self._model, "_tree_snapshot_icons_expected", 0)
            setattr(self._model, "_tree_snapshot_icons_warmed", 0)
            return

        themed_icons: set[str] = set()
        path_icons: set[str] = set()

        def _collect_icon(value: object) -> None:
            if not isinstance(value, str):
                return
            trimmed = value.strip()
            if not trimmed:
                return
            # Normalize absolute-path cache key if present
            if trimmed.startswith("abspath::"):
                trimmed = trimmed.split("::", 1)[-1]
            if (
                trimmed.startswith(":/")
                or trimmed.startswith("qrc:/")
                or "\\" in trimmed
                or "/" in trimmed
                or (len(trimmed) > 2 and trimmed[1] == ":" and trimmed[2] in ("\\", "/"))
            ):
                path_icons.add(trimmed)
            else:
                themed_icons.add(trimmed)

        for section in snapshot:
            if not isinstance(section, dict):
                continue
            _collect_icon(section.get("icon"))
            _collect_icon(section.get("icon_path"))
            categories = section.get("categories") or []
            for category in categories:
                if not isinstance(category, dict):
                    continue
                _collect_icon(category.get("icon"))
                _collect_icon(category.get("icon_path"))

        total_icons = len(themed_icons) + len(path_icons)
        if total_icons == 0:
            setattr(self._model, "_tree_snapshot_icons_ready", True)
            setattr(self._model, "_tree_snapshot_icons_expected", 0)
            setattr(self._model, "_tree_snapshot_icons_warmed", 0)
            return

        warmed_total = 0

        def _warmup() -> int:
            nonlocal warmed_total
            for icon_name in themed_icons:
                try:
                    icon = icon_cache.get_icon(icon_name, source="tree_snapshot")
                    warmed_total += 1
                except Exception as exc:  # noqa: BLE001 - cache must not break UI
                    logger.debug(
                        "TreeSnapshotService: themed icon warmup failed for '%s': %s",
                        icon_name,
                        exc,
                    )
            for icon_path in path_icons:
                try:
                    icon = create_icon_from_path(icon_path)
                    warmed_total += 1
                except Exception as exc:  # noqa: BLE001 - cache must not break UI
                    logger.debug(
                        "TreeSnapshotService: path icon warmup failed for '%s': %s",
                        icon_path,
                        exc,
                    )
            return warmed_total

        try:
            if is_gui_thread():
                warmed_total = _warmup()
            else:
                warmed_total = run_in_gui_thread_sync(_warmup)
        except Exception:  # noqa: BLE001 - defensive
            logger.debug("TreeSnapshotService: icon warmup execution failed", exc_info=True)
            setattr(self._model, "_tree_snapshot_icons_ready", False)
            setattr(self._model, "_tree_snapshot_icons_expected", total_icons)
            setattr(self._model, "_tree_snapshot_icons_warmed", warmed_total)
            return

        ready = warmed_total >= total_icons
        setattr(self._model, "_tree_snapshot_icons_ready", ready)
        setattr(self._model, "_tree_snapshot_icons_expected", total_icons)
        setattr(self._model, "_tree_snapshot_icons_warmed", warmed_total)

        if warmed_total:
            logger.debug(
                "TreeSnapshotService: warmed %s of %s tree icon(s) before applying snapshot",
                warmed_total,
                total_icons,
            )
