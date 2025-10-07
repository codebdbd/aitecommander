# app/views/status_bar.py

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

from app.config_data import app_config
from app.views.widgets.language_selector import LanguageSelector
from i18n.language_service import LanguageService
from i18n.locale_utils import format_number


_TR_CONTEXT = "StatusBar"


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

    language_selector = LanguageSelector(status)
    window.language_selector = language_selector

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
    status.addPermanentWidget(language_selector)

    def _retranslate_status_bar() -> None:
        window.message_label.setText(_tr("Ready"))
        window.path_label.setText(_tr("Path: "))
        window.db_status_label.setText(_tr("Database: connected"))
        window.links_count_label.setText(_arg(_tr("Links: %1"), format_number(0)))
        language_selector.setToolTip(_tr("Switch application language"))
        language_selector.setAccessibleName(_tr("Language Selector"))
        update_status_bar(window)

    window._retranslate_status_bar = _retranslate_status_bar  # type: ignore[attr-defined]

    service = LanguageService.instance()
    service.languageChanged.connect(lambda _code: _retranslate_status_bar())

    if hasattr(window, "destroyed"):
        # Ensure the connection is removed when the window is destroyed to avoid dangling references
        def _cleanup():
            try:
                service.languageChanged.disconnect(_retranslate_status_bar)
            except Exception:
                pass

        window.destroyed.connect(_cleanup)  # type: ignore[arg-type]

    _retranslate_status_bar()

    return status


def update_status_bar(window) -> None:
    """Update the status bar contents for the given window.

    - Update links counter
    - Update database connection status
    - Build the path of the current structure item and active sphere
    """
    try:
        def _set_text_if_changed(label, text: str) -> None:
            try:
                if label is None:
                    return
                current = label.text() if hasattr(label, "text") else None
                if current != text:
                    label.setText(text)
            except Exception:
                # Never crash the UI due to status bar issues
                pass

        # Counter: if category tiles mode is active — show number of categories,
        # otherwise show number of links in the table
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
            if tiles_active and hasattr(window, "tiles") and window.tiles:
                try:
                    cats = int(window.tiles.get_categories_count())
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
            # On unexpected errors — do not crash UI and show 0
            _set_text_if_changed(
                window.links_count_label,
                _arg(_tr("Links: %1"), format_number(0)),
            )

        # DB status (via DatabaseController)
        dc = getattr(window, "database_controller", None)
        db = getattr(dc, "db", None)
        if db is not None and getattr(db, "is_connected", lambda: False)():
            _set_text_if_changed(window.db_status_label, _tr("Database: connected"))
        else:
            _set_text_if_changed(window.db_status_label, _tr("Database: disconnected"))

        # Path in tree + active sphere (QTreeView-only)
        parts = []
        tree = getattr(window, "tree", None)
        try:
            if tree is not None:
                # Use currentIndex and walk through parents
                idx = tree.currentIndex()
                if idx and idx.isValid():
                    cur = idx
                    while cur.isValid():
                        text = cur.data()
                        if isinstance(text, str) and text:
                            parts.insert(0, text)
                        cur = cur.parent()
        except Exception:
            # Ignore failures while building path
            parts = []

        # Prefix: active sphere
        try:
            sb = getattr(window, "structure_business", None)
            if sb is not None and getattr(sb, "current_sphere_id", None):
                sphere_data = sb.get_sphere_by_id(sb.current_sphere_id)
                if sphere_data and isinstance(sphere_data.get("name"), str):
                    parts.insert(0, sphere_data["name"])
        except Exception:
            pass

        # Append selected link name from the table (column 1 — name), if any selection
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
            pass

        if parts:
            _set_text_if_changed(
                window.path_label,
                _tr("Path: ") + " > ".join(parts),
            )
        else:
            if hasattr(window, "path_label") and window.path_label:
                _set_text_if_changed(window.path_label, _tr("Path: "))
    except Exception:
        # In case of unexpected errors do not crash UI, just clear path
        if hasattr(window, "path_label") and window.path_label:
            try:
                _set_text_if_changed(window.path_label, _tr("Path: "))
            except Exception:
                pass
