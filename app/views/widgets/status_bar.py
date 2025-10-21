# app/views/status_bar.py

import logging

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

from app.config_data import app_config
from i18n.language_service import LanguageService
from i18n.locale_utils import format_number

logger = logging.getLogger(__name__)

_TR_CONTEXT = "StatusBar"

_STATUS_BAR_STRINGS = [
    QT_TRANSLATE_NOOP(_TR_CONTEXT, "Ready"),
    QT_TRANSLATE_NOOP(_TR_CONTEXT, "Path: "),
    QT_TRANSLATE_NOOP(_TR_CONTEXT, "Database: connected"),
    QT_TRANSLATE_NOOP(_TR_CONTEXT, "Database: disconnected"),
    QT_TRANSLATE_NOOP(_TR_CONTEXT, "Links: %1"),
    QT_TRANSLATE_NOOP(_TR_CONTEXT, "Categories: %1"),
]

# Hints for pylupdate6: ensure translation catalogs register these texts even though
# we resolve them dynamically at runtime.
if False:  # pragma: no cover
    QCoreApplication.translate("StatusBar", "Ready")
    QCoreApplication.translate("StatusBar", "Path: ")
    QCoreApplication.translate("StatusBar", "Database: connected")
    QCoreApplication.translate("StatusBar", "Database: disconnected")
    QCoreApplication.translate("StatusBar", "Links: %1")
    QCoreApplication.translate("StatusBar", "Categories: %1")


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


def _arg(template: str, *args: str) -> str:
    result = template
    for idx, value in enumerate(args, 1):
        result = result.replace(f"%{idx}", value)
    return result


def setup_status_bar(window) -> QStatusBar:
    """Create and configure the main window status bar.

    Adds persistent widgets:
    - db_status_label: database connection status
    - path_label: path in the structure hierarchy
    - links_count_label: number of links in the current view

    Returns the created QStatusBar.
    """
    status = QStatusBar(window)
    window.setStatusBar(status)
    # External margins for the status bar: 6px left/right
    status.setContentsMargins(6, 0, 6, 0)

    window.db_status_label = QLabel()
    window.db_status_label.setObjectName("dbStatusLabel")
    window.path_label = QLabel()
    window.path_label.setObjectName("pathLabel")
    window.path_label.setMinimumWidth(app_config.ui.get_path_label_min_width())
    window.links_count_label = QLabel()
    window.links_count_label.setObjectName("linksCountLabel")
    window.message_label = QLabel()

    # Inner paddings for clean visuals
    window.message_label.setContentsMargins(6, 0, 12, 0)
    window.path_label.setContentsMargins(0, 0, 12, 0)
    window.db_status_label.setContentsMargins(12, 0, 6, 0)
    window.links_count_label.setContentsMargins(6, 0, 6, 0)

    # Left area: dedicated container with message and path, no overlap
    # Create container with status bar as parent to avoid momentary top-level display
    left_container = QWidget(status)
    left_layout = QHBoxLayout(left_container)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(0)
    left_layout.addWidget(window.message_label)
    left_layout.addWidget(window.path_label, 1)
    status.addWidget(left_container, 1)
    # Right area: DB status, links counter
    status.addPermanentWidget(window.db_status_label)
    status.addPermanentWidget(window.links_count_label)

    def _retranslate_status_bar() -> None:
        window.message_label.setText(_tr("Ready"))
        window.path_label.setText(_tr("Path: "))
        window.db_status_label.setText(_tr("Database: connected"))
        window.links_count_label.setText(_arg(_tr("Links: %1"), format_number(0)))
        update_status_bar(window)

    window._retranslate_status_bar = _retranslate_status_bar  # type: ignore[attr-defined]

    service = LanguageService.instance()
    previous_handler = getattr(window, "_status_bar_lang_handler", None)
    if previous_handler is not None:
        try:
            service.languageChanged.disconnect(previous_handler)
        except TypeError:
            logger.debug(
                "StatusBar: previous language handler disconnect failed",
                exc_info=True,
            )

    def _on_language_changed(lang_code: str) -> None:
        logger.debug("StatusBar: language changed -> %s", lang_code)
        _retranslate_status_bar()

    service.languageChanged.connect(_on_language_changed)
    window._status_bar_lang_handler = _on_language_changed  # type: ignore[attr-defined]

    if hasattr(window, "destroyed"):
        # Ensure the connection is removed when the window is destroyed to avoid dangling references
        def _cleanup():
            try:
                logger.debug("StatusBar: disconnecting language handler during cleanup")
                service.languageChanged.disconnect(_on_language_changed)
            except TypeError:
                logger.debug(
                    "StatusBar: language handler already disconnected",
                    exc_info=True,
                )

        window.destroyed.connect(_cleanup)  # type: ignore[arg-type]

    _retranslate_status_bar()

    return status


