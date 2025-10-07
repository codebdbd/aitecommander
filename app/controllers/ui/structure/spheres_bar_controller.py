# app/controllers/ui/structure/spheres_bar_controller.py
from __future__ import annotations

import logging
from functools import partial
from typing import Any, Dict, Iterable, List

from PyQt6.QtCore import QObject, QSize, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QToolButton

from app.config_data import app_config
from app.utils.db.synchronization import signal_guard
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.updates import suspend_updates

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
        except Exception:
            logger.exception("SpheresBarController.init: failed to connect spheres_loaded")
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
            logger.exception("SpheresBarController._clear_spheres_bar: cannot clear buttons dict")
            raise
        group.setExclusive(True)

    def _build_button(self, sphere: Dict[str, Any]) -> QToolButton:
        btn = QToolButton()
        sphere_id = sphere["id"]
        btn.setCheckable(True)
        icon_name = sphere.get("icon_path")
        if icon_name:
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            if icon_path.exists():
                btn.setIcon(create_icon_from_path(str(icon_path)))
            else:
                btn.setIcon(QIcon())
        else:
            btn.setIcon(QIcon())
        # Enforce square size for sphere buttons
        btn.setFixedSize(62, 62)
        # Remove internal margins at widget level
        try:
            btn.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        # Icon size from UI config; 4px padding is controlled by QSS padding
        try:
            _sz = app_config.get_sphere_button_icon_size()
            btn.setIconSize(QSize(int(_sz[0]), int(_sz[1])))
        except Exception:
            pass
        btn.setToolTip(sphere["name"])
        self.w.sphere_group.addButton(btn, sphere_id)
        btn.clicked.connect(partial(self._on_button_clicked, sphere_id))
        # Ensure there are no graphics effects (neon, etc.) on the button
        try:
            btn.setGraphicsEffect(None)
        except Exception:
            pass
        self.w.sphere_buttons[sphere_id] = btn
        return btn

    @pyqtSlot(list)
    def on_spheres_loaded_ui(self, spheres: List[Dict[str, Any]]):
        """Build sphere buttons in the bar."""
        with suspend_updates(self.w.spheres_bar):
            self._clear_spheres_bar()
            s_layout = self.w.spheres_bar.layout()
            for sp in spheres:
                btn = self._build_button(sp)
                s_layout.addWidget(btn)
            # Explicit update after batch operations
            self.w.spheres_bar.update()

        # Set visual state and/or active sphere
        if not spheres:
            return

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
