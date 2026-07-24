"""Protocols for views module type safety."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any, Optional, Protocol, TypedDict

from PyQt6.QtCore import QAbstractItemModel, QItemSelectionModel, QModelIndex, Qt
from PyQt6.QtWidgets import QHeaderView, QScrollBar, QWidget

from app.interfaces import SupportsUpdates


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


class UpdateStatus(Enum):
    """Status of panel update operation."""

    IDLE = "idle"
    UPDATING = "updating"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class UpdatablePanelProtocol(Protocol):
    """Unified interface for panels that support explicit update lifecycle."""

    def update_data(
        self,
        data: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> bool:
        """Schedule/update panel data and return success state."""
        ...

    def get_update_status(self) -> UpdateStatus:
        """Return current update status."""
        ...

    def cancel_update(self) -> bool:
        """Cancel current update flow if active."""
        ...

    def clear_data(self) -> None:
        """Clear current panel data."""
        ...

    def refresh(self) -> bool:
        """Request external refresh and return scheduling state."""
        ...


@dataclass(slots=True)
class BatchUpdateConfig:
    """Configuration for batched panel updates."""

    enabled: bool = True
    batch_size: int = 10
    interval_ms: int = 16
    max_concurrent: int = 1

    def __post_init__(self) -> None:
        self.batch_size = max(1, int(self.batch_size))
        self.interval_ms = max(1, int(self.interval_ms))
        self.max_concurrent = max(1, int(self.max_concurrent))


@dataclass(slots=True)
class UpdateContext:
    """Runtime context for panel updates."""

    start_time: float = field(default_factory=time)
    data_version: float = field(default_factory=time)
    batch_count: int = 0
    item_count: int = 0
    error_count: int = 0
    is_cancelled: bool = False


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
    def clear_favorites_async(self) -> None: ...


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
        >>> from app.config_data.runtime_config import runtime_app_config as app_config
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

    def sortByColumn(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
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

    def blockSignals(self, _block: bool) -> None:
        """Enable or disable signal emission."""
        ...

    def setCurrentIndex(self, index: QModelIndex) -> None:
        """Set the current index."""
        ...

    def scrollTo(self, index: QModelIndex) -> None:
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


class TranslatableProtocol(Protocol):
    """Protocol for classes that support Qt translation.

    Used by mixins that need to display translated text.
    """

    def tr(self, text: str) -> str:
        """Translate the given text using Qt's translation system."""
        ...


class LinkTableWidgetProtocol(LinkTableProtocol, SupportsUpdates, Protocol):
    """Protocol for link table widgets that also support suspend_updates."""


class SelectionModelProtocol(Protocol):
    """Protocol for Qt selection models used in structure tree workflows."""

    SelectionFlag: type[QItemSelectionModel.SelectionFlag]

    def hasSelection(self) -> bool: ...

    def setCurrentIndex(
        self,
        index: QModelIndex,
        command: QItemSelectionModel.SelectionFlag,
    ) -> None: ...


class StructureTreeModelProtocol(Protocol):
    """Protocol describing the structure tree model interface."""

    def rowCount(self) -> int: ...

    def index(self, row: int, column: int) -> QModelIndex: ...

    def index_for(self, item_type: str, item_id: int) -> QModelIndex | None: ...


class StructureTreeViewProtocol(Protocol):
    """Protocol for the tree widget used by selection workflows."""

    def model(self) -> StructureTreeModelProtocol | None: ...

    def selectionModel(self) -> SelectionModelProtocol | None: ...

    def blockSignals(self, _block: bool) -> None: ...

    def scrollTo(self, index: QModelIndex) -> None: ...


class StructureActionsProtocol(Protocol):
    """Protocol describing actions invoked during selection workflows."""

    def focus_tree(self) -> None: ...

    def clear_table_selection(self) -> None: ...

    def refresh_tiles(self, section_id: int) -> None: ...

    def load_category_via_ui_state(self, category_id: int, *, source: str) -> None: ...
