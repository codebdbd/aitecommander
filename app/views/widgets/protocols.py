"""Protocols for views module type safety."""

from typing import Protocol, TypedDict


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
