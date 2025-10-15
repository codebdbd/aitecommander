"""Constants for topbar layout and configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopBarConstants:
    """Centralized constants for top-bar layout management."""

    # Search widget constraints
    MIN_SEARCH_WIDTH: int = 148
    MAX_SEARCH_WIDTH: int = 500
    MIN_SEARCH_WIDTH_ABSOLUTE: int = 148

    # Panel constraints
    MIN_PANEL_WIDTH: int = 50
    MAX_WIDGET_WIDTH: int = 16777215  # Qt maximum

    # Button visibility limits
    MIN_VISIBLE_BUTTONS: int = 0
    MAX_VISIBLE_BUTTONS: int = 20

    # Default configuration values
    DEFAULT_LOG_INFO: bool = False
    DEFAULT_MIN_SEARCH_WIDTH: int = 148
    DEFAULT_MAX_RECENT: int = 10
    DEFAULT_MAX_FAV: int = 10
    DEFAULT_MAX_QUICK: int = 6
    DEFAULT_MIN_RECENT: int = 0
    DEFAULT_MIN_FAV: int = 0
    DEFAULT_MIN_QUICK: int = 0
    DEFAULT_BUTTON_SIZE: int = 32
    DEFAULT_NARROW_THRESHOLD: int = 600

    # Layout spacing and hysteresis
    HYSTERESIS_THRESHOLD_BASE: int = 12
    HYSTERESIS_SPACING_MULTIPLIER: int = 2
    SEPARATOR_SPACING_VISIBLE: int = 4
    SEPARATOR_SPACING_HIDDEN: int = 0

    # Performance thresholds (milliseconds)
    SLOW_ADJUST_THRESHOLD_MS: int = 50
    SLOW_CLAMP_THRESHOLD_MS: int = 20

    # Cache limits
    CACHE_MAX_SIZE: int = 100


# Global instance for easy import
TOPBAR_CONSTANTS = TopBarConstants()
