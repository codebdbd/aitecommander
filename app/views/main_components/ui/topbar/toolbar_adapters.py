"""Toolbar adapters for top-bar actions with overflow support."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPixmap
from PyQt6.QtWidgets import QMenu, QSizePolicy, QToolBar, QToolButton, QWidget, QWidgetAction

from app.config_data.runtime_config import runtime_app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import (
    resolve_icon_for_link,
    resolve_link_type_icon,
)
from app.utils.ui.icon.loading_service import icon_loading_service
from app.utils.ui.icon.path_service import icon_path_service
from app.views.widgets.panels.recent_panel_widget import RECENT_LINKS_LIMIT

__all__ = [
    "ToolbarSeparatorController",
    "ToolbarActionAdapter",
    "LinksToolbarAdapter",
    "QuickAddToolbarAdapter",
    "FavoritesToolbarAdapter",
    "RecentHistoryToolbarAdapter",
    "StructureActionsToolbarAdapter",
    "ToolsToolbarAdapter",
]

logger = logging.getLogger(__name__)


def _icon_from_path(
    path: Path,
    fallback: Path | None = None,
    link_type: str = "file",
) -> QIcon:
    try:
        icon = create_icon_from_path(str(path))
        if not icon or getattr(icon, "isNull", lambda: True)():
            if fallback is not None:
                icon = create_icon_from_path(str(fallback))
            elif link_type:
                fallback_path = resolve_link_type_icon(link_type)
                if fallback_path:
                    icon = create_icon_from_path(str(fallback_path))
        return icon
    except (TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.debug("TopBarToolbar: failed to load icon %s: %s", path, exc)
        if fallback is not None:
            return create_icon_from_path(str(fallback))
        try:
            fallback_path = resolve_link_type_icon(link_type)
            if fallback_path:
                return create_icon_from_path(str(fallback_path))
        except (TypeError, ValueError, RuntimeError, OSError):
            pass
        return QIcon()




def _setup_topbar_button_contrast(
    btn: QToolButton,
    normal_icon: QIcon,
    svg_filename: str,
) -> None:
    btn.setIcon(normal_icon)


def _resolve_existing_icon_path_fast(icon_path: str | None) -> str:
    return icon_loading_service.resolve_existing_path(icon_path)


def _resolve_icon_for_link_fast(link_data: dict[str, Any] | None) -> str:
    if not isinstance(link_data, dict):
        return ""

    explicit = _resolve_existing_icon_path_fast(link_data.get("icon_path"))
    if explicit:
        return explicit

    try:
        link_type = ((link_data.get("type") or "file").strip() or "file").lower()
    except (AttributeError, TypeError):
        link_type = "file"

    return resolve_link_type_icon(link_type)


def _button_sizes(button_size: int | tuple[int, int], icon_size: tuple[int, int]) -> tuple[QSize, QSize]:
    if isinstance(button_size, (list, tuple)) and len(button_size) >= 2:
        bw, bh = int(button_size[0]), int(button_size[1])
    else:
        bw = bh = int(button_size)
    iw, ih = int(icon_size[0]), int(icon_size[1])
    iw = max(1, min(iw, bw))
    ih = max(1, min(ih, bh))
    return QSize(max(1, bw), max(1, bh)), QSize(iw, ih)


def _resolve_theme(category_provider: Any | None = None) -> str:
    theme = None
    if category_provider is not None:
        if hasattr(category_provider, "settings") and hasattr(
            category_provider.settings, "get_theme"
        ):
            theme = category_provider.settings.get_theme()
    if not theme:
        try:
            from app.core.settings_manager import SettingsManager

            theme = SettingsManager.get("theme.name")
        except Exception:
            pass
    if not theme:
        try:
            from app.utils.ui.icon.path_service import get_current_theme

            theme = get_current_theme()
        except Exception:
            theme = "light"
    return theme or "light"


def _format_link_rich_tooltip(link_data: dict[str, Any]) -> str:
    """Format rich HTML tooltip for a link button/action with target, category, and timestamp."""
    name = link_data.get("name") or "Unknown"
    tooltip_parts = [f"<b>{name}</b>"]
    target_path = link_data.get("path") or link_data.get("url") or link_data.get("target")
    if target_path:
        tooltip_parts.append(f"📍 {target_path}")
    category_name = link_data.get("category_name") or link_data.get("category")
    if category_name:
        tooltip_parts.append(f"📁 {category_name}")
    last_opened = link_data.get("last_opened_at") or link_data.get("last_opened")
    if last_opened:
        tooltip_parts.append(f"🕐 {last_opened}")
    return "<br/>".join(tooltip_parts)


class ToolbarSeparatorController:
    def __init__(
        self,
        sep_add_tools: QAction | None = None,
        sep_tools_recent: QAction | None = None,
        sep_recent_fav: QAction | None = None,
    ) -> None:
        self._sep_add_tools = sep_add_tools
        self._sep_tools_recent = sep_tools_recent
        self._sep_recent_fav = sep_recent_fav
        if self._sep_add_tools is not None:
            self._sep_add_tools.setVisible(False)
        if self._sep_tools_recent is not None:
            self._sep_tools_recent.setVisible(False)
        if self._sep_recent_fav is not None:
            self._sep_recent_fav.setVisible(False)
        self._counts: dict[str, int] = {
            "structure": 0,
            "quick": 0,
            "tools": 0,
            "fav": 0,
            "recent": 0,
        }

    def set_group_count(self, name: str, count: int) -> None:
        self._counts[name] = max(0, int(count))
        self._update()

    def _update(self) -> None:
        structure = self._counts.get("structure", 0)
        quick = self._counts.get("quick", 0)
        tools = self._counts.get("tools", 0)
        recent = self._counts.get("recent", 0)
        fav = self._counts.get("fav", 0)

        add_block = structure + quick
        if self._sep_add_tools is not None:
            self._sep_add_tools.setVisible(add_block > 0 and (tools > 0 or recent > 0 or fav > 0))
        if self._sep_tools_recent is not None:
            self._sep_tools_recent.setVisible(tools > 0 and (recent > 0 or fav > 0))
        if self._sep_recent_fav is not None:
            self._sep_recent_fav.setVisible(recent > 0 and fav > 0)


class TopBarMenu(QMenu):
    """Dropdown menu for top toolbar buttons that seamlessly aligns its top border with the button's bottom border."""

    _active_menu: TopBarMenu | None = None

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._target_button: QWidget | None = None

    def set_target_button(self, button: QWidget) -> None:
        self._target_button = button

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        TopBarMenu._active_menu = self
        if self._target_button is not None and self._target_button.isVisible():
            self._target_button.setFocus(Qt.FocusReason.MouseFocusReason)
            self._target_button.setProperty("menu_active", True)
            self._target_button.style().unpolish(self._target_button)
            self._target_button.style().polish(self._target_button)
            btn_bottom = self._target_button.mapToGlobal(
                QPoint(0, self._target_button.height() - 1)
            ).y()
            if self.y() != btn_bottom:
                self.move(self.x(), btn_bottom)

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        if TopBarMenu._active_menu is self:
            TopBarMenu._active_menu = None
        if self._target_button is not None:
            self._target_button.setProperty("menu_active", False)
            if self._target_button.underMouse():
                hover_icon = getattr(self._target_button, "_hover_icon", None)
                if hover_icon and not hover_icon.isNull():
                    self._target_button.setIcon(hover_icon)
            else:
                rest_icon = getattr(self._target_button, "_rest_icon", None)
                if rest_icon and not rest_icon.isNull():
                    self._target_button.setIcon(rest_icon)
            self._target_button.style().unpolish(self._target_button)
            self._target_button.style().polish(self._target_button)


