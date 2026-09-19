# app/views/widgets/spheres/sphere_tool_button.py
from __future__ import annotations

import json
import logging
from typing import Any

from PyQt6.QtCore import QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PyQt6.QtWidgets import QStyle, QStyleOptionToolButton, QToolButton, QWidget

from app.config_data.runtime_config import get_section_mime_type
from app.utils.ui.dnd.mime import MimeDataParser

logger = logging.getLogger(__name__)


class SphereToolButton(QToolButton):
    """Tool button representing a sphere, supporting Drag & Drop of sections."""

    section_dropped = pyqtSignal(int, int)  # (section_id, target_sphere_id)
    sections_dropped = pyqtSignal(list, int)  # (section_ids, target_sphere_id)

    def __init__(self, sphere_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sphere_id = int(sphere_id)
        self.setCheckable(True)
        self.setAcceptDrops(True)
        self._is_drag_over = False
        self._hover_scale: float = 0.0
        self._target_scale: float = 0.0
        self._lerp_timer: QTimer = QTimer(self)
        self._lerp_timer.setInterval(16)  # ~60 FPS
        self._lerp_timer.timeout.connect(self._step_lerp)
        self.setMouseTracking(True)

    def set_target_scale(self, target: float) -> None:
        """Set target magnification factor (0.0 - 1.0)."""
        self._target_scale = max(0.0, min(1.0, float(target)))
        if not self._lerp_timer.isActive():
            self._lerp_timer.start()

    def _step_lerp(self) -> None:
        """Smooth LERP interpolation step for silky 60 FPS motion."""
        diff = self._target_scale - self._hover_scale
        if abs(diff) < 0.002:
            self._hover_scale = self._target_scale
            self._lerp_timer.stop()
            self.update()
            return
        self._hover_scale += diff * 0.18
        self.update()

    def set_hover_scale(self, scale: float) -> None:
        """Legacy setter compatibility."""
        self.set_target_scale(scale)

    def animate_scale_to(self, target: float, duration_ms: int = 120) -> None:
        """Smooth animation compatibility."""
        self.set_target_scale(target)

    def _extract_section_info(self, event: Any) -> tuple[list[int], int | None]:
        mime = event.mimeData() if hasattr(event, "mimeData") else None
        if not mime:
            return [], None

        # 1. Primary: dedicated section MIME type
        sec_mime = get_section_mime_type()
        if mime.hasFormat(sec_mime):
            ids, source_sphere = MimeDataParser.extract_section_payload(mime)
            if ids:
                return ids, source_sphere

        # 2. Fallback: application/x-structure-tree-index
        if mime.hasFormat("application/x-structure-tree-index"):
            try:
                raw = bytes(mime.data("application/x-structure-tree-index")).decode("utf-8")
                data = json.loads(raw)
                if isinstance(data, list):
                    section_ids = []
                    for item in data:
                        if not (isinstance(item, list) and len(item) == 2):
                            continue
                        item_type, item_id = item
                        if item_type == "section" and isinstance(item_id, int):
                            section_ids.append(item_id)
                    if section_ids:
                        return section_ids, None
            except Exception:
                pass

        return [], None

    def _is_valid_drop(self, event: Any) -> bool:
        section_ids, source_sphere = self._extract_section_info(event)
        if not section_ids:
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
            section_ids, _ = self._extract_section_info(event)
            if section_ids:
                event.acceptProposedAction()
                self.sections_dropped.emit(section_ids, self.sphere_id)
                for section_id in section_ids:
                    self.section_dropped.emit(section_id, self.sphere_id)
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
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            rect = self.rect()

            # 1. Фоновая подложка из QSS (hover / checked / pressed)
            opt = QStyleOptionToolButton()
            self.initStyleOption(opt)
            opt.icon = QIcon()  # стиль отрисовывает только фон, иконку рисуем сами со скруглением
            self.style().drawComplexControl(QStyle.ComplexControl.CC_ToolButton, opt, painter, self)

            # 2. Отрисовка иконки со скруглением углов (squircle)
            icon = self.icon()
            if not icon.isNull():
                # Физика macOS Dock: рост строго вверх от нижней базовой линии
                s = self._hover_scale
                size = 56.0 + 14.0 * s           # 56px в покое -> 70px на пике (+14px)
                bottom_y = float(rect.height() - 14)  # фиксированная базовая линия
                top_y = bottom_y - size
                left_x = (rect.width() - size) / 2.0
                icon_rect_f = QRectF(left_x, top_y, size, size)

                path = QPainterPath()
                path.addRoundedRect(icon_rect_f, 8.0, 8.0)

                painter.save()
                painter.setClipPath(path)
                pix = icon.pixmap(64, 64)
                painter.drawPixmap(icon_rect_f, pix, QRectF(pix.rect()))
                painter.restore()

            # 3. Нижний круглый индикатор (macOS dot): ТОЛЬКО для активной сферы
            if self.isChecked():
                dot_d = 5.0
                dot_x = (rect.width() - dot_d) / 2.0
                dot_y = float(rect.height() - dot_d - 3.0)
                dot_rect = QRectF(dot_x, dot_y, dot_d, dot_d)

                accent = self.palette().color(QPalette.ColorRole.ButtonText)
                if accent.name().lower() in ("#000000", "#ffffff", "#ddf7ff", "#00000000"):
                    accent = QColor("#00D7FF")

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(accent))
                painter.drawEllipse(dot_rect)

            # 4. Состояние Drag & Drop
            if self._is_drag_over:
                painter.setPen(QPen(QColor(0, 120, 215), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                d_rect = rect.adjusted(1, 1, -1, -1)
                painter.drawRoundedRect(QRectF(d_rect), 6.0, 6.0)
        finally:
            painter.end()
