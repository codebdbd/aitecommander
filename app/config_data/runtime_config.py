"""Narrow runtime accessors for frequently used app configuration values.

This module helps reduce direct imports of the hub re-export
``app.config_data`` from UI/system controllers.
"""

from __future__ import annotations

from app.config_data import app_config

runtime_app_config = app_config


def get_runtime_app_config():
    """Return the shared app config proxy for cases where full config is required."""
    return app_config


def get_table_stack_index() -> int:
    return int(app_config.ui.get_stack_index_table())


def get_tiles_stack_index() -> int:
    return int(app_config.ui.get_stack_index_tiles())


def is_fast_tiles_from_cache_enabled(default: bool = True) -> bool:
    return bool(app_config.ui.get("ui.fast_tiles_from_cache", default))


def get_shutdown_default_timeout(default: int = 2000) -> int:
    return int(app_config.get("shutdown.default_timeout", default))


def get_shutdown_max_total_time(default: int = 10000) -> int:
    return int(app_config.get("shutdown.max_total_time", default))


def is_shutdown_parallel_execution(default: bool = False) -> bool:
    return bool(app_config.get("shutdown.parallel_execution", default))


def get_thread_pool_shutdown_timeout() -> int:
    return int(app_config.ui.get_thread_pool_shutdown_timeout())


def get_favorites_panel_limit(default: int = 16) -> int:
    return int(app_config.ui.get("ui.favorites_panel_limit", default))


def get_ui_config():
    return app_config.ui


def get_tree_icon_size() -> tuple[int, int]:
    w, h = app_config.ui.get_tree_icon_size()
    return int(w), int(h)


def is_tree_alphabetical_sort_enabled(default: bool = False) -> bool:
    return bool(app_config.ui.get("ui.tree_alphabetical_sort_enabled", default))


def is_tree_skip_sort_if_sorted(default: bool = True) -> bool:
    return bool(app_config.ui.get("ui.tree_skip_sort_if_sorted", default))


def get_selection_restore_delay_ms(default: int = 0) -> int:
    raw = app_config.ui.get("ui.selection_restore_delay_ms", default)
    try:
        delay_ms = int(raw)
    except (TypeError, ValueError):
        return int(default)
    if delay_ms < 0:
        return int(default)
    return delay_ms


def get_table_selection_restore_delay_ms(default: int = 100) -> int:
    # Defensive clamp: this delay is used for post-save focus restore in UI.
    # Too large values (e.g. seconds written as milliseconds) look like a freeze.
    raw = app_config.ui.get("ui.table_selection_restore_delay", default)
    try:
        delay_ms = int(raw)
    except (TypeError, ValueError):
        return int(default)
    if delay_ms < 0:
        return int(default)
    if delay_ms > 5000:
        return int(default)
    return delay_ms


def get_tree_quiet_first_selection(default: bool = True) -> bool:
    if hasattr(app_config.ui, "get_tree_quiet_first_selection"):
        return bool(app_config.ui.get_tree_quiet_first_selection())
    return bool(app_config.ui.get("ui.tree_quiet_first_selection", default))


def is_tree_snapshot_suspend_updates(default: bool = True) -> bool:
    return bool(app_config.ui.get("ui.tree_snapshot_suspend_updates", default))


def get_tree_sections_first_render(default: bool = True) -> bool:
    if hasattr(app_config.ui, "get_tree_sections_first_render"):
        return bool(app_config.ui.get_tree_sections_first_render())
    return bool(app_config.ui.get("ui.tree_sections_first_render", default))


def get_tree_section_icon_prewarm_limit(default: int = 6) -> int:
    if hasattr(app_config.ui, "get_tree_section_icon_prewarm_limit"):
        return int(app_config.ui.get_tree_section_icon_prewarm_limit())
    return int(app_config.ui.get("ui.tree_section_icon_prewarm_limit", default))


def is_tree_snapshot_icon_warmup(default: bool = False) -> bool:
    return bool(app_config.ui.get("ui.tree_snapshot_icon_warmup", default))


def get_sphere_button_icon_size() -> tuple[int, int]:
    size = app_config.get_sphere_button_icon_size()
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        return int(size[0]), int(size[1])
    if isinstance(size, int):
        return int(size), int(size)
    return 24, 24


def is_dialogs_enable_details() -> bool:
    return bool(app_config.ui.get_dialogs_enable_details())


def get_dialog_message_box_max_width() -> int:
    return int(app_config.ui.get_dialog_message_box_max_width())


def is_debug_links_inline_update() -> bool:
    return bool(app_config.ui.get_debug_links_inline_update())


def is_drop_stale_structure_snapshots(default: bool = False) -> bool:
    if hasattr(app_config.ui, "get_drop_stale_structure_snapshots"):
        return bool(app_config.ui.get_drop_stale_structure_snapshots())
    return bool(app_config.ui.get("ui.drop_stale_structure_snapshots", default))


def get_structure_reload_delay_ms(default: int = 150) -> int:
    if hasattr(app_config.ui, "get_structure_reload_delay_ms"):
        return int(app_config.ui.get_structure_reload_delay_ms())
    return int(app_config.ui.get("ui.structure_reload_delay_ms", default))


def get_structure_reload_immediate_delay_ms(default: int = 50) -> int:
    if hasattr(app_config.ui, "get_structure_reload_immediate_delay_ms"):
        return int(app_config.ui.get_structure_reload_immediate_delay_ms())
    return int(app_config.ui.get("ui.structure_reload_immediate_delay_ms", default))


def get_slow_update_positions_threshold_sec(default: float = 1.0) -> float:
    value = app_config.get("limits.slow_update_positions_threshold_sec", default)
    return float(value) if isinstance(value, (int, float)) else float(default)