class ToolbarActionAdapter(QObject):
    actionRequested = pyqtSignal(object)
    refreshRequested = pyqtSignal(object)
    clearRequested = pyqtSignal()

    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        button_object_name: str,
        button_size: QSize,
        icon_size: QSize,
    ) -> None:
        super().__init__(toolbar)
        self._toolbar = toolbar
        self._insert_before = insert_before
        self._button_object_name = button_object_name
        self._button_size = button_size
        self._icon_size = icon_size
        self._actions: list[QAction] = []
        self._buttons: list[QToolButton] = []
        self._last_marked_button: QToolButton | None = None

    @property
    def actions(self) -> list[QAction]:
        """Return a copy of the registered actions list."""
        return list(self._actions)

    def clear_actions(self) -> None:
        for action in self._actions:
            try:
                menu = action.menu()
                if menu is not None:
                    menu.deleteLater()
                self._toolbar.removeAction(action)
                action.deleteLater()
            except (RuntimeError, AttributeError):
                pass
        self._actions.clear()
        self._buttons.clear()
        self._last_marked_button = None

    def _add_action(self, action: QAction) -> None:
        if self._insert_before is not None:
            self._toolbar.insertAction(self._insert_before, action)
        else:
            self._toolbar.addAction(action)
        self._actions.append(action)
        try:
            button = self._toolbar.widgetForAction(action)
            if isinstance(button, QToolButton):
                button.setObjectName(self._button_object_name)
                button.setIconSize(self._icon_size)
                button.setProperty("toolbar_btn", True)
                button.setProperty("toolbar_last", False)
                label = action.toolTip() or action.text()
                if label:
                    button.setAccessibleName(label)
                    button.setAccessibleDescription(label)
                self._buttons.append(button)
        except (RuntimeError, AttributeError):
            logger.debug("TopBarToolbar: failed to configure button", exc_info=True)

    def _add_separator(self) -> QAction:
        if self._insert_before is not None:
            sep = self._toolbar.insertSeparator(self._insert_before)
        else:
            sep = self._toolbar.addSeparator()
        self._actions.append(sep)
        return sep

    def _set_button_last(self, button: QToolButton, is_last: bool) -> None:
        if bool(button.property("toolbar_last")) == is_last:
            return
        button.setProperty("toolbar_last", is_last)
        try:
            style = button.style()
            if style is not None:
                style.unpolish(button)
                style.polish(button)
            button.update()
        except (RuntimeError, AttributeError):
            pass

    def _update_global_last_button(self) -> None:
        new_last: QToolButton | None = None
        for action in reversed(self._toolbar.actions()):
            try:
                button = self._toolbar.widgetForAction(action)
            except (RuntimeError, AttributeError):
                continue
            if (
                isinstance(button, QToolButton)
                and bool(button.property("toolbar_btn"))
                and not button.isHidden()
            ):
                new_last = button
                break

        previous_last = self._toolbar.property("_global_last_button")
        if not isinstance(previous_last, QToolButton):
            previous_last = getattr(self._toolbar, "_global_last_button", None)
        if previous_last is new_last:
            return
        if previous_last is not None:
            self._set_button_last(previous_last, False)
        if new_last is not None:
            self._set_button_last(new_last, True)
        self._toolbar.setProperty("_global_last_button", new_last)
        self._toolbar._global_last_button = new_last

    def set_actions_visible(self, visible: bool) -> None:
        for action in self._actions:
            try:
                action.setVisible(bool(visible))
            except (RuntimeError, AttributeError):
                pass

    def setVisible(self, visible: bool) -> None:  # noqa: N802 - deprecated compatibility alias
        self.set_actions_visible(visible)

    @staticmethod
    def _normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                result.append(dict(item))
        return result

    def _mark_last_button(self) -> None:
        if not self._buttons:
            self._last_marked_button = None
            return
        new_last = self._buttons[-1]
        previous_last = self._last_marked_button
        if previous_last is new_last:
            return
        if previous_last is not None and previous_last in self._buttons:
            self._set_button_last(previous_last, False)
        for button in self._buttons[:-1]:
            self._set_button_last(button, False)
        self._set_button_last(new_last, True)

