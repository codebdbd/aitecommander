# app/controllers/ui/structure/spheres_bar_controller.py
from __future__ import annotations

import logging
from collections.abc import Iterable
from functools import partial
from typing import Any

from PyQt6.QtCore import QCoreApplication, QObject, QPoint, QSize, Qt, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QMenu, QToolButton, QWidget

from app.config_data.runtime_config import get_sphere_button_icon_size
from app.utils.ui.db_sync import signal_guard
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import (
    get_default_sphere_icon_name,
    resolve_icon_path,
    resolve_sphere_icon_path,
)
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.menu_builders.base import get_menu_icon
from app.utils.ui.updates import suspend_updates
from app.views.windows.dialogs.entity_dialogs import SphereRenameDialog

logger = logging.getLogger(__name__)


class SpheresBarController(QObject):
    """UI controller for the spheres bar.

    Moved from MainWindow methods:
      - _init_spheres_ui
      - _on_spheres_loaded_ui
      - _update_active_sphere_button
      - _switch_sphere (private logic calling structure.switch_sphere)
    """

    def __init__(self, window: Any):
        parent = window if isinstance(window, QObject) else None
        super().__init__(parent=parent)
        self.w = window  # Main window (QMainWindow with required attributes)

        required_attrs = [
            "structure_business",
            "structure",
            "sphere_group",
            "spheres_bar",
            "sphere_buttons",
        ]
        missing = [name for name in required_attrs if not hasattr(self.w, name)]
        if missing:
            raise AttributeError(
                "SpheresBarController requires window attributes: " + ", ".join(missing)
            )

    def init(self) -> None:
        """Subscribe to spheres_loaded and start async loading."""
        sb = getattr(self.w, "structure_business", None)
        if sb is None:
            raise AttributeError("Window must expose structure_business")
        try:
            sb.spheres_loaded.connect(self.on_spheres_loaded_ui)
            if hasattr(sb, "sphere_updated"):
                sb.sphere_updated.connect(self._on_sphere_updated)
        except Exception:
            logger.exception(
                "SpheresBarController.init: failed to connect spheres signals"
            )
            raise
        sb.load_spheres_async()

    @pyqtSlot(int)
    def switch_sphere(self, sphere_id: int) -> None:
        """Switch active sphere via structure controller."""
        try:
            self.w.structure.switch_sphere(sphere_id)
        except Exception:
            logger.exception(
                "SpheresBarController.switch_sphere: structure.switch_sphere failed"
            )

    def _clear_spheres_bar(self) -> None:
        # Clear button group
        group = getattr(self.w, "sphere_group", None)
        if group is None:
            raise AttributeError("Window must expose sphere_group")
        for button in list(group.buttons()):
            group.removeButton(button)
        # Clear layout
        s_layout = self.w.spheres_bar.layout()
        if s_layout is None:
            raise AttributeError("spheres_bar.layout() must not be None")
        for i in reversed(range(s_layout.count())):
            widget = s_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        try:
            self.w.sphere_buttons.clear()
        except Exception:
            logger.exception(
                "SpheresBarController._clear_spheres_bar: cannot clear buttons dict"
            )
            raise
        group.setExclusive(True)

    @classmethod
    def _get_default_icon_name_for_sphere(
        cls, sphere: dict[str, Any] | str, position: int | None = None
    ) -> str:
        return get_default_sphere_icon_name(sphere, position)

    def _get_default_icon_for_sphere(
        self, sphere: dict[str, Any] | str, position: int | None = None
    ) -> QIcon:
        icons_dir = icon_path_service.get_ui_icons_dir()
        icon_name = self._get_default_icon_name_for_sphere(sphere, position)
        return create_icon_from_path(str(icons_dir / icon_name))

    def _resolve_sphere_icon(self, sphere: dict[str, Any]) -> QIcon:
        icon_name = sphere.get("icon_path")
        if icon_name:
            resolved = resolve_icon_path(icon_name)
            if resolved:
                icon = create_icon_from_path(resolved)
                if not icon.isNull():
                    return icon
        # Fallback to default icon
        return self._get_default_icon_for_sphere(sphere)

    def _build_button(self, sphere: dict[str, Any]) -> QToolButton:
        btn = QToolButton()
        sphere_id = sphere["id"]
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setIcon(self._resolve_sphere_icon(sphere))
        # Use icon size from config for both icon and button to avoid inner padding
        icon_w, icon_h = get_sphere_button_icon_size()
        btn.setFixedSize(icon_w, icon_h)
        # Remove internal margins at widget level
        try:
            btn.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        # Icon size from UI config; matching button size removes inner padding
        btn.setIconSize(QSize(icon_w, icon_h))
        default_names = {
            "AI": QCoreApplication.translate("SpheresBarController", "AI"),
            "Work": QCoreApplication.translate("SpheresBarController", "Work"),
            "Study": QCoreApplication.translate("SpheresBarController", "Study"),
            "Personal": QCoreApplication.translate("SpheresBarController", "Personal"),
        }
        btn.setToolTip(default_names.get(sphere["name"], sphere["name"]))
        btn.setProperty("sphereName", sphere["name"])
        self.w.sphere_group.addButton(btn, sphere_id)
        btn.clicked.connect(partial(self._on_button_clicked, sphere_id))
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(partial(self._on_context_menu, sphere_id))
        # Ensure there are no graphics effects (neon, etc.) on the button
        try:
            btn.setGraphicsEffect(None)
        except Exception:
            pass
        self.w.sphere_buttons[sphere_id] = btn
        return btn

    @staticmethod
    def _get_default_name_for_sphere(
        sphere: dict[str, Any] | str, position: int | None = None
    ) -> str:
        pos = position
        if pos is None and isinstance(sphere, dict):
            pos = sphere.get("position")
            if pos is None and isinstance(sphere.get("id"), int):
                pos = sphere["id"] - 1

        position_names = ["AI", "Work", "Study", "Personal"]
        if pos is not None and 0 <= int(pos) < len(position_names):
            return position_names[int(pos)]

        return "Work"

    def _get_localized_sphere_name(self, name: str) -> str:
        default_names = {
            "AI": QCoreApplication.translate("SpheresBarController", "AI"),
            "Work": QCoreApplication.translate("SpheresBarController", "Work"),
            "Study": QCoreApplication.translate("SpheresBarController", "Study"),
            "Personal": QCoreApplication.translate("SpheresBarController", "Personal"),
        }
        return default_names.get(name, name)

    def _on_context_menu(self, sphere_id: int, pos: QPoint) -> None:
        button = self.w.sphere_buttons.get(sphere_id)
        if not button:
            return

        sb = getattr(self.w, "structure_business", None)
        sphere = None
        if sb and hasattr(sb, "get_sphere_by_id"):
            sphere = sb.get_sphere_by_id(sphere_id)
        if not sphere and sb:
            for cached_sp in getattr(sb, "_cached_spheres", []):
                if cached_sp.get("id") == sphere_id:
                    sphere = cached_sp
                    break
        if not sphere:
            sphere = {"id": sphere_id, "name": button.property("sphereName") or "", "icon_path": ""}

        theme = "dark"
        settings = getattr(self.w, "settings", None)
        if settings and hasattr(settings, "get_theme"):
            theme = settings.get_theme()

        menu = QMenu(button)

        # 1. Rename sphere action
        rename_action = menu.addAction(
            get_menu_icon("edit", theme),
            QCoreApplication.translate("SpheresBarController", "Rename Sphere..."),
        )
        rename_action.triggered.connect(partial(self._rename_sphere, sphere_id))

        # 2. Reset sphere name action
        reset_name_action = menu.addAction(
            get_menu_icon("refresh", theme),
            QCoreApplication.translate("SpheresBarController", "Reset to Default Name"),
        )
        default_canonical_name = self._get_default_name_for_sphere(sphere)
        current_name = (sphere.get("name") or button.property("sphereName") or "").strip()
        has_custom_name = bool(current_name and current_name != default_canonical_name)
        reset_name_action.setEnabled(has_custom_name)
        reset_name_action.triggered.connect(partial(self._reset_sphere_name, sphere_id))

        # 3. Separator
        menu.addSeparator()

        # 4. Change sphere icon action
        change_icon_action = menu.addAction(
            get_menu_icon("add_ico", theme),
            QCoreApplication.translate("SpheresBarController", "Change Icon..."),
        )
        change_icon_action.triggered.connect(partial(self._change_sphere_icon, sphere_id))

        # 5. Reset sphere icon action
        reset_icon_action = menu.addAction(
            get_menu_icon("refresh", theme),
            QCoreApplication.translate("SpheresBarController", "Reset to Default Icon"),
        )
        default_icon_name = self._get_default_icon_name_for_sphere(sphere)
        current_icon_path = (sphere.get("icon_path") or "").strip()
        has_custom_icon = bool(current_icon_path and current_icon_path != default_icon_name)
        reset_icon_action.setEnabled(has_custom_icon)
        reset_icon_action.triggered.connect(partial(self._reset_sphere_icon, sphere_id))

        menu.exec(button.mapToGlobal(pos))

    def _rename_sphere(self, sphere_id: int) -> None:
        try:
            button = self.w.sphere_buttons.get(sphere_id)
            sb = getattr(self.w, "structure_business", None)
            sphere = None
            if sb and hasattr(sb, "get_sphere_by_id"):
                sphere = sb.get_sphere_by_id(sphere_id)
            if not sphere and sb:
                for cached_sp in getattr(sb, "_cached_spheres", []):
                    if cached_sp.get("id") == sphere_id:
                        sphere = cached_sp
                        break

            current_name = (
                (sphere.get("name") if sphere else None)
                or (button.property("sphereName") if button else "")
                or ""
            )

            parent_widget = button if isinstance(button, QWidget) else self.w
            dialog = SphereRenameDialog(current_name=current_name, parent=parent_widget)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            clean_name = dialog.get_name().strip()
            if not clean_name:
                return

            if clean_name == current_name:
                return

            if sb and hasattr(sb, "update_sphere_name"):
                sb.update_sphere_name(sphere_id, clean_name)

            if button:
                button.setProperty("sphereName", clean_name)
                button.setToolTip(self._get_localized_sphere_name(clean_name))
        except Exception as e:
            logger.exception("SpheresBarController._rename_sphere failed: %s", e)

    def _reset_sphere_name(self, sphere_id: int) -> None:
        try:
            button = self.w.sphere_buttons.get(sphere_id)
            sb = getattr(self.w, "structure_business", None)
            sphere = None
            if sb and hasattr(sb, "get_sphere_by_id"):
                sphere = sb.get_sphere_by_id(sphere_id)
            if not sphere and sb:
                for cached_sp in getattr(sb, "_cached_spheres", []):
                    if cached_sp.get("id") == sphere_id:
                        sphere = cached_sp
                        break

            sphere_dict = sphere or {"id": sphere_id}
            default_name = self._get_default_name_for_sphere(sphere_dict)

            if sb and hasattr(sb, "update_sphere_name"):
                sb.update_sphere_name(sphere_id, default_name)

            if button:
                button.setProperty("sphereName", default_name)
                button.setToolTip(self._get_localized_sphere_name(default_name))
        except Exception as e:
            logger.exception("SpheresBarController._reset_sphere_name failed: %s", e)

    def _change_sphere_icon(self, sphere_id: int) -> None:
        try:
            from app.utils.ui.icon.selection import choose_icon_and_copy

            user_icons_dir = icon_path_service.get_user_icons_dir()
            fname, icon = choose_icon_and_copy(
                self.w,
                user_icons_dir,
                title=QCoreApplication.translate("SpheresBarController", "Select Icon"),
            )
            if not fname or not icon or icon.isNull():
                return

            sb = getattr(self.w, "structure_business", None)
            if sb and hasattr(sb, "update_sphere_icon"):
                sb.update_sphere_icon(sphere_id, fname)

            button = self.w.sphere_buttons.get(sphere_id)
            if button:
                button.setIcon(icon)
        except Exception as e:
            logger.exception("SpheresBarController._change_sphere_icon failed: %s", e)

    def _reset_sphere_icon(self, sphere_id: int) -> None:
        try:
            sb = getattr(self.w, "structure_business", None)
            sphere = None
            if sb and hasattr(sb, "get_sphere_by_id"):
                sphere = sb.get_sphere_by_id(sphere_id)
            if not sphere and sb:
                for cached_sp in getattr(sb, "_cached_spheres", []):
                    if cached_sp.get("id") == sphere_id:
                        sphere = cached_sp
                        break

            button = self.w.sphere_buttons.get(sphere_id)
            sphere_name = (
                (sphere.get("name") if sphere else None)
                or (button.property("sphereName") if button else "")
                or ""
            )
            sphere_dict = sphere or {"id": sphere_id, "name": sphere_name}
            default_icon_name = self._get_default_icon_name_for_sphere(sphere_dict)

            if sb and hasattr(sb, "update_sphere_icon"):
                sb.update_sphere_icon(sphere_id, default_icon_name)

            if button:
                default_icon = create_icon_from_path(
                    str(icon_path_service.get_ui_icons_dir() / default_icon_name)
                )
                button.setIcon(default_icon)
        except Exception as e:
            logger.exception("SpheresBarController._reset_sphere_icon failed: %s", e)


    @pyqtSlot(int, dict)
    def _on_sphere_updated(self, sphere_id: int, data: dict[str, Any]) -> None:
        """Handle individual sphere update without clearing the entire bar."""
        button = self.w.sphere_buttons.get(sphere_id)
        if not button:
            return
        if "icon_path" in data:
            name = str(button.property("sphereName") or "")
            icon = self._resolve_sphere_icon({"id": sphere_id, "icon_path": data["icon_path"], "name": name})
            button.setIcon(icon)
        if "name" in data:
            button.setProperty("sphereName", data["name"])
            button.setToolTip(self._get_localized_sphere_name(data["name"]))

    @pyqtSlot(list)
    def on_spheres_loaded_ui(self, spheres: list[dict[str, Any]]):
        """Build sphere buttons in the bar."""
        if not spheres:
            logger.warning(
                "SpheresBarController.on_spheres_loaded_ui: ignoring empty spheres payload"
            )
            return

        with suspend_updates(self.w.spheres_bar):
            self._clear_spheres_bar()
            s_layout = self.w.spheres_bar.layout()
            for sp in spheres:
                btn = self._build_button(sp)
                s_layout.addWidget(btn)
            # Explicit update after batch operations
            self.w.spheres_bar.update()

        try:
            sb = getattr(self.w, "structure_business", None)
            current_id = getattr(sb, "current_sphere_id", None) if sb else None
        except Exception:
            logger.debug(
                "SpheresBarController.on_spheres_loaded_ui: failed to read current_sphere_id",
                exc_info=True,
            )
            current_id = None

        if isinstance(current_id, int) and current_id > 0:
            # Sphere already selected — only update button and focus
            self.update_active_sphere_button(int(current_id))
            return

        first_id = spheres[0].get("id")
        if isinstance(first_id, int) and first_id > 0:
            self.switch_sphere(int(first_id))

    @signal_guard("update_active_sphere_button")
    @pyqtSlot(int)
    def update_active_sphere_button(self, sphere_id: int):
        """Update state of sphere buttons and focus."""
        buttons = self._iter_sphere_buttons()
        for button in buttons:
            # Remove any graphics effects so neon doesn't remain on the active button
            try:
                button.setGraphicsEffect(None)
            except Exception:
                logger.debug(
                    "SpheresBarController.update_active_sphere_button: setGraphicsEffect(None) failed",
                    exc_info=True,
                )
            button.setChecked(False)

        button = self.w.sphere_buttons.get(sphere_id)
        if not button:
            logger.debug(
                "SpheresBarController.update_active_sphere_button: button for %s not found",
                sphere_id,
            )
            return

        button.setChecked(True)
        button.setFocus()

    @pyqtSlot(int)
    def _on_button_clicked(self, sphere_id: int) -> None:
        self.switch_sphere(sphere_id)

    def _iter_sphere_buttons(self) -> Iterable[QToolButton]:
        try:
            return list(self.w.sphere_buttons.values())
        except Exception:
            logger.exception(
                "SpheresBarController._iter_sphere_buttons: sphere_buttons is not iterable"
            )
            return []
