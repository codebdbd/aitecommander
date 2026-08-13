"""User interface configuration helpers."""

import logging

from PyQt6.QtGui import QFont

from app.core.strings import WindowStrings

from .base_config import BaseConfig
from .qt_adapters import to_qfont

logger = logging.getLogger(__name__)


_DEFAULT_BOTTOM_ACTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "add_section",
        "handler": "show_section_dialog",
        "shortcut": "F3",
    },
    {
        "id": "add_category",
        "handler": "add_new_category",
        "shortcut": "F4",
    },
    {
        "id": "add_link",
        "handler": "show_link_dialog",
        "shortcut": "F1",
    },
    {
        "id": "edit_link",
        "handler": "edit_current",
        "shortcut": "F2",
    },
    {
        "id": "delete_link",
        "handler": "delete_current",
        "shortcut": "Del",
    },
)


def _default_bottom_actions() -> list[dict[str, str]]:
    return [dict(item) for item in _DEFAULT_BOTTOM_ACTIONS]


class UIConfig(BaseConfig):
    """Expose typed accessors for UI-related settings."""

    # === Core UI settings ===

    def get_default_font_size(self) -> int:
        """Return the default font size."""
        return self.get("ui.default_font_size", 12)

    def get_default_icon_size(self) -> int:
        """Return the default icon size."""
        return self.get("ui.default_icon_size", 24)

    def get_widget_icon_fallback_size(self) -> int:
        """Return fallback icon size for widgets without explicit size."""
        return int(self.get("ui.widget_icon_fallback_size", 16))

    def get_application_font(self) -> QFont:
        """Return the base application font."""
        font_config = self.get("ui.application_font")
        return to_qfont(font_config)

    # === Application window ===

    def get_window_width(self) -> int:
        """Return the main window width."""
        return self.get("ui.window.width", 1024)

    def get_window_height(self) -> int:
        """Return the main window height."""
        return self.get("ui.window.height", 768)

    def get_window_min_width(self) -> int:
        """Return the minimum window width."""
        return self.get("ui.window.min_width", 280)

    def get_window_min_height(self) -> int:
        """Return the minimum window height."""
        return self.get("ui.window.min_height", 600)

    def get_main_window_title(self) -> str:
        """Return the main window title."""
        return WindowStrings.WINDOW_TITLE

    def get_main_window_size(self) -> tuple:
        """Return the startup size of the main window."""
        # Single source of truth: ``ui.window.width`` / ``ui.window.height``
        width = self.get("ui.window.width", 1024)
        height = self.get("ui.window.height", 768)
        return (width, height)

    # === Window border and styling ===

    def get_window_border_enabled(self) -> bool:
        """Return whether window border is enabled."""
        return bool(self.get("ui.window_border.enabled", True))

    def get_window_border_width(self) -> int:
        """Return window border width in pixels."""
        return int(self.get("ui.window_border.width", 1))

    def get_window_border_radius(self) -> int:
        """Return window border corner radius in pixels."""
        return int(self.get("ui.window_border.radius", 12))

    def get_window_shadow_enabled(self) -> bool:
        """Return whether window shadow is enabled."""
        return bool(self.get("ui.window_border.shadow_enabled", True))

    def get_window_shadow_blur_radius(self) -> int:
        """Return window shadow blur radius."""
        return int(self.get("ui.window_border.shadow_blur_radius", 20))

    def get_window_shadow_offset(self) -> tuple[int, int]:
        """Return window shadow offset as (x, y)."""
        offset = self.get("ui.window_border.shadow_offset", [0, 4])
        if isinstance(offset, (list, tuple)) and len(offset) == 2:
            return (int(offset[0]), int(offset[1]))
        return (0, 4)

    def get_window_content_margins(self) -> tuple[int, int, int, int]:
        """Return content margins for window border effect."""
        margins = self.get("ui.window.content_margins", [1, 1, 1, 1])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (1, 1, 1, 1)

    # === Icon sizes ===

    def get_icon_size(self) -> list[int]:
        """Return the icon size used in the links table as ``[w, h]``."""
        from .qt_adapters import to_size_list

        size = self.get("ui.icon_size", 24)
        w, h = to_size_list(size)
        return [max(1, int(w)), max(1, int(h))]

    def get_tree_icon_size(self) -> list[int]:
        """Return the tree icon size as ``[w, h]``."""
        from .qt_adapters import to_size_list

        size = self.get("ui.tree_icon_size", 24)
        w, h = to_size_list(size)
        return [max(1, int(w)), max(1, int(h))]

    def get_dialog_icon_size(self) -> list[int]:
        """Return the dialog button icon size as ``[w, h]``."""
        from .qt_adapters import to_size_list

        size = self.get("ui.dialog_icon_size", self.get("ui.default_icon_size", 24))
        w, h = to_size_list(size)
        return [max(1, int(w)), max(1, int(h))]

    def get_dropdown_icon_size(self) -> list[int]:
        """Return the logical icon size for combo box popups as ``[w, h]``."""
        from .qt_adapters import to_size_list

        size = self.get("ui.dropdown_icon_size", self.get("ui.default_icon_size", 24))
        w, h = to_size_list(size)
        return [max(1, int(w)), max(1, int(h))]

    def get_row_height(self) -> int:
        """Return the row height for the links table."""
        return self.get("ui.row_height", 32)

    def get_col_widths(self) -> list:
        """Return the column widths for the links table."""
        return self.get("ui.col_widths", [40, 400, 130])

    def get_max_favorites(self) -> int:
        """Return the maximum number of favorites."""
        return self.get("ui.max_favorites", 10)

    def get_fixed_button_width(self) -> int:
        """Return the fixed width for standard buttons."""
        return self.get("ui.fixed_button_width", 100)

    # === Category tiles ===

    def get_tile_size(self) -> list:
        """Return the tile size for categories as ``[w, h]``."""
        w = int(self.get("ui.tile_width", 110))
        h = int(self.get("ui.tile_height", 110))
        return [w, h]

    def get_tile_size_safe(self) -> tuple[int, int]:
        """Return tile size with safe fallbacks."""
        try:
            w = int(self.get("ui.tile_width", 110))
            h = int(self.get("ui.tile_height", 110))
        except (TypeError, ValueError):
            w, h = 110, 110
        return (w, h)

    def get_tile_icon_size(self) -> list:
        """Return the icon size on category tiles as ``[w, h]``."""
        size = self.get("ui.tile_icon_size", [64, 64])
        if isinstance(size, int):
            return [size, size]
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return [size[0], size[1]]
        return [64, 64]

    def get_tile_icon_size_safe(self) -> tuple[int, int]:
        """Return tile icon size with safe fallbacks."""
        size = self.get("ui.tile_icon_size", [64, 64])
        if isinstance(size, int):
            return (size, size)
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return (int(size[0]), int(size[1]))
        return (64, 64)

    def get_tile_spacing(self) -> int:
        """Return the spacing between category tiles."""
        return self.get("ui.tile_spacing", 6)

    def get_tile_spacing_safe(self) -> int:
        """Return tile spacing with safe fallbacks."""
        try:
            return int(self.get("ui.tile_spacing", 6))
        except (TypeError, ValueError):
            return 6

    def get_tile_padding(self) -> int:
        """Return the inner padding for tiles."""
        return self.get("ui.tile_padding", 6)

    def get_tile_padding_safe(self) -> int:
        """Return tile padding with safe fallbacks."""
        try:
            return int(self.get("ui.tile_padding", 6))
        except (TypeError, ValueError):
            return 6

    def get_tile_icon_text_gap(self) -> int:
        """Return the gap between tile icon and text."""
        return self.get("ui.tile_icon_text_gap", 5)

    def get_tile_text_font_size(self) -> int:
        """Return the tile text font size."""
        return self.get("ui.tile_text_font_size", 11)

    def get_tile_text_max_lines(self) -> int:
        """Return the maximum number of text lines on a tile."""
        return self.get("ui.tile_text_max_lines", 4)

    def get_tile_columns(self) -> int:
        """Return the number of tile columns."""
        return self.get("ui.tile_columns", 6)

    def get_tile_margins(self) -> list:
        """Return tile margins as ``[left, top, right, bottom]``."""
        return self.get("ui.tile_margins", [20, 20, 20, 20])

    def get_tile_width(self) -> int:
        """Return the tile width."""
        return self.get("ui.tile_width", 128)

    def get_tile_height(self) -> int:
        """Return the tile height."""
        return self.get("ui.tile_height", 110)

    def get_tile_border_radius(self) -> int:
        """Return the tile corner radius."""
        return self.get("ui.tile_border_radius", 8)

    def get_tile_border_width(self) -> int:
        """Return the tile border width."""
        return self.get("ui.tile_border_width", 2)

    def get_tile_border_margin(self) -> int:
        """Return the tile border margin."""
        return self.get("ui.tile_border_margin", 2)

    # === Spheres bar ===

    def get_spheres_bar_height(self) -> int:
        """Return the height of the spheres bar."""
        return self.get("ui.spheres_bar_height", 86)

    def get_spheres_bar_min_height(self) -> int:
        """Return the minimum height for the spheres bar."""
        return self.get("ui.spheres_bar_min_height", 86)

    def get_spheres_bar_spacing(self) -> int:
        """Return spacing between elements on the spheres bar."""
        return self.get("ui.spheres_bar_spacing", 8)

    def get_sphere_button_icon_size(self) -> list[int]:
        """Return the sphere button icon size as ``[w, h]``."""
        from .qt_adapters import to_size_list

        # Request a larger size so Qt downscales with better quality
        size = self.get("ui.sphere_button_icon_size", 64)  # increased from 48 to 64
        w, h = to_size_list(size)
        return [max(1, int(w)), max(1, int(h))]

    # === Top panel ===

    def get_tiles_layout_margins(self) -> list:
        """Return layout margins for tiles as ``[L, T, R, B]``."""
        return self.get("ui.tiles_layout_margins", [0, 0, 0, 0])

    def get_quick_add_button_size(self) -> list:
        """Return the size of quick-access buttons as ``[w, h]``."""
        # Single key: ``ui.quick_add_button_size``
        size = self.get("ui.quick_add_button_size", 32)
        if isinstance(size, int):
            return [size, size]
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return [size[0], size[1]]
        return [32, 32]

    def get_top_panel_button_size(self) -> int:
        """Return the standard size for every button in the top panel."""
        return self.get("ui.top_panel_button_size", 36)

    def get_top_panel_icon_size(self) -> list[int]:
        """Return the icon size for top-panel buttons as ``[w, h]``."""
        from .qt_adapters import to_size_list

        size = self.get("ui.top_panel_icon_size", 32)
        w, h = to_size_list(size)
        return [max(1, int(w)), max(1, int(h))]

    # === Structure tree ===

    # === Splitter ===

    def get_splitter_handle_width(self) -> int:
        """Return the splitter handle width."""
        return self.get("ui.splitter_handle_width", 1)

    def get_splitter_stretch_factors(self) -> list:
        """Return splitter stretch factors."""
        return self.get("ui.splitter_stretch_factors", [1, 3])

    def get_splitter_sizes(self) -> list:
        """Return initial splitter sizes."""
        return self.get("ui.splitter_sizes", [250, 750])

    def get_central_frame_shape(self) -> str:
        """Return the frame shape for the central widget."""
        return self.get("ui.central_frame_shape", "StyledPanel")

    def get_top_panel_size_policy(self) -> list:
        """Return size policy configuration for the top panel."""
        return self.get("ui.top_panel_size_policy", ["Expanding", "Fixed"])

    def get_top_bar_height(self) -> int:
        """Return the height of the top bar host widget."""
        return int(self.get("ui.top_bar_height", 40))

    def get_top_panel_search_width(self) -> int:
        """Return the search field width in the top panel."""
        return self.get("ui.top_panel_search_width", 320)

    def get_top_panel_search_min_width(self) -> int:
        """Return the minimum search field width, used when squeezing layout."""
        return self.get("ui.top_panel_search_min_width", 148)

    def get_top_panel_search_height(self) -> int:
        """Return the search field height in the top panel."""
        return self.get("ui.top_panel_search_height", 32)

    def get_topbar_panel_padding(self) -> int:
        """Return padding used in top bar panel placeholders."""
        return int(self.get("ui.topbar.panel_padding", 16))

    def get_topbar_panel_spacing_adjustment(self) -> int:
        """Return spacing adjustment for top bar panels."""
        return int(self.get("ui.topbar.panel_spacing_adjustment", -1))

    def get_topbar_separator_spacing(self) -> int:
        """Return spacing around separators in the top bar."""
        return int(self.get("ui.topbar.separator_spacing", 4))

    def get_topbar_button_size(self) -> int:
        """Return default button size for top bar widgets."""
        return int(self.get("ui.topbar.button_size", 32))

    def get_topbar_max_visible_recent(self) -> int:
        """Return max visible buttons for recent panel."""
        return int(self.get("ui.topbar.max_visible.recent", 10))

    def get_topbar_max_visible_fav(self) -> int:
        """Return max visible buttons for favorites panel."""
        return int(self.get("ui.topbar.max_visible.fav", 10))

    def get_topbar_max_visible_quick(self) -> int:
        """Return max visible buttons for quick panel."""
        return int(self.get("ui.topbar.max_visible.quick", 6))

    def get_topbar_min_panel_width(self) -> int:
        """Return minimum panel width in the top bar."""
        return int(self.get("ui.topbar.min_panel_width", 50))

    def get_topbar_min_search_width_absolute(self) -> int:
        """Return absolute minimum search width for the top bar."""
        return int(self.get("ui.topbar.min_search_width_absolute", 148))

    def get_topbar_max_search_width(self) -> int:
        """Return maximum search width for the top bar."""
        return int(self.get("ui.topbar.max_search_width", 500))

    def get_topbar_max_widget_width(self) -> int:
        """Return maximum widget width for the top bar."""
        return int(self.get("ui.topbar.max_widget_width", 16777215))

    def get_topbar_max_visible_buttons(self) -> int:
        """Return maximum visible button count in top bar panels."""
        return int(self.get("ui.topbar.max_visible_buttons", 20))

    def get_topbar_narrow_threshold(self) -> int:
        """Return the narrow mode threshold for the top bar."""
        return int(self.get("ui.topbar.narrow_threshold", 380))

    def get_topbar_hysteresis_threshold(self) -> int:
        """Return the hysteresis threshold for top bar layout logic."""
        return int(self.get("ui.topbar.hysteresis_threshold", 8))

    def get_main_components_min_search_width(self) -> int:
        """Return minimum search width used by main components."""
        return int(self.get("ui.main_components.min_search_width", 50))

    def get_main_components_max_search_width(self) -> int:
        """Return maximum search width used by main components."""
        return int(self.get("ui.main_components.max_search_width", 800))

    def get_stack_index_tiles(self) -> int:
        """Return the stacked-widget index that shows tiles.

        Supports both ``ui.stack_indices.tiles`` (new) and ``ui.stack_index_tiles`` (legacy).
        """
        val = self.get("ui.stack_indices.tiles")
        if val is None:
            val = self.get("ui.stack_index_tiles", 0)
        return int(val)

    def get_stack_index_table(self) -> int:
        """Return the stacked-widget index that shows the table.

        Supports both ``ui.stack_indices.table`` (new) and ``ui.stack_index_table`` (legacy).
        """
        val = self.get("ui.stack_indices.table")
        if val is None:
            val = self.get("ui.stack_index_table", 1)
        return int(val)

    def get_table_selection_restore_delay(self) -> int:
        """Return the selection restore delay for the links table."""
        return self.get("ui.table_selection_restore_delay", 100)

    def get_thread_pool_shutdown_timeout(self) -> int:
        """Return the thread pool shutdown timeout."""
        return self.get("ui.thread_pool_shutdown_timeout", 2000)

    # === Structure reload timing ===

    def get_structure_reload_delay_ms(self) -> int:
        """Return the coalesced structure reload delay in milliseconds."""
        return int(self.get("ui.structure_reload_delay_ms", 50))

    def get_structure_reload_immediate_delay_ms(self) -> int:
        """Return the immediate structure reload delay (usually 0 ms)."""
        return int(self.get("ui.structure_reload_immediate_delay_ms", 0))

    # === Dialogs ===

    def get_dialogs_enable_details(self) -> bool:
        """Return whether QMessageBox instances show the detailed text section."""
        return self.get("ui.dialogs.enable_details", False)

    def get_delete_confirm_title(self) -> str:
        """Return the delete confirmation dialog title."""
        return "Confirm Deletion"

    def get_delete_confirm_text(self) -> str:
        """Return the delete confirmation dialog body text."""
        return "Are you sure you want to delete {count} link(s)?"

    def get_yes_text(self) -> str:
        """Return the label for the affirmative button."""
        return "Yes"

    def get_no_text(self) -> str:
        """Return the label for the negative button."""
        return "No"

    def get_link_dialog_width(self) -> int:
        """Return the width for the add/edit link dialog."""
        return self.get("ui.link_dialog_width", 600)

    def get_link_dialog_height(self) -> int:
        """Return the height for the add/edit link dialog."""
        return self.get("ui.link_dialog_height", 520)

    def get_link_dialog_margins(self) -> int:
        """Return link dialog margins."""
        return self.get("ui.link_dialog_margins", 20)

    def get_link_dialog_spacing(self) -> int:
        """Return spacing between widgets in the link dialog."""
        return self.get("ui.link_dialog_spacing", 10)

    def get_link_dialog_type_icon_size(self) -> int:
        """Return the icon size for link type buttons in the link dialog."""
        return int(self.get("ui.link_dialog_type_icon_size", 32))

    def get_dialog_control_height(self) -> int:
        """Return the uniform control height for dialogs."""
        return int(self.get("ui.dialogs.control_height", 32))

    def get_dialog_message_box_max_width(self) -> int:
        """Return the maximum width for standard message boxes."""
        return int(self.get("ui.dialogs.message_box_max_width", 400))

    def get_restore_db_dialog_size(self) -> tuple[int, int]:
        """Return the restore DB dialog size."""
        width = int(self.get("ui.dialogs.restore_db.width", 500))
        height = int(self.get("ui.dialogs.restore_db.height", 300))
        return (width, height)

    def get_import_browser_dialog_size(self) -> tuple[int, int]:
        """Return the import browser dialog size."""
        width = int(self.get("ui.dialogs.import_browser.width", 400))
        height = int(self.get("ui.dialogs.import_browser.height", 180))
        return (width, height)

    def get_browser_profile_dialog_min_size(self) -> tuple[int, int]:
        """Return the minimum size for the browser profile dialog."""
        width = int(self.get("ui.dialogs.browser_profile.min_width", 480))
        height = int(self.get("ui.dialogs.browser_profile.min_height", 400))
        return (width, height)

    def get_async_operation_dialog_min_width(self) -> int:
        """Return the minimum width for async operation dialogs."""
        return int(self.get("ui.dialogs.async_operation.min_width", 400))

    def get_async_operation_dialog_spacing(self) -> int:
        """Return layout spacing for async operation dialogs."""
        return int(self.get("ui.dialogs.async_operation.spacing", 15))

    def get_icon_refresh_dialog_min_width(self) -> int:
        """Return the minimum width for icon refresh dialogs."""
        return int(self.get("ui.dialogs.icon_refresh.min_width", 400))

    def get_icon_refresh_buttons_spacing(self) -> int:
        """Return spacing for icon refresh dialog buttons."""
        return int(self.get("ui.dialogs.icon_refresh.buttons_spacing", 8))

    def get_bad_url_cleanup_dialog_min_size(self) -> tuple[int, int]:
        """Return the minimum size for bad URL cleanup dialogs."""
        width = int(self.get("ui.dialogs.bad_url_cleanup.min_width", 900))
        height = int(self.get("ui.dialogs.bad_url_cleanup.min_height", 400))
        return (width, height)

    def get_file_search_dialog_size(self) -> tuple[int, int]:
        """Return the file search dialog size."""
        width = int(self.get("ui.dialogs.file_search.width", 900))
        height = int(self.get("ui.dialogs.file_search.height", 700))
        return (width, height)

    def get_file_search_root_min_width(self) -> int:
        """Return the minimum width for the file search root input."""
        return int(self.get("ui.dialogs.file_search.root_min_width", 200))

    def get_file_search_pattern_max_width(self) -> int:
        """Return the maximum width for the file search pattern input."""
        return int(self.get("ui.dialogs.file_search.pattern_max_width", 100))

    def get_file_search_pattern_combo_extra_width(self) -> int:
        """Return extra width added to the pattern combo for arrow/padding."""
        return int(self.get("ui.dialogs.file_search.pattern_combo_extra_width", 36))

    def get_file_search_content_min_width(self) -> int:
        """Return the minimum width for the file search content input."""
        return int(self.get("ui.dialogs.file_search.content_min_width", 200))

    def get_file_search_size_field_max_width(self) -> int:
        """Return the maximum width for file size inputs."""
        return int(self.get("ui.dialogs.file_search.size_field_max_width", 60))

    def get_entity_dialog_name_spacing(self) -> int:
        """Return spacing inside entity name rows."""
        return int(self.get("ui.dialogs.entity.name_spacing", 6))

    def get_entity_dialog_fixed_width(self) -> int:
        """Return fixed width for entity dialogs."""
        return int(self.get("ui.dialogs.entity.fixed_width", 400))

    def get_settings_dialog_size(self) -> tuple[int, int]:
        """Return the settings dialog size."""
        width = int(self.get("ui.dialogs.settings.width", 420))
        height = int(self.get("ui.dialogs.settings.height", 280))
        return (width, height)

    def get_settings_dialog_margins(self) -> tuple[int, int, int, int]:
        """Return settings dialog layout margins."""
        margins = self.get("ui.dialogs.settings.margins", [12, 12, 12, 12])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (12, 12, 12, 12)

    def get_settings_dialog_spacing(self) -> int:
        """Return settings dialog layout spacing."""
        return int(self.get("ui.dialogs.settings.spacing", 10))

    def get_settings_dialog_form_horizontal_spacing(self) -> int:
        """Return settings dialog form horizontal spacing."""
        return int(self.get("ui.dialogs.settings.form_horizontal_spacing", 12))

    def get_settings_dialog_form_vertical_spacing(self) -> int:
        """Return settings dialog form vertical spacing."""
        return int(self.get("ui.dialogs.settings.form_vertical_spacing", 8))

    def get_settings_dialog_actions_spacing(self) -> int:
        """Return settings dialog action-row spacing."""
        return int(self.get("ui.dialogs.settings.actions_spacing", 8))

    def get_notes_dialog_size(self) -> tuple[int, int]:
        """Return the notes dialog size."""
        width = int(self.get("ui.dialogs.notes.width", 400))
        height = int(self.get("ui.dialogs.notes.height", 300))
        return (width, height)

    def get_chrome_profile_dialog_base_size(self) -> tuple[int, int]:
        """Return the base size for the Chrome profile dialog."""
        width = int(self.get("ui.dialogs.chrome_profiles.base_width", 600))
        height = int(self.get("ui.dialogs.chrome_profiles.base_height", 500))
        return (width, height)

    # === Bottom panel ===

    def get_bottom_actions(self) -> list[dict[str, str]]:
        """Return normalized configuration for bottom panel actions."""
        raw_actions = self.get("ui.bottom_actions", _default_bottom_actions())
        normalized: list[dict[str, str]] = []

        for item in raw_actions or []:
            if isinstance(item, dict):
                handler = str(item.get("handler", "") or "").strip()
                if not handler:
                    continue
                action_id = str(item.get("id", "") or "").strip() or handler
                shortcut = str(item.get("shortcut", "") or "").strip()
                normalized.append(
                    {
                        "id": action_id,
                        "handler": handler,
                        "shortcut": shortcut,
                    }
                )
                continue

            if isinstance(item, (list, tuple)) and len(item) >= 2:
                handler_raw = item[1]
                handler = str(handler_raw or "").strip()
                if not handler:
                    continue

                template = next(
                    (
                        action
                        for action in _DEFAULT_BOTTOM_ACTIONS
                        if action["handler"] == handler
                    ),
                    None,
                )
                if template is not None:
                    normalized.append(dict(template))
                else:
                    label_raw = item[0] if len(item) >= 1 else ""
                    shortcut_raw = item[2] if len(item) >= 3 else ""
                    normalized.append(
                        {
                            "id": str(label_raw or "").strip() or handler,
                            "handler": handler,
                            "shortcut": str(shortcut_raw or "").strip(),
                        }
                    )

        if not normalized:
            normalized = _default_bottom_actions()

        return normalized

    def get_links_table_headers(self) -> list:
        """Return the header labels for the links table."""
        return ["♥", "Name", "Last opened", "Notes"]

    def get_links_table_columns(self) -> dict[str, int]:
        """Return the column indexes for the links table."""
        return self.get(
            "ui.links_table_columns",
            {"favorite": 0, "name": 1, "last_used": 2, "notes": 3},
        )

    def get_links_table_messages(self) -> dict[str, str]:
        """Return localized strings used by the links table UI."""
        return {
            "no_categories": "No categories available. Create a category first.",
            "select_category": "Select a category to insert the link",
            "error_saving": "Error saving note",
            "database_error": "Database error",
            "validation_error": "Validation error",
            "warning_title": "Warning",
            "error_title": "Error",
            "unsafe_url_info": "This link cannot be opened for security reasons.",
            "unsafe_url_hint": "Check the link address or edit it.",
        }

    # === Margins and spacing ===

    def get_layout_margins(self, margin_type: str) -> tuple[int, int, int, int]:
        """Return margins for a layout type as ``(L, T, R, B)``."""
        margins = self.get(f"ui.layout.margins.{margin_type}")
        if margins and len(margins) == 4:
            return tuple(margins)
        default_margins = {
            "main": (0, 0, 0, 0),
            "mid": (0, 0, 0, 0),
            "left": (0, 0, 0, 0),
            "right": (0, 0, 0, 0),
            "bottom": (0, 0, 0, 0),
            "top": (0, 0, 0, 0),
        }
        return default_margins.get(margin_type, (0, 0, 0, 0))

    def get_top_bar_margins(self) -> tuple:
        """Return margins for the top bar."""
        margins = self.get("ui.top_bar_margins", [4, 4, 4, 4])
        return tuple(margins)

    def get_top_bar_spacing(self) -> int:
        """Return spacing between widgets in the top bar."""
        return self.get("ui.layout.spacing.top_bar", 6)

    def get_top_bar_buttons_spacing(self) -> int:
        """Return spacing between buttons inside top bar panels."""
        return self.get(
            "ui.layout.spacing.top_bar_buttons",
            self.get("ui.layout.spacing.top_bar", 8),
        )

    def get_top_bar_widgets_side_spacing(self) -> int:
        """Return side spacing for top bar widgets; neighbor gap equals twice this value."""
        return self.get("ui.layout.spacing.top_bar_widgets_side", 8)

    def get_main_layout_margins(self) -> tuple:
        """Return margins for the main layout."""
        margins = self.get("ui.main_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_main_layout_spacing(self) -> int:
        """Return spacing within the main layout."""
        return self.get("ui.main_layout_spacing", 0)

    def get_mid_layout_margins(self) -> tuple:
        """Return margins for the middle layout."""
        margins = self.get("ui.mid_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_left_layout_margins(self) -> tuple:
        """Return margins for the left layout."""
        margins = self.get("ui.left_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_table_layout_margins(self) -> tuple:
        """Return margins for the table layout."""
        margins = self.get("ui.table_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_table_layout_spacing(self) -> int:
        """Return spacing within the table layout."""
        return self.get("ui.table_layout_spacing", 6)

    def get_tiles_layout_spacing(self) -> int:
        """Return spacing within the tiles layout."""
        return self.get("ui.layout.spacing.tiles", 0)

    def get_right_layout_spacing(self) -> int:
        """Return spacing within the right layout.

        Explicit accessor (no runtime fallbacks). Config key: ``ui.right_layout_spacing``.
        Defaults to ``0``.
        """
        return self.get("ui.right_layout_spacing", 0)

    def get_bottom_layout_margins(self) -> tuple:
        """Return margins for the bottom layout."""
        margins = self.get("ui.bottom_layout_margins", [5, 5, 5, 5])
        return tuple(margins)

    def get_bottom_layout_spacing(self) -> int:
        """Return spacing in the bottom layout."""
        return self.get("ui.layout.spacing.bottom", 0)

    def get_bottom_bar_min_width(self) -> int:
        """Return minimum width for the bottom bar container."""
        return int(self.get("ui.bottom_bar.min_width", 200))

    def get_bottom_bar_button_height(self) -> int:
        """Return fixed height for bottom bar buttons."""
        return int(self.get("ui.bottom_bar.button_height", 32))

    def get_spheres_layout_margins(self) -> tuple:
        """Return margins for the spheres layout."""
        margins = self.get("ui.spheres_layout_margins", [5, 5, 5, 5])
        return tuple(margins)

    def get_spheres_bar_margins(self) -> tuple[int, int, int, int]:
        """Return spheres bar margins, allowing left/right overrides.

        Sources:
        - Base: ``ui.spheres_layout_margins`` `[L, T, R, B]` (default `[5, 5, 5, 5]`)
        - Overrides: ``ui.spheres_bar_margin_left``, ``ui.spheres_bar_margin_right``
        """
        base = list(self.get_spheres_layout_margins())
        left_override = self.get("ui.spheres_bar_margin_left")
        right_override = self.get("ui.spheres_bar_margin_right")
        if isinstance(left_override, int):
            base[0] = left_override
        if isinstance(right_override, int):
            base[2] = right_override
        return tuple(base)

    # === Search and UI text ===

    def get_search_placeholder(self) -> str:
        """Return the placeholder text for the search field."""
        return WindowStrings.SEARCH_PLACEHOLDER

    def get_qss_path(self) -> str:
        """Return path to the default QSS theme file."""
        return self.get("ui.qss_path", "dark.qss")

    # === Macros and status text ===

    def get_macro_add_links_text(self) -> str:
        """Return macro text for adding links."""
        return self.get("ui.macro_add_links_text", "Adding {count} links")

    def get_macro_delete_links_text(self) -> str:
        """Return macro text for deleting links."""
        return self.get("ui.macro_delete_links_text", "Deleting {count} links")

    def get_db_connected_text(self) -> str:
        """Return status text for a connected DB."""
        return "DB: Connected"

    def get_db_disconnected_text(self) -> str:
        """Return status text for a disconnected DB."""
        return "DB: Disconnected"

    def get_links_count_text(self) -> str:
        """Return the default text showing total links."""
        return "Links: 0"

    def get_status_ready_text(self) -> str:
        """Return the "ready" status string."""
        return "Ready"

    def get_path_label_min_width(self) -> int:
        """Return minimum width for the path label."""
        return self.get("ui.path_label_min_width", 350)

    def get_status_bar_margins(self) -> tuple[int, int, int, int]:
        """Return status bar outer margins."""
        margins = self.get("ui.status_bar.margins", [6, 2, 6, 2])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (6, 2, 6, 2)

    def get_status_bar_message_margins(self) -> tuple[int, int, int, int]:
        """Return content margins for the status message label."""
        margins = self.get("ui.status_bar.message_margins", [6, 2, 12, 2])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (6, 2, 12, 2)

    def get_status_bar_path_margins(self) -> tuple[int, int, int, int]:
        """Return content margins for the path label."""
        margins = self.get("ui.status_bar.path_margins", [0, 2, 12, 2])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (0, 2, 12, 2)

    def get_status_bar_db_margins(self) -> tuple[int, int, int, int]:
        """Return content margins for the DB status label."""
        margins = self.get("ui.status_bar.db_margins", [12, 2, 6, 2])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (12, 2, 6, 2)

    def get_status_bar_links_margins(self) -> tuple[int, int, int, int]:
        """Return content margins for the links count label."""
        margins = self.get("ui.status_bar.links_margins", [6, 2, 6, 2])
        if isinstance(margins, (list, tuple)) and len(margins) == 4:
            return tuple(int(v) for v in margins)
        return (6, 2, 6, 2)

    def get_status_bar_min_height(self) -> int:
        """Return the minimum height for the status bar."""
        return int(self.get("ui.status_bar.min_height", 24))

    def get_status_bar_extra_height_padding(self) -> int:
        """Return extra padding added to status bar height calculations."""
        return int(self.get("ui.status_bar.extra_height_padding", 8))

    def get_powershell_path(self) -> str:
        """Return the configured PowerShell executable path."""
        return self.get("ui.powershell_path", "pwsh.exe")

    def get_favorite_icon_size(self) -> int:
        """Return the icon size used for favorites."""
        return self.get("ui.favorite_icon_size", 24)

    # === Additional UI parameters (avoid duplicating QSS values) ===

    def get_menu_font_size(self) -> int:
        """Return the menu font size."""
        return self.get("ui.menu_font_size", 11)

    def get_menu_item_height(self) -> int:
        """Return menu item height."""
        return self.get("ui.menu_item_height", 32)

    def get_menubar_font_size(self) -> int:
        """Return the menubar font size."""
        return self.get("ui.menubar_font_size", 10)

    def get_menubar_item_height(self) -> int:
        """Return menubar item height."""
        return self.get("ui.menubar_item_height", 24)

    def get_menu_icon_size(self) -> int:
        """Return icon size used in menus."""
        return self.get("ui.menu_icon_size", 20)

    def get_menu_indicator_size(self) -> int:
        """Return indicator size used in menus."""
        return self.get("ui.menu_indicator_size", 16)

    def get_scrollbar_width(self) -> int:
        """Return vertical scrollbar width."""
        return self.get("ui.scrollbar_width", 12)

    def get_scrollbar_height(self) -> int:
        """Return horizontal scrollbar height."""
        return self.get("ui.scrollbar_height", 12)

    def get_tree_item_height(self) -> int:
        """Return tree view item height."""
        return self.get("ui.tree_item_height", 32)

    def get_tree_indentation(self) -> int:
        """Return tree view child indentation in pixels."""
        try:
            return max(0, int(self.get("ui.tree_indentation", 20)))
        except (TypeError, ValueError):
            return 20

    def get_table_item_height(self) -> int:
        """Return table view item height."""
        return self.get("ui.table_item_height", 28)

    def get_separator_height(self) -> int:
        """Return separator widget height."""
        return self.get("ui.separator_height", 1)

    def get_separator_width(self) -> int:
        """Return separator width for vertical dividers."""
        return self.get("ui.separator_width", 1)

    # === Debug and performance knobs ===

    def get_debug_links_inline_update(self) -> bool:
        """Enable extended debug logs for inline link-table updates.

        Config key: ``ui.debug_links_inline_update``. Defaults to ``False``.
        """
        # Temporarily enabled by default for diagnostics; set to False in config to disable
        return bool(self.get("ui.debug_links_inline_update", True))

    def get_preload_categories_limit(self) -> int:
        """Return the maximum number of sections to preload after structure load.

        Config key: ``ui.preload_categories_limit``. Defaults to ``3``.
        """
        try:
            return max(0, int(self.get("ui.preload_categories_limit", 3)))
        except Exception:
            return 3

    def get_preload_delay_step_ms(self) -> int:
        """Return delay between category preload tasks in milliseconds.

        Config key: ``ui.preload_delay_step_ms``. Defaults to ``10`` ms.
        """
        try:
            return max(0, int(self.get("ui.preload_delay_step_ms", 10)))
        except Exception:
            return 10

    def get_drop_stale_structure_snapshots(self) -> bool:
        """Return whether outdated structure snapshots should be discarded.

        Config key: ``ui.drop_stale_structure_snapshots``. Defaults to ``True``.
        """
        try:
            return bool(self.get("ui.drop_stale_structure_snapshots", True))
        except Exception:
            return True

    def get_tree_sections_first_render(self) -> bool:
        """Return whether sphere switches should render sections before categories.

        Config key: ``ui.tree_sections_first_render``. Defaults to ``True``.
        """
        try:
            return bool(self.get("ui.tree_sections_first_render", True))
        except Exception:
            return True

    def get_tree_quiet_first_selection(self) -> bool:
        """Return whether first tree selection should suppress signal cascade during setCurrentIndex.

        Config key: ``ui.tree_quiet_first_selection``. Defaults to ``True``.
        """
        try:
            return bool(self.get("ui.tree_quiet_first_selection", True))
        except Exception:
            return True

    def get_tree_section_icon_prewarm_limit(self) -> int:
        """Return the number of top sections to prewarm icons for during sphere switches.

        Config key: ``ui.tree_section_icon_prewarm_limit``. Defaults to ``6``.
        """
        try:
            return max(0, int(self.get("ui.tree_section_icon_prewarm_limit", 6)))
        except Exception:
            return 6

    # === Debug toggles ===

    def get_debug_show_tile_font_sample(self) -> bool:
        """Return whether tile font sample labels should be shown for inspection."""
        return self.get("ui.debug_show_tile_font_sample", False)

    # === Auto-hide and top bar ===

    def get_auto_hide_manage_topbar(self) -> bool:
        """Return whether auto-hide logic should manage top bar visibility.

        Config key: ``ui.auto_hide_manage_topbar``. Defaults to ``False``.
        """
        return bool(self.get("ui.auto_hide_manage_topbar", False))

    def get_auto_hide_switch_to_table(self) -> bool:
        """Return whether auto-hide should switch to table view when tree hides.

        Config key: ``ui.auto_hide_switch_to_table``. Defaults to ``False``.
        """
        return bool(self.get("ui.auto_hide_switch_to_table", False))

    def get_topbar_throttle_ms(self) -> int:
        """Return throttle interval for top bar layout updates in milliseconds.

        Config key: ``ui.topbar.throttle_ms``. Defaults to ``50``.
        """
        return int(self.get("ui.topbar.throttle_ms", 50))

    def get_topbar_log_info(self) -> bool:
        """Return whether info-level logging is enabled for the top bar.

        Config key: ``ui.topbar.log_info``. Defaults to ``False``.
        """
        return bool(self.get("ui.topbar.log_info", False))

    def get_topbar_min_visible_recent(self) -> int:
        """Return minimum number of visible "recent" buttons in the top bar.

        Config key: ``ui.topbar.min_visible.recent``. Defaults to ``0``.
        """
        return int(self.get("ui.topbar.min_visible.recent", 0))

    def get_topbar_min_visible_fav(self) -> int:
        """Return minimum number of visible "favorites" buttons in the top bar.

        Config key: ``ui.topbar.min_visible.fav``. Defaults to ``0``.
        """
        return int(self.get("ui.topbar.min_visible.fav", 0))

    def get_topbar_min_visible_quick(self) -> int:
        """Return minimum number of visible "quick add" buttons in the top bar.

        Config key: ``ui.topbar.min_visible.quick``. Defaults to ``1``.
        """
        return int(self.get("ui.topbar.min_visible.quick", 1))

    def get_topbar_favorites_min_visible_threshold(self) -> int:
        """Return the minimum number of visible favorites buttons before hiding.

        Config key: ``ui.topbar.favorites_min_visible_threshold``. Defaults to ``5``.
        """
        return int(self.get("ui.topbar.favorites_min_visible_threshold", 5))

    def get_topbar_separator_search_spacing(self) -> int:
        """Return the spacing around separators when search widget is present.

        Config key: ``ui.topbar.separator_search_spacing``. Defaults to ``4``.
        """
        return int(self.get("ui.topbar.separator_search_spacing", 4))

    def get_topbar_separator_hidden_spacing(self) -> int:
        """Return the spacing around separators when hidden.

        Config key: ``ui.topbar.separator_hidden_spacing``. Defaults to ``0``.
        """
        return int(self.get("ui.topbar.separator_hidden_spacing", 0))

    def get_topbar_layout_spacing_fallback(self) -> int:
        """Return the fallback spacing value when layout spacing is unavailable.

        Config key: ``ui.topbar.layout_spacing_fallback``. Defaults to ``6``.
        """
        return int(self.get("ui.topbar.layout_spacing_fallback", 6))