class StructureActionsToolbarAdapter(ToolbarActionAdapter):
    """Toolbar buttons for structure operations: add section and add category."""

    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        category_provider: Any | None = None,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        button_size_raw = runtime_app_config.ui.get_top_panel_button_size()
        icon_size = runtime_app_config.ui.get_top_panel_icon_size()
        button_size, icon_size = _button_sizes(button_size_raw, icon_size)
        super().__init__(
            toolbar,
            insert_before=insert_before,
            button_object_name="structureButton",
            button_size=button_size,
            icon_size=icon_size,
        )
        self._category_provider = category_provider
        self._separator_controller = separator_controller
        self._build_actions()

    def refresh_actions(self) -> None:
        if (
            hasattr(self, "_toggle_action")
            and hasattr(self, "_back_action")
            and hasattr(self, "_forward_action")
            and hasattr(self, "_sec_action")
            and hasattr(self, "_cat_action")
            and self._actions
        ):
            theme = _resolve_theme(self._category_provider)
            from app.utils.ui.menu_builders.base import get_menu_icon

            toggle_icon = get_menu_icon("left_panel_close", theme)
            if toggle_icon and not toggle_icon.isNull():
                self._toggle_action.setIcon(toggle_icon)
                btn = self._toolbar.widgetForAction(self._toggle_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, toggle_icon, "left_panel_close.svg")

            back_icon = get_menu_icon("skip_previous", theme)
            if back_icon and not back_icon.isNull():
                self._back_action.setIcon(back_icon)
                btn = self._toolbar.widgetForAction(self._back_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, back_icon, "skip_previous.svg")

            fwd_icon = get_menu_icon("skip_next", theme)
            if fwd_icon and not fwd_icon.isNull():
                self._forward_action.setIcon(fwd_icon)
                btn = self._toolbar.widgetForAction(self._forward_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, fwd_icon, "skip_next.svg")

            sec_icon = get_menu_icon("add_section", theme)
            if sec_icon and not sec_icon.isNull():
                self._sec_action.setIcon(sec_icon)
                btn = self._toolbar.widgetForAction(self._sec_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, sec_icon, "add_section.svg")

            cat_icon = get_menu_icon("add_category", theme)
            if cat_icon and not cat_icon.isNull():
                self._cat_action.setIcon(cat_icon)
                btn = self._toolbar.widgetForAction(self._cat_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, cat_icon, "add_category.svg")
            return

        self._build_actions()

    def _build_actions(self) -> None:
        self.clear_actions()
        theme = _resolve_theme(self._category_provider)
        from app.utils.ui.menu_builders.base import get_menu_icon

        # Toggle sidebar
        toggle_icon = get_menu_icon("left_panel_close", theme)
        if not toggle_icon or toggle_icon.isNull():
            toggle_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "left_panel_close.svg")
        toggle_text = QCoreApplication.translate("MenuActions", "Toggle sidebar")
        toggle_action = QAction(toggle_icon, toggle_text, self._toolbar)
        toggle_action.setToolTip(toggle_text)
        toggle_action.triggered.connect(self._on_toggle_left_panel)
        self._add_action(toggle_action)
        self._toggle_action = toggle_action
        toggle_btn = self._toolbar.widgetForAction(toggle_action)
        if isinstance(toggle_btn, QToolButton):
            toggle_btn.setObjectName("topBarToggleLeftPanelButton")
            _setup_topbar_button_contrast(toggle_btn, toggle_icon, "left_panel_close.svg")

        # Navigate back
        back_icon = get_menu_icon("skip_previous", theme)
        if not back_icon or back_icon.isNull():
            back_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "skip_previous.svg")
        back_text = QCoreApplication.translate("MenuActions", "Back")
        back_action = QAction(back_icon, back_text, self._toolbar)
        back_action.setToolTip(f"{back_text} (Alt+Left)")
        back_action.setShortcut("Alt+Left")
        back_action.triggered.connect(self._on_navigate_back)
        self._add_action(back_action)
        self._back_action = back_action
        back_btn = self._toolbar.widgetForAction(back_action)
        if isinstance(back_btn, QToolButton):
            back_btn.setObjectName("topBarBackButton")
            _setup_topbar_button_contrast(back_btn, back_icon, "skip_previous.svg")

        # Navigate forward
        fwd_icon = get_menu_icon("skip_next", theme)
        if not fwd_icon or fwd_icon.isNull():
            fwd_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "skip_next.svg")
        fwd_text = QCoreApplication.translate("MenuActions", "Forward")
        fwd_action = QAction(fwd_icon, fwd_text, self._toolbar)
        fwd_action.setToolTip(f"{fwd_text} (Alt+Right)")
        fwd_action.setShortcut("Alt+Right")
        fwd_action.triggered.connect(self._on_navigate_forward)
        self._add_action(fwd_action)
        self._forward_action = fwd_action
        fwd_btn = self._toolbar.widgetForAction(fwd_action)
        if isinstance(fwd_btn, QToolButton):
            fwd_btn.setObjectName("topBarForwardButton")
            _setup_topbar_button_contrast(fwd_btn, fwd_icon, "skip_next.svg")

        self._add_separator()

        # Add section
        sec_icon = get_menu_icon("add_section", theme)
        if not sec_icon or sec_icon.isNull():
            sec_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "add_section.svg")
        sec_text = QCoreApplication.translate("MenuActions", "Add section")
        sec_action = QAction(sec_icon, sec_text, self._toolbar)
        sec_action.setToolTip(sec_text)
        sec_action.triggered.connect(self._on_add_section)
        self._add_action(sec_action)
        self._sec_action = sec_action
        btn = self._toolbar.widgetForAction(sec_action)
        if isinstance(btn, QToolButton):
            btn.setObjectName("topBarAddSectionButton")
            _setup_topbar_button_contrast(btn, sec_icon, "add_section.svg")

        # Add category
        cat_icon = get_menu_icon("add_category", theme)
        if not cat_icon or cat_icon.isNull():
            cat_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "add_category.svg")
        cat_text = QCoreApplication.translate("MenuActions", "Add category")
        cat_action = QAction(cat_icon, cat_text, self._toolbar)
        cat_action.setToolTip(cat_text)
        cat_action.triggered.connect(self._on_add_category)
        self._add_action(cat_action)
        self._cat_action = cat_action
        btn = self._toolbar.widgetForAction(cat_action)
        if isinstance(btn, QToolButton):
            btn.setObjectName("topBarAddCategoryButton")
            _setup_topbar_button_contrast(btn, cat_icon, "add_category.svg")

        self._update_global_last_button()
        if self._separator_controller is not None:
            self._separator_controller.set_group_count("structure", len(self._actions))

    def _on_add_section(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "show_section_dialog"):
            self._category_provider.show_section_dialog()

    def _on_add_category(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "add_new_category"):
            self._category_provider.add_new_category()

    def _on_toggle_left_panel(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "toggle_left_panel"):
            self._category_provider.toggle_left_panel()

    def _on_navigate_back(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "navigate_back"):
            self._category_provider.navigate_back()

    def _on_navigate_forward(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "navigate_forward"):
            self._category_provider.navigate_forward()


