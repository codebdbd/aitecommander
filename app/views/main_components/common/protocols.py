"""Protocols that provide strict typing for the main-window components.

Improvement note: strict Protocol definitions replace ``Any`` usage and improve
static analysis, resulting in safer and more maintainable code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

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
    top_bar_host: QWidget | None
    content_container: QWidget | None
    quick_add_widget: QWidget | None
    fav_widget: QWidget | None
    recent_links_widget: QWidget | None
    search: QLineEdit | None

    # UI components — main area
    left_panel: QWidget | None
    tree: QWidget | None
    tree_model: QObject | None
    splitter: QWidget | None
    stack: QStackedLayout | None
    tiles: QWidget | None
    tiles_scroll: QWidget | None
    table: QWidget | None
    table_container: QWidget | None

    # UI components — bottom bar
    spheres_bar: QWidget | None
    sphere_group: QButtonGroup | None
    sphere_buttons: dict[int, QWidget]
    bottom_bar_container: QWidget | None
    switch_sphere_button: QWidget | None

    # State
    current_category_id: int | None
    current_sphere_id: int | None
    thread_pool: QThreadPool | None  # Improvement: explicit type instead of Any
    undo_stack: Any | None  # UndoManager reference; avoid cyclic import

    # Internal flags
    _first_structure_load: bool
    _topbar_manager: Any | None  # TopBarLayoutManager reference; avoid cyclic import
    _topbar_initialized: bool
    _auto_hide_tree_filter: Any | None  # `_AutoHideTreeFilter` (private helper)

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

    def setUpdatesEnabled(self, _enable: bool) -> None:
        """Enable or disable widget updates."""
        ...

    def centralWidget(self) -> QWidget | None:
        """Return the central widget."""
        ...

    def setCentralWidget(self, widget: QWidget) -> None:
        """Assign the central widget."""
        ...

    def setMenuBar(self, _menubar: QWidget) -> None:
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

    def get_current_category(self) -> int | None:
        """Return the current category ID."""
        ...


@runtime_checkable
class StructureBusinessProtocol(Protocol):
    """Protocol describing the structure business logic layer."""

    current_sphere_id: int | None
    structure_loaded: pyqtSignal
    async_operations: Any | None

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
