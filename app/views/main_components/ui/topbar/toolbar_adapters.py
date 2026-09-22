"""Toolbar adapters for top-bar actions with overflow support."""
from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

from PyQt6.QtCore import QByteArray, QCoreApplication, QEvent, QObject, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
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


def _contrast_icon_from_path(
    path: Path,
    contrast_color: str = "#FFFFFF",
) -> QIcon:
    try:
        raw_svg = path.read_text(encoding="utf-8")
        tinted = re.sub(r'stroke="(?!none")[^"]*"', f'stroke="{contrast_color}"', raw_svg)
        tinted = re.sub(r'fill="(?!none")[^"]*"', f'fill="{contrast_color}"', tinted)
        if "fill=" not in tinted and "stroke=" not in tinted:
            tinted = raw_svg.replace("<svg ", f'<svg fill="{contrast_color}" ')
        renderer = QSvgRenderer(QByteArray(tinted.encode("utf-8")))
        if not renderer.isValid():
            return QIcon()
        icon = QIcon()
        for sz in (16, 20, 24, 32, 48):
            pm = QPixmap(sz, sz)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
            icon.addPixmap(pm)
        return icon
    except Exception:
        return QIcon()


def _get_theme_contrast_color(theme_name: str | None = None) -> str:
    return "#0E1116"


def _update_button_contrast_icon(btn: QToolButton) -> QIcon | None:
    svg_filename = getattr(btn, "_svg_filename", None)
    if not svg_filename:
        return getattr(btn, "_contrast_icon", None)
    from app.utils.ui.icon.path_service import get_current_theme
    cur_theme = get_current_theme()
    cached_theme = getattr(btn, "_contrast_theme", None)
    contrast_color = _get_theme_contrast_color(cur_theme)
    if (
        cached_theme != cur_theme
        or getattr(btn, "_contrast_icon", None) is None
        or getattr(btn, "_contrast_color", None) != contrast_color
    ):
        svg_path = icon_path_service.get_ui_icons_dir() / "base" / svg_filename
        btn._contrast_icon = _contrast_icon_from_path(svg_path, contrast_color)
        btn._contrast_theme = cur_theme
        btn._contrast_color = contrast_color
    return getattr(btn, "_contrast_icon", None)


