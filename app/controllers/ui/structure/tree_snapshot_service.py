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

        # Преобразуем icon_path в QIcon ДО передачи в модель
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

    def _preprocess_snapshot(self, snapshot: list[dict]) -> list[dict]:
        """Преобразуем icon_path в QIcon для корректной работы модели."""
        try:
            from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
        except ImportError:
            logger.debug("Icon cache not available, skipping preprocessing")
            return snapshot

        processed = []
        for section in snapshot:
            if not isinstance(section, dict):
                processed.append(section)
                continue

            # Преобразуем icon_path секции в QIcon
            section_copy = dict(section)
            icon_path = section.get("icon_path")
            # Check if icon_path is valid non-empty string after stripping
            if icon_path and isinstance(icon_path, str):
                icon_path_clean = icon_path.strip()
                if icon_path_clean:
                    try:
                        section_copy["icon"] = icon_cache.get_icon(icon_path_clean, source="tree_snapshot")
                    except Exception:
                        section_copy["icon"] = None
                else:
                    section_copy["icon"] = None
            else:
                section_copy["icon"] = None

            # Преобразуем icon_path категорий в QIcon
            if "categories" in section:
                processed_categories = []
                for category in section["categories"]:
                    if not isinstance(category, dict):
                        processed_categories.append(category)
                        continue

                    category_copy = dict(category)
                    icon_path = category.get("icon_path")
                    # Check if icon_path is valid non-empty string after stripping
                    if icon_path and isinstance(icon_path, str):
                        icon_path_clean = icon_path.strip()
                        if icon_path_clean:
                            try:
                                category_copy["icon"] = icon_cache.get_icon(icon_path_clean, source="tree_snapshot")
                            except Exception:
                                category_copy["icon"] = None
                        else:
                            category_copy["icon"] = None
                    else:
                        category_copy["icon"] = None

                    processed_categories.append(category_copy)
                section_copy["categories"] = processed_categories

            processed.append(section_copy)

        return processed