def _set_text_if_changed(label, text: str) -> None:
    """Safely update label text only if changed."""
    try:
        if label is None:
            return
        current = label.text() if hasattr(label, "text") else None
        if current != text:
            label.setText(text)
    except Exception:
        logger.debug("StatusBar: failed to update label text", exc_info=True)


def _update_counter(window) -> None:
    """Update links/categories counter in status bar."""
    try:
        stack = getattr(window, "stack", None)
        tiles_active = False
        if stack is not None:
            tiles_index = app_config.ui.get_stack_index_tiles()
            try:
                current_index = stack.currentIndex()
            except Exception:
                current_index = None
            tiles_active = current_index == tiles_index

        widgets = getattr(window, "widgets", None)
        tiles_widget = widgets.tiles if widgets else getattr(window, "tiles", None)

        if tiles_active and tiles_widget:
            try:
                cats = int(tiles_widget.get_categories_count())
            except Exception:
                cats = 0
            _set_text_if_changed(
                window.links_count_label,
                _arg(_tr("Categories: %1"), format_number(cats)),
            )
        else:
            links = getattr(window, "links", None)
            if links is not None:
                _set_text_if_changed(
                    window.links_count_label,
                    _arg(_tr("Links: %1"), format_number(links.get_row_count())),
                )
            else:
                _set_text_if_changed(
                    window.links_count_label,
                    _arg(_tr("Links: %1"), format_number(0)),
                )
    except Exception:
        _set_text_if_changed(
            window.links_count_label,
            _arg(_tr("Links: %1"), format_number(0)),
        )


def _update_db_status(window) -> None:
    """Update database connection status in status bar."""
    dc = getattr(window, "database_controller", None)
    db = getattr(dc, "db", None)
    try:
        connected = getattr(db, "is_connected", lambda: False)()
    except Exception:
        logger.debug("StatusBar: database connectivity check failed", exc_info=True)
        connected = False

    if connected:
        _set_text_if_changed(window.db_status_label, _tr("Database: connected"))
    else:
        _set_text_if_changed(window.db_status_label, _tr("Database: disconnected"))


def _build_tree_path(window) -> list[str]:
    """Build path from tree current index."""
    parts: list[str] = []
    tree = getattr(window, "tree", None)
    try:
        if tree is not None:
            idx = tree.currentIndex()
            if idx and idx.isValid():
                cur = idx
                while cur.isValid():
                    text = cur.data()
                    if isinstance(text, str) and text:
                        parts.insert(0, text)
                    cur = cur.parent()
    except Exception:
        logger.debug("StatusBar: building tree path failed", exc_info=True)
        parts = []
    return parts


def _add_sphere_prefix(window, parts: list[str]) -> None:
    """Add active sphere name as prefix to path."""
    try:
        sb = getattr(window, "structure_business", None)
        if sb is not None and getattr(sb, "current_sphere_id", None):
            sphere_data = sb.get_sphere_by_id(sb.current_sphere_id)
            if sphere_data and isinstance(sphere_data.get("name"), str):
                parts.insert(0, sphere_data["name"])
    except Exception:
        logger.debug("StatusBar: failed to append sphere prefix", exc_info=True)


def _add_selected_link(window, parts: list[str]) -> None:
    """Append selected link name from table to path."""
    try:
        table = getattr(window, "table", None)
        if table is not None:
            selection_model = table.selectionModel()
            idx = (
                table.currentIndex()
                if table.currentIndex().isValid()
                else (selection_model.currentIndex() if selection_model else None)
            )
            if idx and idx.isValid():
                name_idx = idx.sibling(idx.row(), 1)
                name_data = name_idx.data() if name_idx.isValid() else None
                if isinstance(name_data, str) and name_data.strip():
                    parts.append(name_data.strip())
    except Exception:
        logger.debug("StatusBar: failed to append selected link", exc_info=True)


def _update_path(window) -> None:
    """Update path label with current hierarchy."""
    parts = _build_tree_path(window)
    _add_sphere_prefix(window, parts)
    _add_selected_link(window, parts)

    if parts:
        _set_text_if_changed(
            window.path_label,
            _tr("Path: ") + " > ".join(parts),
        )
    else:
        if hasattr(window, "path_label") and window.path_label:
            _set_text_if_changed(window.path_label, _tr("Path: "))


def update_status_bar(window) -> None:
    """Update the status bar contents for the given window.

    - Update links counter
    - Update database connection status
    - Build the path of the current structure item and active sphere
    """
    required_labels = (
        "links_count_label",
        "db_status_label",
        "path_label",
    )
    for attr in required_labels:
        label = getattr(window, attr, None)
        if label is None:
            logger.debug("StatusBar: skipping update, missing '%s'", attr)
            return

    try:
        _update_counter(window)
        _update_db_status(window)
        _update_path(window)
    except Exception:
        logger.exception("StatusBar: unexpected error during update")
        if hasattr(window, "path_label") and window.path_label:
            try:
                _set_text_if_changed(window.path_label, _tr("Path: "))
            except Exception:
                logger.debug(
                    "StatusBar: failed to reset path label after error", exc_info=True
                )