class TopBarButtonHoverFilter(QObject):
    """Event filter to invert button icon on hover/pressed while preserving normal icon."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        t = event.type()
        if t in (QEvent.Type.Enter, QEvent.Type.MouseButtonPress):
            if isinstance(obj, QToolButton):
                contrast_icon = _update_button_contrast_icon(obj)
                if contrast_icon and not contrast_icon.isNull():
                    obj.setIcon(contrast_icon)
        elif t == QEvent.Type.Leave:
            if isinstance(obj, QToolButton) and not bool(obj.property("menu_active")):
                normal_icon = getattr(obj, "_normal_icon", None)
                if normal_icon and not normal_icon.isNull():
                    obj.setIcon(normal_icon)
        elif t == QEvent.Type.MouseButtonRelease:
            if isinstance(obj, QToolButton) and not bool(obj.property("menu_active")):
                if not obj.underMouse():
                    normal_icon = getattr(obj, "_normal_icon", None)
                    if normal_icon and not normal_icon.isNull():
                        obj.setIcon(normal_icon)
        elif t == QEvent.Type.ContextMenu:
            return True
        return False


def _setup_topbar_button_contrast(
    btn: QToolButton,
    normal_icon: QIcon,
    svg_filename: str,
) -> None:
    btn._normal_icon = normal_icon
    btn._svg_filename = svg_filename
    btn._contrast_icon = None
    btn._contrast_theme = None
    _update_button_contrast_icon(btn)
    filt = getattr(btn, "_invert_hover_filter", None)
    if filt is None:
        filt = TopBarButtonHoverFilter(btn)
        btn._invert_hover_filter = filt
        btn.installEventFilter(filt)


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


class ToolbarSeparatorController:
    def __init__(self, sep_tools_recent: QAction, sep_recent_fav: QAction) -> None:
        self._sep_tools_recent = sep_tools_recent
        self._sep_recent_fav = sep_recent_fav
        self._sep_tools_recent.setVisible(False)
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

        left_block = structure + quick + tools
        if self._sep_tools_recent is not None:
            self._sep_tools_recent.setVisible(left_block > 0 and recent > 0)
        if self._sep_recent_fav is not None:
            self._sep_recent_fav.setVisible(recent > 0 and fav > 0)


class TopBarMenu(QMenu):
    """Dropdown menu for top toolbar buttons that seamlessly aligns its top border with the button's bottom border."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._target_button: QWidget | None = None

    def set_target_button(self, button: QWidget) -> None:
        self._target_button = button

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self._target_button is not None and self._target_button.isVisible():
            self._target_button.setFocus(Qt.FocusReason.MouseFocusReason)
            self._target_button.setProperty("menu_active", True)
            contrast_icon = _update_button_contrast_icon(self._target_button)
            if contrast_icon and not contrast_icon.isNull():
                self._target_button.setIcon(contrast_icon)
            self._target_button.style().unpolish(self._target_button)
            self._target_button.style().polish(self._target_button)
            btn_bottom = self._target_button.mapToGlobal(
                QPoint(0, self._target_button.height() - 1)
            ).y()
            if self.y() != btn_bottom:
                self.move(self.x(), btn_bottom)

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        if self._target_button is not None:
            self._target_button.setProperty("menu_active", False)
            if self._target_button.underMouse():
                contrast_icon = _update_button_contrast_icon(self._target_button)
                if contrast_icon and not contrast_icon.isNull():
                    self._target_button.setIcon(contrast_icon)
            else:
                normal_icon = getattr(self._target_button, "_normal_icon", None)
                if normal_icon and not normal_icon.isNull():
                    self._target_button.setIcon(normal_icon)
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
                button.setFixedSize(self._button_size)
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

        previous_last = getattr(self._toolbar, "_global_last_button", None)
        if previous_last is new_last:
            return
        if previous_last is not None:
            self._set_button_last(previous_last, False)
        if new_last is not None:
            self._set_button_last(new_last, True)
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
        self._build_actions()

    def _build_actions(self) -> None:
        self.clear_actions()
        theme = _resolve_theme(self._category_provider)
        from app.utils.ui.menu_builders.base import get_menu_icon

        # Add section
        sec_icon = get_menu_icon("add_section", theme)
        if not sec_icon or sec_icon.isNull():
            sec_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "add_section.svg")
        sec_text = QCoreApplication.translate("MenuActions", "Add section")
        sec_action = QAction(sec_icon, sec_text, self._toolbar)
        sec_action.setToolTip(sec_text)
        sec_action.triggered.connect(self._on_add_section)
        self._add_action(sec_action)
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


