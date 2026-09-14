# app/views/widgets/spheres/sphere_tool_button.py
from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QToolButton, QWidget

from app.config_data.runtime_config import get_section_mime_type
from app.utils.ui.dnd.mime import MimeDataParser

logger = logging.getLogger(__name__)


class SphereToolButton(QToolButton):
    """Tool button representing a sphere, supporting Drag & Drop of sections."""

    section_dropped = pyqtSignal(int, int)  # (section_id, target_sphere_id)

    def __init__(self, sphere_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sphere_id = int(sphere_id)
        self.setCheckable(True)
        self.setAcceptDrops(True)
        self._is_drag_over = False

    def _extract_section_info(self, event: Any) -> tuple[int | None, int | None]:
        mime = event.mimeData() if hasattr(event, "mimeData") else None
        if not mime:
            return None, None

        # 1. Primary: dedicated section MIME type
        sec_mime = get_section_mime_type()
        if mime.hasFormat(sec_mime):
            ids, source_sphere = MimeDataParser.extract_section_payload(mime)
            if ids:
                return ids[0], source_sphere

        # 2. Fallback: application/x-structure-tree-index
        if mime.hasFormat("application/x-structure-tree-index"):
            try:
                raw = bytes(mime.data("application/x-structure-tree-index")).decode("utf-8")
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    item_type, item_id = data[0]
                    if item_type == "section" and isinstance(item_id, int):
                        return item_id, None
            except Exception:
                pass

        return None, None

    def _is_valid_drop(self, event: Any) -> bool:
        sec_id, source_sphere = self._extract_section_info(event)
        if sec_id is None:
            return False
        # Do not allow drop if section is from the same sphere
        if source_sphere is not None and source_sphere == self.sphere_id:
            return False
        if source_sphere is None:
            main_win = self.window()
            sb = getattr(main_win, "structure_business", None)
            if sb and getattr(sb, "current_sphere_id", None) == self.sphere_id:
                return False
        # Do not allow drop if this button is currently checked (current active sphere)
        if self.isChecked():
            return False
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._is_valid_drop(event):
            event.acceptProposedAction()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._is_valid_drop(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_over(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_over(False)
        if self._is_valid_drop(event):
            sec_id, _ = self._extract_section_info(event)
            if sec_id is not None:
                event.acceptProposedAction()
                self.section_dropped.emit(sec_id, self.sphere_id)
                return
        event.ignore()

    def _set_drag_over(self, value: bool) -> None:
        if self._is_drag_over != value:
            self._is_drag_over = value
            self.setProperty("dragOver", value)
            try:
                style = self.style()
                if style:
                    style.unpolish(self)
                    style.polish(self)
            except Exception:
                pass
            self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._is_drag_over:
            painter = QPainter(self)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                pen = QPen(QColor(0, 120, 215), 2)
                painter.setPen(pen)
                rect = self.rect().adjusted(1, 1, -1, -1)
                painter.drawRoundedRect(rect, 4, 4)
            finally:
                painter.end()
