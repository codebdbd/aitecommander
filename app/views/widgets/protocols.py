"""Protocols for views module type safety."""

from pathlib import Path
from typing import Any, Optional, Protocol, TypedDict

from PyQt6.QtCore import QAbstractItemModel, QItemSelectionModel, QModelIndex, Qt
from PyQt6.QtWidgets import QHeaderView, QScrollBar, QWidget


class LinkDict(TypedDict, total=False):
    """Typed dictionary for link data instead of ``Dict[str, Any]``."""

    id: int
    name: str
    url: str
    category_id: int
    type: str
    browser_key: str
    icon_path: str
    position: int
    is_favorite: int
    notes: str


class TreeNodeDict(TypedDict):
    """Typed dictionary for tree node data."""

    type: str  # "section" | "category"
    id: int
    name: str
    icon_path: str
    position: int


class SystemDialogsProtocol(Protocol):
    """Protocol for system dialogs instead of a plain ``object``.

    Used in ``MainWindow`` for type-safe access to the system dialogs controller
    without tight coupling to a particular implementation.
    """

    def show_about_dialog(self) -> None: ...
    def show_settings_dialog(self) -> None: ...
    def show_file_search_dialog(self) -> None: ...
    def handle_import_browser_bookmarks(self) -> None: ...


class LinksBusinessProtocol(Protocol):
    """Protocol for links business layer instead of ``Any``."""

    def get_links(self, category_id: int) -> list[LinkDict]: ...
    def create_link(self, data: LinkDict) -> int: ...
    def update_link(self, link_id: int, data: LinkDict) -> bool: ...
    def delete_link(self, link_id: int) -> bool: ...


class WidgetConfigProtocol(Protocol):
    """Configuration interface for widgets.

    Enables dependency injection and simplifies testing by providing
    a stable contract for configuration access.
    """

    def get_top_panel_button_size(self) -> int:
        """Returns button size for top panels in pixels."""
        ...

    def get_top_panel_icon_size(self) -> tuple[int, int]:
        """Returns (width, height) for top panel icons in pixels."""
        ...

    def get_top_bar_buttons_spacing(self) -> int:
        """Returns spacing between buttons in top bar."""
        ...

    def get_tile_size(self) -> tuple[int, int]:
        """Returns (width, height) for category tiles."""
        ...

    def get_tile_icon_size(self) -> tuple[int, int]:
        """Returns (width, height) for tile icons."""
        ...

    def get_tile_spacing(self) -> int:
        """Returns spacing between tiles."""
        ...

    def get_tile_padding(self) -> int:
        """Returns padding inside tiles."""
        ...

    def get_row_height(self) -> int:
        """Returns row height for tree/table views."""
        ...

    def get_hover_color(self) -> str:
        """Returns hover color as hex string (e.g., '#444444')."""
        ...