class ToolsToolbarAdapter(ToolbarActionAdapter):
    """Toolbar buttons for file search, bookmarks import, bad URLs check, and icon refresh."""

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
        self._build_actions()

    def _build_actions(self) -> None:
        self.clear_actions()
        theme = _resolve_theme(self._category_provider)
        from app.utils.ui.menu_builders.base import get_menu_icon

        tools = [
            ("topBarFileSearchButton", "search", "search.svg", QCoreApplication.translate("MenuActions", "Search files"), self._on_file_search),
            ("topBarImportBookmarksButton", "import", "import.svg", QCoreApplication.translate("MenuActions", "Import Bookmarks"), self._on_import_bookmarks),
            ("topBarBadUrlsButton", "link_off", "link_off.svg", QCoreApplication.translate("MainMenu", "Check Bad URLs"), self._on_check_bad_urls),
            ("topBarRefreshIconsButton", "refresh", "refresh.svg", QCoreApplication.translate("MainMenu", "Refresh Icons"), self._on_refresh_icons),
        ]

        for obj_name, icon_name, svg_file, tooltip, handler in tools:
            icon = get_menu_icon(icon_name, theme)
            if not icon or icon.isNull():
                icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / svg_file)
            action = QAction(icon, tooltip, self._toolbar)
            action.setToolTip(tooltip)
            action.triggered.connect(handler)
            self._add_action(action)
            btn = self._toolbar.widgetForAction(action)
            if isinstance(btn, QToolButton):
                btn.setObjectName(obj_name)
                _setup_topbar_button_contrast(btn, icon, svg_file)

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
        """Rebuild quick-add actions (e.g., after theme change)."""
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

        theme = None
        if self._category_provider is not None:
            if hasattr(self._category_provider, "settings") and hasattr(
                self._category_provider.settings, "get_theme"
            ):
                theme = self._category_provider.settings.get_theme()
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

        main_action = QAction(add_icon, self.tr("Add Link..."), self._toolbar)
        main_action.setToolTip(self.tr("Add Link..."))
        main_action.setMenu(menu)
        self._add_action(main_action)

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
        if hasattr(provider, "get_current_category_id"):
            try:
                return provider.get_current_category_id()
            except (RuntimeError, AttributeError, TypeError, ValueError):
                logger.debug("QuickAddToolbar: failed to get current category", exc_info=True)
        if hasattr(provider, "facade") and provider.facade:
            try:
                return provider.facade.get_current_category_id()
            except (RuntimeError, AttributeError, TypeError, ValueError):
                logger.debug("QuickAddToolbar: facade category lookup failed", exc_info=True)
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

    def set_data(
        self,
        items: list[dict[str, Any]],
        *,
        fast_icons: bool = False,
    ) -> None:
        self._last_items = self._normalize_items(items)
        self.clear_actions()
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
            action.setToolTip("<br/>".join(tooltip_parts))

            action.setData(link_data)
            action.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
            self._add_action(action)
        self._mark_last_button()
        self._update_global_last_button()
        if self._separator_controller is not None:
            self._separator_controller.set_group_count(self._group_name, len(self._actions))

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
        self._rebuild_menu()

    def _resolve_theme(self) -> str:
        theme = None
        if self._category_provider is not None:
            if hasattr(self._category_provider, "settings") and hasattr(
                self._category_provider.settings, "get_theme"
            ):
                theme = self._category_provider.settings.get_theme()
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

    def refresh_actions(self) -> None:
        """Refresh favorites button icon on theme change."""
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

                tooltip_parts = [f"<b>{name}</b>"]
                target_path = link_data.get("path") or link_data.get("url") or link_data.get("target")
                if target_path:
                    tooltip_parts.append(f"📍 {target_path}")
                category_name = link_data.get("category_name") or link_data.get("category")
                if category_name:
                    tooltip_parts.append(f"📁 {category_name}")
                action.setToolTip("<br/>".join(tooltip_parts))

                action.setData(link_data)
                action.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
                menu.addAction(action)

        main_action = QAction(fav_icon, self.tr("Favorites"), self._toolbar)
        main_action.setToolTip(self.tr("Favorites"))
        main_action.setMenu(menu)
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
        self._rebuild_menu()

    def _resolve_theme(self) -> str:
        theme = None
        if self._category_provider is not None:
            if hasattr(self._category_provider, "settings") and hasattr(
                self._category_provider.settings, "get_theme"
            ):
                theme = self._category_provider.settings.get_theme()
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

    def refresh_actions(self) -> None:
        """Refresh history button icon on theme change."""
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
                action.setToolTip("<br/>".join(tooltip_parts))

                action.setData(link_data)
                action.triggered.connect(lambda checked=False, data=link_data: self._on_link(data))
                menu.addAction(action)

        main_action = QAction(history_icon, self.tr("Recent Links"), self._toolbar)
        main_action.setToolTip(self.tr("Recent Links"))
        main_action.setMenu(menu)
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
