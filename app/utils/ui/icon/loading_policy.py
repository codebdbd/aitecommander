from __future__ import annotations

from dataclasses import dataclass

from app.config_data.runtime_config import (
    get_tree_section_icon_prewarm_limit,
    get_tree_sections_first_render,
    get_runtime_app_config,
)


@dataclass(frozen=True)
class TreeIconLoadingPolicy:
    sections_first_render: bool
    section_sync_limit: int
    defer_category_loads: bool


@dataclass(frozen=True)
class TilesIconLoadingPolicy:
    lazy: bool
    sync_prefetch_count: int
    batch_size: int


def get_tree_icon_loading_policy(*, snapshot_mode: str) -> TreeIconLoadingPolicy:
    try:
        sections_first = bool(get_tree_sections_first_render(True))
    except Exception:
        sections_first = True

    try:
        section_limit = max(0, int(get_tree_section_icon_prewarm_limit(6)))
    except Exception:
        section_limit = 6

    mode = str(snapshot_mode or "fast_switch").strip().lower()
    if mode == "full_restore":
        return TreeIconLoadingPolicy(
            sections_first_render=False,
            section_sync_limit=section_limit,
            defer_category_loads=False,
        )

    return TreeIconLoadingPolicy(
        sections_first_render=sections_first,
        section_sync_limit=section_limit,
        defer_category_loads=True,
    )


def get_tiles_icon_loading_policy() -> TilesIconLoadingPolicy:
    app_config = get_runtime_app_config()
    lazy = bool(app_config.ui.get("ui.tiles_lazy_icons", True))
    try:
        prefetch = max(0, int(app_config.ui.get("ui.tiles_icon_prefetch_count", 24)))
    except Exception:
        prefetch = 24
    try:
        sync_cap = max(
            0,
            int(app_config.ui.get("ui.tiles_icon_sync_prefetch_cap", prefetch)),
        )
    except Exception:
        sync_cap = prefetch
    try:
        batch_size = max(1, int(app_config.ui.get("ui.tiles_icon_batch_size", 32)))
    except Exception:
        batch_size = 32

    return TilesIconLoadingPolicy(
        lazy=lazy,
        sync_prefetch_count=min(prefetch, sync_cap),
        batch_size=batch_size,
    )