class AppConfigWidgetAdapter:
    """Adapter for app_config implementing WidgetConfigProtocol.

    Wraps global app_config with type-safe interface and fallback values.

    Example:
        >>> from app.config_data import app_config
        >>> config = AppConfigWidgetAdapter(app_config)
        >>> button_size = config.get_top_panel_button_size()
    """

    def __init__(self, config):
        """Initialize adapter.

        Args:
            config: Global app_config object
        """
        self._config = config

    def get_top_panel_button_size(self) -> int:
        """Returns button size with fallback to 32."""
        try:
            return int(self._config.ui.get_top_panel_button_size())
        except (AttributeError, TypeError, ValueError):
            return 32

    def get_top_panel_icon_size(self) -> tuple[int, int]:
        """Returns icon size with fallback to (24, 24)."""
        try:
            size = self._config.ui.get_top_panel_icon_size()
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                return (int(size[0]), int(size[1]))
        except (AttributeError, TypeError, ValueError, IndexError):
            pass
        return (24, 24)

    def get_top_bar_buttons_spacing(self) -> int:
        """Returns buttons spacing with fallback to 4."""
        try:
            return int(self._config.ui.get_top_bar_buttons_spacing())
        except (AttributeError, TypeError, ValueError):
            return 4

    def get_tile_size(self) -> tuple[int, int]:
        """Returns tile size with fallback to (120, 100)."""
        try:
            size = self._config.ui.get_tile_size()
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                return (int(size[0]), int(size[1]))
        except (AttributeError, TypeError, ValueError, IndexError):
            pass
        return (120, 100)

    def get_tile_icon_size(self) -> tuple[int, int]:
        """Returns tile icon size with fallback to (48, 48)."""
        try:
            size = self._config.ui.get_tile_icon_size()
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                return (int(size[0]), int(size[1]))
        except (AttributeError, TypeError, ValueError, IndexError):
            pass
        return (48, 48)

    def get_tile_spacing(self) -> int:
        """Returns tile spacing with fallback to 8."""
        try:
            return int(self._config.ui.get_tile_spacing())
        except (AttributeError, TypeError, ValueError):
            return 8

    def get_tile_padding(self) -> int:
        """Returns tile padding with fallback to 8."""
        try:
            return int(self._config.ui.get_tile_padding())
        except (AttributeError, TypeError, ValueError):
            return 8

    def get_row_height(self) -> int:
        """Returns row height with fallback to 24."""
        try:
            return int(self._config.ui.get_row_height())
        except (AttributeError, TypeError, ValueError):
            return 24

    def get_hover_color(self) -> str:
        """Returns hover color with fallback to '#444444'."""
        try:
            color = self._config.ui.get("ui.colors.hover")
            if color and isinstance(color, str):
                return str(color)
        except (AttributeError, KeyError, TypeError):
            pass
        return "#444444"


# ============================================================================
# Protocols for Mixins
# ============================================================================


class TableViewProtocol(Protocol):
    """Protocol defining the interface expected by table view mixins.
    
    This protocol documents methods that mixins expect from QTableView.
    Any class using table view mixins should implement this protocol.
    """
    
    def model(self) -> Optional[QAbstractItemModel]:
        """Return the model attached to this view."""
        ...
    
    def sortByColumn(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sort the view by the given column."""
        ...
    
    def verticalScrollBar(self) -> Optional[QScrollBar]:
        """Return the vertical scroll bar."""
        ...
    
    def viewport(self) -> Optional[QWidget]:
        """Return the viewport widget."""
        ...
    
    def selectionModel(self) -> Optional[QItemSelectionModel]:
        """Return the selection model."""
        ...
    
    def horizontalHeader(self) -> Optional[QHeaderView]:
        """Return the horizontal header."""
        ...
    
    def setCurrentIndex(self, index: QModelIndex) -> None:
        """Set the current index."""
        ...
    
    def scrollTo(self, index: QModelIndex, hint: Any = ...) -> None:
        """Scroll to the given index."""
        ...
    
    def selectRow(self, row: int) -> None:
        """Select the given row."""
        ...


class LinkTableProtocol(TableViewProtocol, Protocol):
    """Protocol for link table views with additional link-specific methods.
    
    Extends TableViewProtocol with methods specific to link management.
    """
    
    def get_link_at(self, row: int) -> Optional[dict[str, Any]]:
        """Get link data at the given row."""
        ...
    
    def validate_cache_integrity(self) -> bool:
        """Validate the integrity of the link cache."""
        ...
    
    def rebuild_cache_from_items(self) -> None:
        """Rebuild the link cache from table items."""
        ...


class IconProviderProtocol(Protocol):
    """Protocol for classes that provide default icon paths.
    
    Used by LinkButtonMixin and similar components.
    """
    
    def _get_default_icon_path(self) -> Path:
        """Return the path to the default icon."""
        ...


class TranslatableProtocol(Protocol):
    """Protocol for classes that support Qt translation.
    
    Used by mixins that need to display translated text.
    """
    
    def tr(self, text: str) -> str:
        """Translate the given text using Qt's translation system."""
        ...
