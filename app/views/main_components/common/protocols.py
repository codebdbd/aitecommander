"""Protocols that provide strict typing for the main-window components.

Improvement note: strict Protocol definitions replace ``Any`` usage and improve
static analysis, resulting in safer and more maintainable code.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, runtime_checkable, TYPE_CHECKING

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

if TYPE_CHECKING:
    pass
from PyQt6.QtWidgets import (
    QButtonGroup,
    QLineEdit,
    QStackedLayout,
    QWidget,
)


@runtime_checkable
class SettingsProtocol(Protocol):
    """Protocol describing the application settings object."""

    def get_font_size(self) -> int:
        """Return the font size stored in the settings."""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by key."""
        ...


@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol describing the database abstraction."""

    def is_ready(self) -> bool:
        """Check whether the database is ready."""
        ...

    def execute(self, query: str, params: tuple = ()) -> Any:
        """Execute an SQL query."""
        ...


@runtime_checkable
class ThemeControllerProtocol(Protocol):
    """Protocol describing the theme controller."""

    def apply_theme(self, theme_name: str) -> None:
        """Apply the selected theme to the application."""
        ...

    def get_current_theme(self) -> str:
        """Return the name of the currently active theme."""
        ...

    def _log_tables_header_font(self, window: QWidget) -> None:
        """Log table-header font information for diagnostics."""
        ...


@runtime_checkable
class MainWindowProtocol(Protocol):
    """Protocol describing the application main window.

    Improvement note: replaces ``MainWindowLike`` and ``Any`` with strict typing
    and enumerates all required attributes and methods.
    """

    # Signals
    shown: pyqtSignal

    # Settings and controllers
    settings: SettingsProtocol
    theme_ctrl: ThemeControllerProtocol

    # UI components — top bar
    top_bar_host: Optional[QWidget]
    content_container: Optional[QWidget]
    quick_add_widget: Optional[QWidget]
    fav_widget: Optional[QWidget]
    recent_links_widget: Optional[QWidget]
    search: Optional[QLineEdit]

    # UI components — main area
    left_panel: Optional[QWidget]
    tree: Optional[QWidget]
    tree_model: Optional[QObject]
    splitter: Optional[QWidget]
    stack: Optional[QStackedLayout]
    tiles: Optional[QWidget]
    tiles_scroll: Optional[QWidget]
    table: Optional[QWidget]
    table_container: Optional[QWidget]

    # UI components — bottom bar
    spheres_bar: Optional[QWidget]
    sphere_group: Optional[QButtonGroup]
    sphere_buttons: dict[int, QWidget]
    bottom_bar_container: Optional[QWidget]
    switch_sphere_button: Optional[QWidget]

    # State
    current_category_id: Optional[int]
    current_sphere_id: Optional[int]
    thread_pool: Optional[QThreadPool]  # Improvement: explicit type instead of Any
    undo_stack: Optional[Any]  # UndoManager reference; avoid cyclic import

    # Internal flags
    _first_structure_load: bool
    _topbar_manager: Optional[Any]  # TopBarLayoutManager reference; avoid cyclic import
    _topbar_initialized: bool
    _auto_hide_tree_filter: Optional[Any]  # `_AutoHideTreeFilter` (private helper)

    # QMainWindow methods
    def show(self) -> None:
        """Show the window."""
        ...

    def close(self) -> bool:
        """Close the window."""
        ...

    def isVisible(self) -> bool:
        """Return whether the window is visible."""
        ...

    def isEnabled(self) -> bool:
        """Return whether the window is enabled."""
        ...

    def width(self) -> int:
        """Return the window width."""
        ...

    def height(self) -> int:
        """Return the window height."""
        ...

    def setUpdatesEnabled(self, enable: bool) -> None:
        """Enable or disable widget updates."""
        ...

    def centralWidget(self) -> Optional[QWidget]:
        """Return the central widget."""
        ...

    def setCentralWidget(self, widget: QWidget) -> None:
        """Assign the central widget."""
        ...

    def setMenuBar(self, menubar: QWidget) -> None:
        """Install the menu bar."""
        ...

    def installEventFilter(self, filter_obj: QObject) -> None:
        """Install an event filter."""
        ...

    def removeEventFilter(self, filter_obj: QObject) -> None:
        """Remove a previously installed event filter."""
        ...

    # Application-specific methods
    def apply_font_size_to_content(self, size: int) -> None:
        """Apply the font size to content widgets."""
        ...

    def on_search(self, text: str) -> None:
        """Handle search text changes."""
        ...


@runtime_checkable
class UIStateManagerProtocol(Protocol):
    """Protocol describing the UI state manager."""

    def load_category(self, category_id: int, source: str = "") -> None:
        """Load a category."""
        ...

    def get_current_category(self) -> Optional[int]:
        """Return the current category ID."""
        ...


@runtime_checkable
class StructureBusinessProtocol(Protocol):
    """Protocol describing the structure business logic layer."""

    current_sphere_id: Optional[int]
    structure_loaded: pyqtSignal
    async_operations: Optional[Any]

    def load_structure_async(self, sphere_id: int) -> None:
        """Load the structure for a sphere asynchronously."""
        ...


@runtime_checkable
class TopPanelsControllerProtocol(Protocol):
    """Protocol describing the top-panel controller."""

    data_loaded: pyqtSignal

    def refresh_all(self) -> None:
        """Refresh all panels."""
        ...


class ResourceManagerProtocol(Protocol):
    """Protocol describing a resource manager with centralized cleanup.

    Improvement note: adds a dedicated Protocol for resource lifecycle control.
    """

    def register_resource(self, resource: Any, cleanup_func: Callable[[], None]) -> None:
        """Register a resource for automatic cleanup."""
        ...

    def cleanup_all(self) -> None:
        """Clean up the registered resources."""
        ...

    def is_cleaned_up(self) -> bool:
        """Return whether cleanup has already occurred."""
        ...
