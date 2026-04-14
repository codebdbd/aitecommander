from __future__ import annotations

import logging
import weakref
from typing import Callable

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from i18n.language_service import LanguageService
from i18n.locale_utils import format_number

logger = logging.getLogger(__name__)

class StatusBarWidget(QStatusBar):
    """Dedicated status bar responsible for rendering and updating UI state."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._window_ref = weakref.ref(window)
        self._language_service = LanguageService.instance()
        self._message_label = QLabel(self)
        self._path_label = QLabel(self)
        self._path_label.setObjectName("pathLabel")
        self._path_label.setMinimumWidth(app_config.ui.get_path_label_min_width())
        self._db_status_label = QLabel(self)
        self._db_status_label.setObjectName("dbStatusLabel")
        self._links_count_label = QLabel(self)
        self._links_count_label.setObjectName("linksCountLabel")
        self._setup_layout()
        self._language_handler: Callable[[str], None] | None = None
        self._connect_language_service()
        self.retranslate()

    # --- Public API -------------------------------------------------------

    def retranslate(self) -> None:
        """Update static strings after a language change."""
        self._message_label.setText(QCoreApplication.translate("StatusBar", "Ready"))
        self._path_label.setText(QCoreApplication.translate("StatusBar", "Path: "))
        self._db_status_label.setText(
            QCoreApplication.translate("StatusBar", "Database: connected")
        )
        self._links_count_label.setText(
            QCoreApplication.translate("StatusBar", "Links: {count}").format(
                count=format_number(0)
            )
        )
        self.refresh()

    def set_message(self, text: str) -> None:
        """Expose a safe way to override the primary status message."""
        self._set_text_if_changed(self._message_label, text)

    def refresh(self) -> None:
        """Pull live data from the window and display current state."""
        owner = self._owner()
        if owner is None:
            return
        self._update_counter(owner)
        self._update_db_status(owner)
        self._update_path(owner)

    # --- Internal helpers -------------------------------------------------

    def _owner(self):
        return self._window_ref()

    def _connect_language_service(self) -> None:
        def _on_language_changed(lang_code: str) -> None:
            logger.debug("StatusBar: language changed -> %s", lang_code)
            self.retranslate()

        self._language_handler = _on_language_changed
        self._language_service.languageChanged.connect(_on_language_changed)
        self.destroyed.connect(self._disconnect_language_handler)  # type: ignore[arg-type]

    def _disconnect_language_handler(self) -> None:
        if self._language_handler is None:
            return
        try:
            self._language_service.languageChanged.disconnect(self._language_handler)
        except TypeError:
            logger.debug("StatusBar: language handler already disconnected")
        finally:
            self._language_handler = None

    def _setup_layout(self) -> None:
        # Небольшие вертикальные отступы, чтобы текст не обрезался сверху
        self.setContentsMargins(*app_config.ui.get_status_bar_margins())
        # Message + path stretch on the left, counters stay on the right
        left_container = QWidget(self)
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self._message_label.setContentsMargins(
            *app_config.ui.get_status_bar_message_margins()
        )
        self._path_label.setContentsMargins(*app_config.ui.get_status_bar_path_margins())
        self._db_status_label.setContentsMargins(*app_config.ui.get_status_bar_db_margins())
        self._links_count_label.setContentsMargins(
            *app_config.ui.get_status_bar_links_margins()
        )
        left_layout.addWidget(self._message_label)
        left_layout.addWidget(self._path_label, 1)
        self.addWidget(left_container, 1)
        self.addPermanentWidget(self._db_status_label)
        self.addPermanentWidget(self._links_count_label)

    def _update_counter(self, window) -> None:
        stack = getattr(window, "stack", None)
        tiles_active = False
        if stack is not None:
            try:
                tiles_active = (
                    stack.currentIndex() == app_config.ui.get_stack_index_tiles()
                )
            except Exception:
                logger.debug("StatusBar: failed to read stack index", exc_info=True)

        widgets = getattr(window, "widgets", None)
        tiles_widget = widgets.tiles if widgets else getattr(window, "tiles", None)

        if tiles_active and tiles_widget is not None:
            count = self._safe_int(getattr(tiles_widget, "get_categories_count", None))
            text = QCoreApplication.translate("StatusBar", "Categories: {count}").format(
                count=format_number(count)
            )
        else:
            links = getattr(window, "links", None)
            get_row_count = getattr(links, "get_row_count", None)
            count = self._safe_int(get_row_count) if callable(get_row_count) else 0
            text = QCoreApplication.translate("StatusBar", "Links: {count}").format(
                count=format_number(count)
            )

        self._set_text_if_changed(self._links_count_label, text)

    def _update_db_status(self, window) -> None:
        controller = getattr(window, "database_controller", None)
        db = getattr(controller, "db", None)
        is_connected = getattr(db, "is_connected", None)
        connected = False
        if callable(is_connected):
            try:
                connected = bool(is_connected())
            except Exception:
                logger.debug("StatusBar: DB connectivity check failed", exc_info=True)
        text = QCoreApplication.translate(
            "StatusBar",
            "Database: connected" if connected else "Database: disconnected",
        )
        self._set_text_if_changed(self._db_status_label, text)

    def _update_path(self, window) -> None:
        parts = []
        parts.extend(self._collect_tree_parts(window))
        prefix = self._read_current_sphere(window)
        if prefix:
            parts.insert(0, prefix)
        link_name = self._read_selected_link(window)
        if link_name:
            parts.append(link_name)

        if parts:
            separator = QCoreApplication.translate("StatusBar", " > ")
            text = QCoreApplication.translate("StatusBar", "Path: {path}").format(
                path=separator.join(parts)
            )
        else:
            text = QCoreApplication.translate("StatusBar", "Path: ")
        self._set_text_if_changed(self._path_label, text)

    def _collect_tree_parts(self, window) -> list[str]:
        tree = getattr(window, "tree", None)
        if tree is None:
            return []
        try:
            idx = tree.currentIndex()
        except Exception:
            logger.debug("StatusBar: tree currentIndex failed", exc_info=True)
            return []
        if not idx or not idx.isValid():
            return []

        parts: list[str] = []
        current = idx
        while current.isValid():
            text = current.data()
            if isinstance(text, str) and text.strip():
                parts.insert(0, text.strip())
            current = current.parent()
        return parts

    def _read_current_sphere(self, window) -> str:
        structure = getattr(window, "structure_business", None)
        if structure is None:
            return ""
        sphere_id = getattr(structure, "current_sphere_id", None)
        if sphere_id is None:
            return ""
        try:
            sphere = structure.get_sphere_by_id(sphere_id)
        except Exception:
            logger.debug("StatusBar: failed to read sphere data", exc_info=True)
            return ""
        name = sphere.get("name") if isinstance(sphere, dict) else None
        return name.strip() if isinstance(name, str) else ""

    def _read_selected_link(self, window) -> str:
        table = getattr(window, "table", None)
        if table is None:
            return ""
        try:
            idx = table.currentIndex()
        except Exception:
            logger.debug("StatusBar: failed to read table index", exc_info=True)
            return ""
        if not idx or not idx.isValid():
            selection_model = table.selectionModel()
            idx = selection_model.currentIndex() if selection_model else None
        if not idx or not idx.isValid():
            return ""
        name_idx = idx.sibling(idx.row(), 1)
        data = name_idx.data() if name_idx.isValid() else None
        return data.strip() if isinstance(data, str) else ""

    def _safe_int(self, getter: Callable[[], int] | None) -> int:
        if getter is None:
            return 0
        try:
            return int(getter())
        except Exception:
            logger.debug("StatusBar: failed to convert counter value", exc_info=True)
            return 0

    @staticmethod
    def _set_text_if_changed(label: QLabel, text: str) -> None:
        if label.text() != text:
            label.setText(text)


def setup_status_bar(window) -> StatusBarWidget:
    """Attach a managed status bar to the given window."""
    status_bar = StatusBarWidget(window)
    window.setStatusBar(status_bar)
    window._retranslate_status_bar = status_bar.retranslate
    window._refresh_status_bar = status_bar.refresh
    _apply_fixed_height(status_bar)
    return status_bar


def _apply_fixed_height(status_bar: QStatusBar) -> None:
    try:
        hint = status_bar.sizeHint().height() or 0
        font_h = status_bar.fontMetrics().height() if status_bar.fontMetrics() else 0
        padding = app_config.ui.get_status_bar_extra_height_padding()
        min_height = app_config.ui.get_status_bar_min_height()
        height = max(hint, font_h + padding, min_height)
    except (AttributeError, ValueError, TypeError):
        height = app_config.ui.get_status_bar_min_height()

    try:
        status_bar.setMinimumHeight(height)
    except Exception:
        logger.debug("StatusBar: failed to set minimum height", exc_info=True)


def update_status_bar(window) -> None:
    """Refresh the status bar if the window owns a StatusBarWidget."""
    status = _get_status_bar(window)
    if status is not None:
        status.refresh()


def set_status_message(window, text: str) -> bool:
    """Update the primary status message. Returns ``True`` if updated."""
    status = _get_status_bar(window)
    if status is not None:
        status.set_message(text)
        return True
    return False


def _get_status_bar(window) -> StatusBarWidget | None:
    status_method = getattr(window, "statusBar", None)
    status = status_method() if callable(status_method) else None
    if isinstance(status, StatusBarWidget):
        return status
    if status is not None:
        logger.debug(
            "StatusBar: window owns %s, skipping managed refresh",
            type(status).__name__,
        )
    return None