class ToolsToolbarAdapter(ToolbarActionAdapter):
    """Toolbar dropdown button for tools (file search, bookmarks import, bad URLs check, and icon refresh)."""

    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        category_provider: Any | None = None,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        button_size_raw = runtime_app_config.ui.get_top_panel_button_size()
        icon_size = runtime_app_config.ui.get_top_panel_icon_size()
        button_size, icon_size = _button_sizes(button_size_raw, icon_size)
        super().__init__(
            toolbar,
            insert_before=insert_before,
            button_object_name="toolButton",
            button_size=button_size,
            icon_size=icon_size,
        )
        self._category_provider = category_provider
        self._separator_controller = separator_controller
        self._build_actions()

    def refresh_actions(self) -> None:
        if hasattr(self, "_main_action") and self._actions and self._main_action is not None:
            theme = _resolve_theme(self._category_provider)
            from app.utils.ui.menu_builders.base import get_menu_icon

            tools_icon = get_menu_icon("construction", theme)
            if tools_icon and not tools_icon.isNull():
                self._main_action.setIcon(tools_icon)
                btn = self._toolbar.widgetForAction(self._main_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, tools_icon, "construction.svg")
            menu = self._create_tools_menu(theme)
            old_menu = self._main_action.menu()
            if old_menu is not None:
                old_menu.deleteLater()
            self._main_action.setMenu(menu)
            btn = self._toolbar.widgetForAction(self._main_action)
            if isinstance(btn, QToolButton):
                menu.set_target_button(btn)
            return

        self._build_actions()

    def _create_tools_menu(self, theme: str) -> TopBarMenu:
        from app.utils.ui.menu_builders.base import get_menu_icon

        menu = TopBarMenu(self._toolbar)
        menu.setObjectName("topBarToolsMenu")

        tools_items = [
            ("search", "search.svg", QCoreApplication.translate("MenuActions", "Search files"), self._on_file_search),
            ("bookmark_import", "bookmark_import.svg", QCoreApplication.translate("MenuActions", "Import Bookmarks"), self._on_import_bookmarks),
            (None, None, None, None),
            ("link_off", "link_off.svg", QCoreApplication.translate("MenuActions", "Check Links"), self._on_check_bad_urls),
            ("refresh", "refresh.svg", QCoreApplication.translate("MainMenu", "Refresh Icons"), self._on_refresh_icons),
        ]

        for icon_name, svg_file, text, handler in tools_items:
            if icon_name is None:
                menu.addSeparator()
                continue
            item_icon = get_menu_icon(icon_name, theme)
            if not item_icon or item_icon.isNull():
                item_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / svg_file)
            sub_action = QAction(item_icon, text, menu)
            sub_action.setToolTip(text)
            sub_action.triggered.connect(handler)
            menu.addAction(sub_action)

        return menu

    def _build_actions(self) -> None:
        self.clear_actions()
        theme = _resolve_theme(self._category_provider)
        from app.utils.ui.menu_builders.base import get_menu_icon

        tools_icon = get_menu_icon("construction", theme)
        if not tools_icon or tools_icon.isNull():
            tools_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "construction.svg")

        menu = self._create_tools_menu(theme)

        tools_title = QCoreApplication.translate("MenuActions", "Tools")
        main_action = QAction(tools_icon, tools_title, self._toolbar)
        main_action.setToolTip(tools_title)
        main_action.setMenu(menu)
        self._add_action(main_action)
        self._main_action = main_action

        btn = self._toolbar.widgetForAction(main_action)
        if isinstance(btn, QToolButton):
            btn.setObjectName("topBarToolsButton")
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu.set_target_button(btn)
            _setup_topbar_button_contrast(btn, tools_icon, "construction.svg")

        self._update_global_last_button()
        if self._separator_controller is not None:
            self._separator_controller.set_group_count("tools", len(self._actions))

    def _on_file_search(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "show_file_search_dialog"):
            self._category_provider.show_file_search_dialog()

    def _on_import_bookmarks(self) -> None:
        if self._category_provider and hasattr(self._category_provider, "handle_import_browser_bookmarks"):
            self._category_provider.handle_import_browser_bookmarks()

    def _on_check_bad_urls(self) -> None:
        if self._category_provider:
            sd = getattr(self._category_provider, "system_dialogs", None)
            if sd and hasattr(sd, "handle_check_bad_urls"):
                sd.handle_check_bad_urls()
            elif hasattr(self._category_provider, "keyboard_manager"):
                km = getattr(self._category_provider, "keyboard_manager", None)
                if km and hasattr(km, "handle_check_bad_urls"):
                    km.handle_check_bad_urls()

    def _on_refresh_icons(self) -> None:
        if self._category_provider:
            sd = getattr(self._category_provider, "system_dialogs", None)
            if sd and hasattr(sd, "handle_refresh_icons"):
                sd.handle_refresh_icons()
            elif hasattr(self._category_provider, "keyboard_manager"):
                km = getattr(self._category_provider, "keyboard_manager", None)
                if km and hasattr(km, "handle_refresh_icons"):
                    km.handle_refresh_icons()


