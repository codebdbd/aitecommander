"""Protocol that defines configuration for top-bar components.

This module provides a protocol-based abstraction for dependency injection,
simplifying testing and decoupling from global configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class TopBarConfigProtocol(Protocol):
    """Protocol that describes the configuration interface for the top bar.

    Used for dependency injection so tests can easily swap configurations and
    components remain isolated from global state.

    Example:
        >>> class MockConfig:
        ...     def get_button_size(self) -> int:
        ...         return 32
        >>>
        >>> manager = TopBarLayoutManager(window, MockConfig())
    """

    def get_button_size(self) -> int:
        """Return the button size in pixels.

        Returns:
            Button size (typically 32 or 24).
        """
        ...

    def get_search_min_width(self) -> int:
        """Return the minimal search-field width in pixels.

        Returns:
            Minimum width (typically 148).
        """
        ...

    def get_search_height(self) -> int:
        """Return the search-field height in pixels.

        Returns:
            Height in pixels (typically 32).
        """
        ...

    def get_top_bar_height(self) -> int:
        """Return the top-bar height in pixels.

        Returns:
            Height in pixels (typically 40).
        """
        ...

    def get_side_spacing(self) -> int:
        """Return side spacing for widgets in pixels.

        Returns:
            Spacing in pixels (typically 8).
        """
        ...

    def get_throttle_ms(self) -> int:
        """Return the throttling interval for resize events.

        Returns:
            Interval in milliseconds (typically 32).
        """
        ...

    def get_log_info(self) -> bool:
        """Return the flag controlling INFO-level logging.

        Returns:
            ``True`` when INFO messages should be logged.
        """
        ...

    def get_min_visible(self, panel: str) -> int:
        """Return the minimum number of visible buttons for a panel.

        Args:
            panel: Panel name (``"recent"``/``"fav"``/``"quick"``).

        Returns:
            Minimum number of visible buttons (typically 0).
        """
        ...
    def get_max_visible(self, panel: str) -> int:
        """Return the maximum number of visible buttons for the given panel."""
        ...

    def get_favorites_min_visible_threshold(self) -> int:
        """Return the minimum number of visible favorites buttons before hiding.

        Returns:
            Threshold value (typically 5).
        """
        ...

    def get_separator_search_spacing(self) -> int:
        """Return the spacing around separators when search widget is present.

        Returns:
            Spacing in pixels (typically 4).
        """
        ...

    def get_separator_hidden_spacing(self) -> int:
        """Return the spacing around separators when hidden.

        Returns:
            Spacing in pixels (typically 0).
        """
        ...

    def get_layout_spacing_fallback(self) -> int:
        """Return the fallback spacing value when layout spacing is unavailable.

        Returns:
            Spacing in pixels (typically 6).
        """
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """Generic configuration accessor.

        Args:
            default: Fallback value when the key is missing.

        Returns:
            Requested configuration value or ``default``.
        """
        ...

class AppConfigAdapter(TopBarConfigProtocol):
    """Adapter over ``app_config`` that implements ``TopBarConfigProtocol``.

    This adapter wraps the global ``app_config`` so it matches the protocol and 
    can be used through a single DI-friendly interface.

    Example:
        >>> from app.config_data.runtime_config import runtime_app_config as app_config
        >>> config = AppConfigAdapter(app_config)
        >>> manager = TopBarLayoutManager(window, config)
    """

    def __init__(self, app_config: Any):
        """Initialize the adapter.

        Args:
            app_config: Global application configuration object.
        """
        self._config = app_config
        self._warned_deprecated: set[str] = set()

    def _get_with_fallback(
        self,
        primary_key: str,
        fallback_key: str,
        default: Any,
    ) -> Any:
        missing = object()
        try:
            primary = self._config.get(primary_key, missing)
        except (KeyError, AttributeError):
            primary = missing
        if primary is not missing:
            return primary

        try:
            fallback = self._config.get(fallback_key, missing)
        except (KeyError, AttributeError):
            fallback = missing

        if fallback is not missing:
            if fallback_key not in self._warned_deprecated:
                logger.warning(
                    "TopBarConfig: deprecated key '%s' in use; migrate to '%s'",
                    fallback_key,
                    primary_key,
                )
                self._warned_deprecated.add(fallback_key)
            return fallback

        return default

    def get_button_size(self) -> int:
        """Return the button size pulled from configuration."""
        try:
            return int(self._config.ui.get_top_panel_button_size())
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_topbar_button_size())

    def get_search_min_width(self) -> int:
        """Return the minimal search width pulled from configuration."""
        try:
            return int(self._config.ui.get_top_panel_search_min_width())
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_top_panel_search_min_width())

    def get_search_height(self) -> int:
        """Return the search height pulled from configuration."""
        try:
            return int(self._config.ui.get_top_panel_search_height())
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_top_panel_search_height())

    def get_top_bar_height(self) -> int:
        """Return the top-bar height pulled from configuration."""
        try:
            return int(self._config.ui.get_top_bar_height())
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_top_bar_height())

    def get_side_spacing(self) -> int:
        """Return the side spacing pulled from configuration."""
        try:
            return int(self._config.ui.get_top_bar_widgets_side_spacing())
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_top_bar_widgets_side_spacing())

    def get_throttle_ms(self) -> int:
        """Return the throttling interval pulled from configuration."""
        try:
            return int(
                self._get_with_fallback(
                    "ui.topbar.throttle_ms",
                    "topbar.throttle_ms",
                    self._config.ui.get_topbar_throttle_ms(),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_topbar_throttle_ms())

    def get_log_info(self) -> bool:
        """Return the logging flag pulled from configuration."""
        try:
            return bool(
                self._get_with_fallback(
                    "ui.topbar.log_info",
                    "topbar.log_info",
                    self._config.ui.get_topbar_log_info(),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return bool(self._config.ui.get_topbar_log_info())

    def get_min_visible(self, panel: str) -> int:
        """Return the minimum number of visible buttons."""
        try:
            mv = self._get_with_fallback(
                "ui.topbar.min_visible", "topbar.min_visible", {}
            ) or {}
            fallback = {
                "recent": self._config.ui.get_topbar_min_visible_recent(),
                "fav": self._config.ui.get_topbar_min_visible_fav(),
                "quick": self._config.ui.get_topbar_min_visible_quick(),
            }.get(panel, 0)
            return int(mv.get(panel, fallback))
        except (KeyError, ValueError, TypeError, AttributeError):
            return 0

    def get_max_visible(self, panel: str) -> int:
        """Return the maximum number of visible buttons."""
        default = {
            "recent": self._config.ui.get_topbar_max_visible_recent(),
            "fav": self._config.ui.get_topbar_max_visible_fav(),
            "quick": self._config.ui.get_topbar_max_visible_quick(),
        }.get(panel, 10)
        try:
            mv = self._get_with_fallback(
                "ui.topbar.max_visible", "topbar.max_visible", {}
            ) or {}
            return int(mv.get(panel, default))
        except (KeyError, ValueError, TypeError, AttributeError):
            return default

    def get(self, key: str, default: Any = None) -> Any:
        """Generic accessor that mirrors ``dict.get`` semantics."""
        try:
            return self._config.get(key, default)
        except (KeyError, AttributeError):
            return default

    def get_favorites_min_visible_threshold(self) -> int:
        """Return the minimum number of visible favorites buttons before hiding."""
        try:
            return int(
                self._get_with_fallback(
                    "ui.topbar.favorites_min_visible_threshold",
                    "topbar.favorites_min_visible_threshold",
                    self._config.ui.get_topbar_favorites_min_visible_threshold(),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_topbar_favorites_min_visible_threshold())

    def get_separator_search_spacing(self) -> int:
        """Return the spacing around separators when search widget is present."""
        try:
            return int(
                self._get_with_fallback(
                    "ui.topbar.separator_search_spacing",
                    "topbar.separator_search_spacing",
                    self._config.ui.get_topbar_separator_search_spacing(),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_topbar_separator_search_spacing())

    def get_separator_hidden_spacing(self) -> int:
        """Return the spacing around separators when hidden."""
        try:
            return int(
                self._get_with_fallback(
                    "ui.topbar.separator_hidden_spacing",
                    "topbar.separator_hidden_spacing",
                    self._config.ui.get_topbar_separator_hidden_spacing(),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_topbar_separator_hidden_spacing())

    def get_layout_spacing_fallback(self) -> int:
        """Return the fallback spacing value when layout spacing is unavailable."""
        try:
            return int(
                self._get_with_fallback(
                    "ui.topbar.layout_spacing_fallback",
                    "topbar.layout_spacing_fallback",
                    self._config.ui.get_topbar_layout_spacing_fallback(),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return int(self._config.ui.get_topbar_layout_spacing_fallback())

class MockTopBarConfig:
    """Mock configuration used in tests.

    Lightweight protocol implementation for unit tests without external
    dependencies.

    Example:
        >>> config = MockTopBarConfig(button_size=24, search_min_width=100)
        >>> manager = TopBarLayoutManager(window, config)
    """

    def __init__(
        self,
        button_size: int = 32,
        search_min_width: int = 148,
        search_height: int = 32,
        top_bar_height: int = 40,
        side_spacing: int = 8,
        throttle_ms: int = 32,
        log_info: bool = False,
        min_visible_recent: int = 0,
        min_visible_fav: int = 0,
        min_visible_quick: int = 0,
    ):
        """Initialize the mock configuration with explicit values."""
        self._button_size = button_size
        self._search_min_width = search_min_width
        self._search_height = search_height
        self._top_bar_height = top_bar_height
        self._side_spacing = side_spacing
        self._throttle_ms = throttle_ms
        self._log_info = log_info
        self._min_visible: dict[str, int] = {
            "recent": min_visible_recent,
            "fav": min_visible_fav,
            "quick": min_visible_quick,
        }
        self._custom_values: dict[str, int] = {}

    def get_button_size(self) -> int:
        return self._button_size

    def get_search_min_width(self) -> int:
        return self._search_min_width

    def get_search_height(self) -> int:
        return self._search_height

    def get_top_bar_height(self) -> int:
        return self._top_bar_height

    def get_side_spacing(self) -> int:
        return self._side_spacing

    def get_throttle_ms(self) -> int:
        return self._throttle_ms

    def get_log_info(self) -> bool:
        return self._log_info

    def get_min_visible(self, panel: str) -> int:
        return self._min_visible.get(panel, 0)

    def get(self, key: str, default: Any = None) -> Any:
        return self._custom_values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Override a custom value for tests."""
        self._custom_values[key] = value

    def get_favorites_min_visible_threshold(self) -> int:
        """Return the minimum number of visible favorites buttons before hiding."""
        return self._custom_values.get("favorites_min_visible_threshold", 5)

    def get_separator_search_spacing(self) -> int:
        """Return the spacing around separators when search widget is present."""
        return self._custom_values.get("separator_search_spacing", 4)

    def get_separator_hidden_spacing(self) -> int:
        """Return the spacing around separators when hidden."""
        return self._custom_values.get("separator_hidden_spacing", 0)

    def get_layout_spacing_fallback(self) -> int:
        """Return the fallback spacing value when layout spacing is unavailable."""
        return self._custom_values.get("layout_spacing_fallback", 6)
