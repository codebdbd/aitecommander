"""Configuration protocols for widgets.

Provides type-safe configuration interfaces for dependency injection,
eliminating hard dependencies on global app_config.
"""

from typing import Protocol, Tuple


class WidgetConfigProtocol(Protocol):
    """Configuration interface for widgets.
    
    Enables dependency injection and simplifies testing by providing
    a stable contract for configuration access.
    """
    
    def get_top_panel_button_size(self) -> int:
        """Returns button size for top panels in pixels."""
        ...
    
    def get_top_panel_icon_size(self) -> Tuple[int, int]:
        """Returns (width, height) for top panel icons in pixels."""
        ...
    
    def get_top_bar_buttons_spacing(self) -> int:
        """Returns spacing between buttons in top bar."""
        ...
    
    def get_tile_size(self) -> Tuple[int, int]:
        """Returns (width, height) for category tiles."""
        ...
    
    def get_tile_icon_size(self) -> Tuple[int, int]:
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
    
    def get_top_panel_icon_size(self) -> Tuple[int, int]:
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
    
    def get_tile_size(self) -> Tuple[int, int]:
        """Returns tile size with fallback to (120, 100)."""
        try:
            size = self._config.ui.get_tile_size()
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                return (int(size[0]), int(size[1]))
        except (AttributeError, TypeError, ValueError, IndexError):
            pass
        return (120, 100)
    
    def get_tile_icon_size(self) -> Tuple[int, int]:
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