class QuickAddToolbarAdapter(ToolbarActionAdapter):
    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        category_provider: Any | None,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        button_size_raw = runtime_app_config.ui.get_top_panel_button_size()
        icon_size = runtime_app_config.ui.get_top_panel_icon_size()
        button_size, icon_size = _button_sizes(button_size_raw, icon_size)
        super().__init__(
            toolbar,
            insert_before=insert_before,
            button_object_name="quickButton",
            button_size=button_size,
            icon_size=icon_size,
        )
        self._category_provider = category_provider
        self._separator_controller = separator_controller
        self._build_quick_actions()

    def refresh_actions(self) -> None:
        """Refresh quick-add action icon in place."""
        if hasattr(self, "_main_action") and self._actions:
            theme = _resolve_theme(self._category_provider)

            from app.utils.ui.menu_builders.base import get_menu_icon

            add_icon = get_menu_icon("add_link", theme)
            if not add_icon or add_icon.isNull():
                add_icon_path = icon_path_service.get_ui_icons_dir() / "base" / "add_link.svg"
                add_icon = _icon_from_path(add_icon_path, link_type="file")
            if add_icon and not add_icon.isNull():
                self._main_action.setIcon(add_icon)
                btn = self._toolbar.widgetForAction(self._main_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, add_icon, "add_link.svg")
            return

        self._build_quick_actions()

    def refresh_buttons(self) -> None:
        """Alias to keep compatibility with widget-based quick add panels."""
        self.refresh_actions()

    def set_data(self, _items: list[Any]) -> None:
        """No-op: quick add actions are driven by settings, not external data."""
        return

    def get_items(self) -> list[dict[str, Any]]:
        """Quick add doesn't expose data items; return empty list."""
        return []

    def _build_quick_actions(self) -> None:
        self.clear_actions()
        quick_types = runtime_app_config.settings.get_quick_types()
        tooltips = runtime_app_config.settings.get_quick_type_tooltips()

        type_dict: dict[str, tuple[str, str]] = {}
        for code, icon_name, tooltip in quick_types:
            label = tooltips.get(code, tooltip) or code
            type_dict[code] = (icon_name, label)

        from app.utils.links.type_labels import LINK_TYPE_DESCRIPTORS

        ordered_codes = [descriptor.key for descriptor in LINK_TYPE_DESCRIPTORS]
        for code in type_dict:
            if code not in ordered_codes:
                ordered_codes.append(code)

        theme = _resolve_theme(self._category_provider)

        from app.utils.ui.menu_builders.base import get_menu_icon

        add_icon = get_menu_icon("add_link", theme)
        if not add_icon or add_icon.isNull():
            add_icon_path = icon_path_service.get_ui_icons_dir() / "base" / "add_link.svg"
            add_icon = _icon_from_path(add_icon_path, link_type="file")

        menu = TopBarMenu(self._toolbar)
        menu.setObjectName("quickAddMenu")

        for code in ordered_codes:
            if code not in type_dict:
                continue
            icon_name, label = type_dict[code]
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            icon = _icon_from_path(icon_path, link_type=code)
            sub_action = QAction(icon, label, menu)
            sub_action.setToolTip(label)
            sub_action.triggered.connect(
                lambda checked=False, ct=code: self._on_quick_add(ct)
            )
            menu.addAction(sub_action)

        main_action = QAction(add_icon, self.tr("Add Link"), self._toolbar)
        main_action.setToolTip(self.tr("Add Link"))
        main_action.setMenu(menu)
        self._add_action(main_action)
        self._main_action = main_action

        btn = self._toolbar.widgetForAction(main_action)
        if isinstance(btn, QToolButton):
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu.set_target_button(btn)
            _setup_topbar_button_contrast(btn, add_icon, "add_link.svg")

        self._mark_last_button()
        self._update_global_last_button()
        if self._separator_controller is not None:
            self._separator_controller.set_group_count("quick", len(self._actions))

    def _on_quick_add(self, link_type: str) -> None:
        category_id = self._get_current_category_id()
        payload = {
            "type": "quick_add",
            "link_type": link_type,
            "category_id": category_id,
        }
        self.actionRequested.emit(payload)

    def _get_current_category_id(self) -> int | None:
        provider = self._category_provider
        if provider is None:
            return None
        target = provider if hasattr(provider, "get_current_category_id") else getattr(provider, "facade", None)
        if target is not None and hasattr(target, "get_current_category_id"):
            try:
                return target.get_current_category_id()
            except (RuntimeError, AttributeError, TypeError, ValueError):
                logger.debug("QuickAddToolbar: failed to get current category", exc_info=True)
        return None


