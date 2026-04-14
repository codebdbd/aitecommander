from __future__ import annotations

import importlib
import os

from app.config_data import runtime_config


def test_runtime_config_alias_and_accessors_smoke() -> None:
    cfg = runtime_config.get_runtime_app_config()
    assert cfg is runtime_config.runtime_app_config

    assert isinstance(runtime_config.get_table_stack_index(), int)
    assert isinstance(runtime_config.get_tiles_stack_index(), int)
    assert isinstance(runtime_config.get_tree_icon_size(), tuple)
    assert isinstance(runtime_config.get_tree_section_icon_prewarm_limit(), int)
    assert isinstance(runtime_config.get_structure_reload_delay_ms(), int)
    assert isinstance(runtime_config.get_structure_reload_immediate_delay_ms(), int)
    assert isinstance(runtime_config.get_slow_update_positions_threshold_sec(), float)


def test_import_smoke_for_migrated_modules() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    modules = [
        "app.views.windows.dialogs.base_dialog",
        "app.views.windows.dialogs.link_dialog.link_dialog",
        "app.views.main_components.ui.window_ui_setup",
        "app.views.main_components.ui.topbar.top_bar_setup",
        "app.views.widgets.link.base_table",
        "app.views.widgets.tiles.widget",
        "app.views.widgets.status_bar",
        "app.views.models.categories_list_model",
        "app.views.models.structure_tree_model",
        "app.services.structure_share_service",
        "app.services.theme_registry",
        "app.services.theme_import_service",
        "app.services.bulk_operation_service",
    ]
    for module_name in modules:
        importlib.import_module(module_name)
