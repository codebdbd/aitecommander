"""Constants for topbar layout and configuration."""

from __future__ import annotations

from dataclasses import dataclass

from app.config_data.runtime_config import runtime_app_config as app_config


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
    
    # Favorites panel thresholds
    FAVORITES_MIN_VISIBLE_THRESHOLD: int = 5
    
    # Layout spacing fallbacks
    LAYOUT_SPACING_FALLBACK: int = 6

    # Performance thresholds (milliseconds)
    SLOW_ADJUST_THRESHOLD_MS: int = 50
    SLOW_CLAMP_THRESHOLD_MS: int = 20

    # Cache limits
    CACHE_MAX_SIZE: int = 100


def _build_topbar_constants() -> TopBarConstants:
    ui = app_config.ui
    return TopBarConstants(
        MIN_SEARCH_WIDTH=ui.get_top_panel_search_min_width(),
        MAX_SEARCH_WIDTH=ui.get_topbar_max_search_width(),
        MIN_SEARCH_WIDTH_ABSOLUTE=ui.get_topbar_min_search_width_absolute(),
        MIN_PANEL_WIDTH=ui.get_topbar_min_panel_width(),
        MAX_WIDGET_WIDTH=ui.get_topbar_max_widget_width(),
        MAX_VISIBLE_BUTTONS=ui.get_topbar_max_visible_buttons(),
        DEFAULT_LOG_INFO=ui.get_topbar_log_info(),
        DEFAULT_MIN_SEARCH_WIDTH=ui.get_top_panel_search_min_width(),
        DEFAULT_MAX_RECENT=ui.get_topbar_max_visible_recent(),
        DEFAULT_MAX_FAV=ui.get_topbar_max_visible_fav(),
        DEFAULT_MAX_QUICK=ui.get_topbar_max_visible_quick(),
        DEFAULT_MIN_RECENT=ui.get_topbar_min_visible_recent(),
        DEFAULT_MIN_FAV=ui.get_topbar_min_visible_fav(),
        DEFAULT_MIN_QUICK=ui.get_topbar_min_visible_quick(),
        DEFAULT_BUTTON_SIZE=ui.get_topbar_button_size(),
        DEFAULT_NARROW_THRESHOLD=ui.get_topbar_narrow_threshold(),
        SEPARATOR_SPACING_VISIBLE=ui.get_topbar_separator_search_spacing(),
        SEPARATOR_SPACING_HIDDEN=ui.get_topbar_separator_hidden_spacing(),
        LAYOUT_SPACING_FALLBACK=ui.get_topbar_layout_spacing_fallback(),
    )


# Global instance for easy import
TOPBAR_CONSTANTS = _build_topbar_constants()