class LinksToolbarAdapter(ToolbarActionAdapter):
    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        button_object_name: str,
        group_name: str,
        emit_refresh_on_click: bool = False,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        button_size_raw = runtime_app_config.ui.get_top_panel_button_size()
        icon_size = runtime_app_config.ui.get_top_panel_icon_size()
        button_size, icon_size = _button_sizes(button_size_raw, icon_size)
        super().__init__(
            toolbar,
            insert_before=insert_before,
            button_object_name=button_object_name,
            button_size=button_size,
            icon_size=icon_size,
        )
        self._group_name = group_name
        self._emit_refresh_on_click = emit_refresh_on_click
        self._separator_controller = separator_controller
        self._last_items: list[dict[str, Any]] = []
        self._link_actions: list[QAction] = []
        self._more_action: QAction | None = None
        self._is_folded: bool = False

    def set_data(
        self,
        items: list[dict[str, Any]],
        *,
        fast_icons: bool = False,
    ) -> None:
        self._last_items = self._normalize_items(items)
        for act in self._link_actions:
            try:
                self._toolbar.removeAction(act)
                act.deleteLater()
            except (RuntimeError, AttributeError):
                pass
        self._link_actions.clear()

        for link_data in self._last_items:
            name = link_data.get("name") or "Unknown"
            link_type = ((link_data.get("type") or "file").strip() or "file").lower()
            if fast_icons:
                icon_path = _resolve_icon_for_link_fast(link_data)
            else:
                icon_path = resolve_icon_for_link(link_data)
            icon = (
                _icon_from_path(Path(icon_path), link_type=link_type)
                if icon_path
                else _icon_from_path(Path(""), link_type=link_type)
            )
            action = QAction(icon, name, self._toolbar)
            action.setToolTip(_format_link_rich_tooltip(link_data))
            action.setData(link_data)
            action.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
            self._link_actions.append(action)
            self._add_action(action)
            btn = self._toolbar.widgetForAction(action)
            if isinstance(btn, QToolButton) and self._group_name == "fav":
                btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                btn.customContextMenuRequested.connect(
                    lambda pos, b=btn, data=link_data: self._show_context_menu(b.mapToGlobal(pos), data)
                )

        if self._group_name == "fav":
            self._setup_more_action(fast_icons=fast_icons)
            self._apply_fold_visibility()

        self._mark_last_button()
        self._update_global_last_button()
        if self._separator_controller is not None:
            count = 1 if (self._is_folded and self._last_items) else len(self._link_actions)
            self._separator_controller.set_group_count(self._group_name, count)

    def _show_context_menu(self, global_pos: QPoint, link_data: dict[str, Any]) -> None:
        menu = QMenu(self._toolbar)
        theme = _resolve_theme()
        from app.utils.ui.menu_builders.base import get_menu_icon

        edit_icon = get_menu_icon("edit", theme)
        if not edit_icon or edit_icon.isNull():
            edit_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "edit.svg")
        edit_text = QCoreApplication.translate("MenuActions", "Edit")
        edit_action = QAction(edit_icon, edit_text, menu)
        edit_action.triggered.connect(
            lambda checked=False, d=link_data: self.actionRequested.emit(
                {"type": "edit_link", "link": d}
            )
        )
        menu.addAction(edit_action)

        del_icon = get_menu_icon("delete_favorites", theme)
        if not del_icon or del_icon.isNull():
            del_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "delete_favorites.svg")
        del_text = QCoreApplication.translate("MenuActions", "Remove from favorites")
        del_action = QAction(del_icon, del_text, menu)
        del_action.triggered.connect(
            lambda checked=False, d=link_data: self.actionRequested.emit(
                {"type": "remove_favorite", "link": d}
            )
        )
        menu.addAction(del_action)

        menu.exec(global_pos)

    def _setup_more_action(self, *, fast_icons: bool = False) -> None:
        from app.utils.ui.menu_builders.base import get_menu_icon
        theme = _resolve_theme()
        icon = get_menu_icon("more", theme)
        if not icon or icon.isNull():
            icon_path = icon_path_service.get_ui_icons_dir() / "base" / "more.svg"
            icon = _icon_from_path(icon_path)

        menu = TopBarMenu(self._toolbar)
        menu.setObjectName("favoriteLinksMenu")
        for link_data in self._last_items:
            name = link_data.get("name") or "Unknown"
            link_type = ((link_data.get("type") or "file").strip() or "file").lower()
            icon_p = _resolve_icon_for_link_fast(link_data) if fast_icons else resolve_icon_for_link(link_data)
            item_icon = _icon_from_path(Path(icon_p), link_type=link_type) if icon_p else _icon_from_path(Path(""), link_type=link_type)
            act = QAction(item_icon, name, menu)
            act.setData(link_data)
            act.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
            menu.addAction(act)

        if self._more_action is None:
            more_act = QAction(icon, self.tr("Favorites"), self._toolbar)
            more_act.setToolTip(self.tr("Favorites"))
            more_act.setMenu(menu)
            self._more_action = more_act
            self._add_action(more_act)
            btn = self._toolbar.widgetForAction(more_act)
            if isinstance(btn, QToolButton):
                btn.setObjectName("favoriteMoreButton")
                btn.setProperty("toolbar_btn", True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                menu.set_target_button(btn)
                _setup_topbar_button_contrast(btn, icon, "more.svg")
        else:
            old_menu = self._more_action.menu()
            if old_menu is not None:
                old_menu.deleteLater()
            self._more_action.setMenu(menu)
            btn = self._toolbar.widgetForAction(self._more_action)
            if isinstance(btn, QToolButton):
                menu.set_target_button(btn)

    def set_folded(self, folded: bool) -> None:
        if self._group_name != "fav" or self._is_folded == folded:
            return
        self._is_folded = folded
        self._apply_fold_visibility()
        if self._separator_controller is not None:
            count = 1 if (self._is_folded and self._last_items) else len(self._link_actions)
            self._separator_controller.set_group_count(self._group_name, count)

    def is_folded(self) -> bool:
        return self._is_folded

    def _apply_fold_visibility(self) -> None:
        has_items = bool(self._last_items)
        if self._more_action is not None:
            self._more_action.setVisible(self._is_folded and has_items)
        for act in self._link_actions:
            act.setVisible((not self._is_folded) and has_items)

    def refresh_actions(self) -> None:
        if self._more_action is not None:
            from app.utils.ui.menu_builders.base import get_menu_icon
            theme = _resolve_theme()
            icon = get_menu_icon("more", theme)
            if not icon or icon.isNull():
                icon_path = icon_path_service.get_ui_icons_dir() / "base" / "more.svg"
                icon = _icon_from_path(icon_path)
            if icon and not icon.isNull():
                self._more_action.setIcon(icon)
                btn = self._toolbar.widgetForAction(self._more_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, icon, "more.svg")

    def get_items(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._last_items]

    def get_limit(self) -> int | None:
        if self._group_name != "recent":
            return None
        return RECENT_LINKS_LIMIT

    def clear_favorites(self) -> None:
        """Emit clearRequested to mirror FavoritesPanelWidget behavior."""
        if self._group_name != "fav":
            return
        try:
            self.clearRequested.emit()
        except (RuntimeError, AttributeError):
            logger.debug("TopBarToolbar: failed to emit clearRequested", exc_info=True)

    def _on_link(self, link_data: dict[str, Any]) -> None:
        self.actionRequested.emit({"type": "open_link", "link": link_data})
        if self._emit_refresh_on_click:
            self.refreshRequested.emit({"limit": RECENT_LINKS_LIMIT})


class FavoritesToolbarAdapter(ToolbarActionAdapter):
    """Single favorites button with a popup menu showing favorite links."""

    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        button_object_name: str = "favoriteButton",
        category_provider: Any | None = None,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        button_size_raw = runtime_app_config.ui.get_top_panel_button_size()
        icon_size = runtime_app_config.ui.get_top_panel_icon_size()
        button_size, icon_size = _button_sizes(button_size_raw, icon_size)
        super().__init__(
            toolbar,
            insert_before=insert_before,
            button_object_name=button_object_name,
            button_size=button_size,
            icon_size=icon_size,
        )
        self._category_provider = category_provider
        self._separator_controller = separator_controller
        self._last_items: list[dict[str, Any]] = []
        self._main_action: QAction | None = None
        self._rebuild_menu()

    def _resolve_theme(self) -> str:
        return _resolve_theme(self._category_provider)

    def refresh_actions(self) -> None:
        """Refresh favorites button icon in place without destroying toolbar buttons."""
        if hasattr(self, "_main_action") and self._actions:
            theme = _resolve_theme(self._category_provider)
            from app.utils.ui.menu_builders.base import get_menu_icon

            fav_icon = get_menu_icon("add_favorites", theme)
            if not fav_icon or fav_icon.isNull():
                fav_icon_path = icon_path_service.get_ui_icons_dir() / "base" / "add_favorites.svg"
                fav_icon = _icon_from_path(fav_icon_path, link_type="file")
            if fav_icon and not fav_icon.isNull():
                self._main_action.setIcon(fav_icon)
                btn = self._toolbar.widgetForAction(self._main_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, fav_icon, "add_favorites.svg")
            return
        self._rebuild_menu()

    def set_data(
        self,
        items: list[dict[str, Any]],
        *,
        fast_icons: bool = False,
    ) -> None:
        self._last_items = self._normalize_items(items)
        self._rebuild_menu(fast_icons=fast_icons)

    def get_items(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._last_items]

    def clear_favorites(self) -> None:
        try:
            self.clearRequested.emit()
        except (RuntimeError, AttributeError):
            logger.debug("TopBarToolbar: failed to emit clearRequested", exc_info=True)

    def _rebuild_menu(self, *, fast_icons: bool = False) -> None:
        has_main = self._main_action is not None and self._main_action in self._actions
        if not has_main:
            self.clear_actions()
        theme = self._resolve_theme()

        from app.utils.ui.menu_builders.base import get_menu_icon

        fav_icon = get_menu_icon("add_favorites", theme)
        if not fav_icon or fav_icon.isNull():
            fav_icon = get_menu_icon("fav_ok", theme)
        if not fav_icon or fav_icon.isNull():
            fav_icon_path = icon_path_service.get_ui_icons_dir() / "base" / "add_favorites.svg"
            fav_icon = _icon_from_path(fav_icon_path, link_type="file")

        menu = TopBarMenu(self._toolbar)
        menu.setObjectName("favoriteLinksMenu")

        if not self._last_items:
            empty_action = QAction(self.tr("No favorite links"), menu)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)
        else:
            for link_data in self._last_items:
                name = link_data.get("name") or "Unknown"
                link_type = ((link_data.get("type") or "file").strip() or "file").lower()
                if fast_icons:
                    icon_path = _resolve_icon_for_link_fast(link_data)
                else:
                    icon_path = resolve_icon_for_link(link_data)
                icon = (
                    _icon_from_path(Path(icon_path), link_type=link_type)
                    if icon_path
                    else _icon_from_path(Path(""), link_type=link_type)
                )
                action = QAction(icon, name, menu)
                action.setToolTip(_format_link_rich_tooltip(link_data))
                action.setData(link_data)
                action.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
                menu.addAction(action)

        if has_main and self._main_action is not None:
            old_menu = self._main_action.menu()
            if old_menu is not None:
                old_menu.deleteLater()
            self._main_action.setMenu(menu)
            btn = self._toolbar.widgetForAction(self._main_action)
            if isinstance(btn, QToolButton):
                menu.set_target_button(btn)
        else:
            main_action = QAction(fav_icon, self.tr("Favorites"), self._toolbar)
            main_action.setToolTip(self.tr("Favorites"))
            main_action.setMenu(menu)
            self._main_action = main_action
            self._add_action(main_action)

            btn = self._toolbar.widgetForAction(main_action)
            if isinstance(btn, QToolButton):
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                menu.set_target_button(btn)
                _setup_topbar_button_contrast(btn, fav_icon, "add_favorites.svg")

            self._mark_last_button()
            self._update_global_last_button()
            if self._separator_controller is not None:
                self._separator_controller.set_group_count("fav", len(self._actions))

    def _on_link(self, link_data: dict[str, Any]) -> None:
        self.actionRequested.emit({"type": "open_link", "link": link_data})


