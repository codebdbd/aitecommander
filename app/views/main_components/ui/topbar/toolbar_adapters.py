"""Toolbar adapters for top-bar actions with overflow support."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QToolBar, QToolButton

from app.config_data.runtime_config import runtime_app_config
from app.utils.ui.icon.loading_service import icon_loading_service
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import icon_path_service
from app.views.widgets.panels.recent_panel_widget import RECENT_LINKS_LIMIT

logger = logging.getLogger(__name__)


def _icon_from_path(path: Path, fallback: Path | None = None) -> QIcon:
    try:
        icon = create_icon_from_path(str(path))
        if not icon or getattr(icon, "isNull", lambda: True)():
            if fallback is not None:
                icon = create_icon_from_path(str(fallback))
        return icon
    except Exception as exc:
        logger.debug("TopBarToolbar: failed to load icon %s: %s", path, exc)
        if fallback is not None:
            return create_icon_from_path(str(fallback))
        return QIcon()


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
    except Exception:
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


class ToolbarSeparatorController:
    def __init__(self, sep_quick_fav: QAction, sep_fav_recent: QAction) -> None:
        self._sep_quick_fav = sep_quick_fav
        self._sep_fav_recent = sep_fav_recent
        self._counts: dict[str, int] = {"quick": 0, "fav": 0, "recent": 0}

    def set_group_count(self, name: str, count: int) -> None:
        self._counts[name] = max(0, int(count))
        self._update()

    def _update(self) -> None:
        quick = self._counts.get("quick", 0) > 0
        fav = self._counts.get("fav", 0) > 0
        recent = self._counts.get("recent", 0) > 0
        self._sep_quick_fav.setVisible(quick and (fav or recent))
        self._sep_fav_recent.setVisible(fav and recent)


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

    def clear_actions(self) -> None:
        for action in self._actions:
            try:
                self._toolbar.removeAction(action)
                action.deleteLater()
            except Exception:
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
        except Exception:
            logger.debug("TopBarToolbar: failed to configure button", exc_info=True)

    def _update_global_last_button(self) -> None:
        buttons: list[QToolButton] = []
        for action in self._toolbar.actions():
            try:
                button = self._toolbar.widgetForAction(action)
            except Exception:
                continue
            if (
                isinstance(button, QToolButton)
                and bool(button.property("toolbar_btn"))
                and button.isVisible()
            ):
                buttons.append(button)
        if not buttons:
            self._last_marked_button = None
            return
        new_last = buttons[-1]
        previous_last = self._last_marked_button
        if previous_last is new_last:
            return
        if previous_last is not None:
            previous_last.setProperty("toolbar_last", False)
            try:
                previous_last.update()
            except Exception:
                pass
        if not bool(new_last.property("toolbar_last")):
            new_last.setProperty("toolbar_last", True)
            try:
                new_last.update()
            except Exception:
                pass
        self._last_marked_button = new_last

    def setVisible(self, visible: bool) -> None:  # noqa: N802 - Qt-style API
        for action in self._actions:
            try:
                action.setVisible(bool(visible))
            except Exception:
                pass

    def _mark_last_button(self) -> None:
        if not self._buttons:
            self._last_marked_button = None
            return
        new_last = self._buttons[-1]
        previous_last = self._last_marked_button
        if previous_last is new_last:
            return
        if previous_last is not None and previous_last in self._buttons:
            previous_last.setProperty("toolbar_last", False)
            try:
                previous_last.update()
            except Exception:
                pass
        for button in self._buttons[:-1]:
            if bool(button.property("toolbar_last")):
                button.setProperty("toolbar_last", False)
        if not bool(new_last.property("toolbar_last")):
            new_last.setProperty("toolbar_last", True)
            try:
                new_last.update()
            except Exception:
                pass
        self._last_marked_button = new_last


class QuickAddToolbarAdapter(ToolbarActionAdapter):
    def __init__(
        self,
        toolbar: QToolBar,
        *,
        insert_before: QAction | None,
        category_provider: Any | None,
        separator_controller: ToolbarSeparatorController | None = None,
    ) -> None:
        try:
            button_size_raw = runtime_app_config.ui.get_quick_add_button_size()
        except Exception:
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
        for code, icon_name, tooltip in quick_types:
            label = tooltips.get(code, tooltip) or code
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            icon = _icon_from_path(icon_path)
            action = QAction(icon, label, self._toolbar)
            action.setToolTip(label)
            action.triggered.connect(lambda _=False, ct=code: self._on_quick_add(ct))
            self._add_action(action)
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
            except Exception:
                logger.debug("QuickAddToolbar: failed to get current category", exc_info=True)
        if hasattr(provider, "facade") and provider.facade:
            try:
                return provider.facade.get_current_category_id()
            except Exception:
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
            if fast_icons:
                icon_path = _resolve_icon_for_link_fast(link_data)
            else:
                icon_path = resolve_icon_for_link(link_data)
            icon = _icon_from_path(Path(icon_path)) if icon_path else QIcon()
            action = QAction(icon, name, self._toolbar)
            action.setToolTip(name)
            action.setData(link_data)
            action.triggered.connect(lambda _=False, data=link_data: self._on_link(data))
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
        except Exception:
            logger.debug("TopBarToolbar: failed to emit clearRequested", exc_info=True)

    def _on_link(self, link_data: dict[str, Any]) -> None:
        self.actionRequested.emit({"type": "open_link", "link": link_data})
        if self._emit_refresh_on_click:
            self.refreshRequested.emit({"limit": RECENT_LINKS_LIMIT})

    @staticmethod
    def _normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                result.append(dict(item))
        return result