class RecentHistoryToolbarAdapter(ToolbarActionAdapter):
    """Single history button with a popup menu showing recent links."""

    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        button_object_name: str = "recentButton",
        category_provider: Any | None = None,
        emit_refresh_on_click: bool = True,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        button_size_raw = runtime_app_config.ui.get_top_panel_button_size()
        icon_size = runtime_app_config.ui.get_top_panel_icon_size()
        button_size, icon_size = _button_sizes(button_size_raw, icon_size)
        super().__init__(
            toolbar,
            insert_before=insert_before,
            button_object_name=button_object_name,
            button_size=button_size,
            icon_size=icon_size,
        )
        self._category_provider = category_provider
        self._emit_refresh_on_click = emit_refresh_on_click
        self._separator_controller = separator_controller
        self._last_items: list[dict[str, Any]] = []
        self._main_action: QAction | None = None
        self._rebuild_menu()

    def _resolve_theme(self) -> str:
        return _resolve_theme(self._category_provider)

    def refresh_actions(self) -> None:
        """Refresh history button icon in place without destroying toolbar buttons."""
        if hasattr(self, "_main_action") and self._actions:
            theme = _resolve_theme(self._category_provider)
            from app.utils.ui.menu_builders.base import get_menu_icon

            history_icon = get_menu_icon("history", theme)
            if not history_icon or history_icon.isNull():
                history_icon_path = icon_path_service.get_ui_icons_dir() / "base" / "history.svg"
                history_icon = _icon_from_path(history_icon_path, link_type="file")
            if history_icon and not history_icon.isNull():
                self._main_action.setIcon(history_icon)
                btn = self._toolbar.widgetForAction(self._main_action)
                if isinstance(btn, QToolButton):
                    _setup_topbar_button_contrast(btn, history_icon, "history.svg")
            return
        self._rebuild_menu()

    def set_data(
        self,
        items: list[dict[str, Any]],
        *,
        fast_icons: bool = False,
    ) -> None:
        self._last_items = self._normalize_items(items)
        self._rebuild_menu(fast_icons=fast_icons)

    def get_items(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._last_items]

    def get_limit(self) -> int:
        return RECENT_LINKS_LIMIT

    def _rebuild_menu(self, *, fast_icons: bool = False) -> None:
        has_main = self._main_action is not None and self._main_action in self._actions
        if not has_main:
            self.clear_actions()
        theme = self._resolve_theme()

        from app.utils.ui.menu_builders.base import get_menu_icon

        history_icon = get_menu_icon("history", theme)
        if not history_icon or history_icon.isNull():
            history_icon_path = icon_path_service.get_ui_icons_dir() / "base" / "history.svg"
            history_icon = _icon_from_path(history_icon_path, link_type="file")

        menu = TopBarMenu(self._toolbar)
        menu.setObjectName("recentLinksMenu")

        if not self._last_items:
            empty_action = QAction(self.tr("No recent links"), menu)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)
        else:
            for link_data in self._last_items:
                name = link_data.get("name") or "Unknown"
                link_type = ((link_data.get("type") or "file").strip() or "file").lower()
                if fast_icons:
                    icon_path = _resolve_icon_for_link_fast(link_data)
                else:
                    icon_path = resolve_icon_for_link(link_data)
                icon = (
                    _icon_from_path(Path(icon_path), link_type=link_type)
                    if icon_path
                    else _icon_from_path(Path(""), link_type=link_type)
                )
                action = QAction(icon, name, menu)
                action.setToolTip(_format_link_rich_tooltip(link_data))
                action.setData(link_data)
                action.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
                menu.addAction(action)

        if has_main and self._main_action is not None:
            old_menu = self._main_action.menu()
            if old_menu is not None:
                old_menu.deleteLater()
            self._main_action.setMenu(menu)
            btn = self._toolbar.widgetForAction(self._main_action)
            if isinstance(btn, QToolButton):
                menu.set_target_button(btn)
        else:
            main_action = QAction(history_icon, self.tr("Recent Links"), self._toolbar)
            main_action.setToolTip(self.tr("Recent Links"))
            main_action.setMenu(menu)
            self._main_action = main_action
            self._add_action(main_action)

            btn = self._toolbar.widgetForAction(main_action)
            if isinstance(btn, QToolButton):
                btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                menu.set_target_button(btn)
                _setup_topbar_button_contrast(btn, history_icon, "history.svg")

            self._mark_last_button()
            self._update_global_last_button()
            if self._separator_controller is not None:
                self._separator_controller.set_group_count("recent", len(self._actions))

    def _on_link(self, link_data: dict[str, Any]) -> None:
        self.actionRequested.emit({"type": "open_link", "link": link_data})
        if self._emit_refresh_on_click:
            self.refreshRequested.emit({"limit": RECENT_LINKS_LIMIT})
