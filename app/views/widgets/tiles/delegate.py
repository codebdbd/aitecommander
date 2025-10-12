# app/views/tiles/delegate.py
from __future__ import annotations

import logging

from PyQt6.QtCore import QModelIndex, QPoint, QPointF, QRect, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QFont,
    QFontMetrics,
    QHelpEvent,
    QIcon,
    QPainter,
    QPen,
    QTextLayout,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from app.config_data import app_config

logger = logging.getLogger("category_tiles")


class CategoryTileDelegate(QStyledItemDelegate):
    """Simple delegate for rendering category tiles."""

    def __init__(self, icon_size: QSize | None = None, tile_size: QSize | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon_size = icon_size or QSize(48, 48)
        self.tile_size = tile_size or QSize(120, 100)
        self.padding = 8
        self.border_radius = 4
        self._font_diag_logged = False

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Render a tile: icon on top, text below."""
        painter.save()
        rect = option.rect
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        # Tile text font is centralized via ui.fonts.tiles_px (QSS)

        try:
            w = option.widget
            style = w.style() if w is not None else None
            if style is not None:
                style.drawPrimitive(
                    QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w
                )
        except (AttributeError, RuntimeError) as e:
            logger.debug("Style primitive draw skipped: %s", e)

        icon_rect = QRect(
            rect.left() + (rect.width() - self.icon_size.width()) // 2,
            rect.top() + self.padding,
            self.icon_size.width(),
            self.icon_size.height(),
        )

        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, icon_rect)
        else:
            mid = option.palette.color(option.palette.ColorRole.Mid)
            dark = option.palette.color(option.palette.ColorRole.Dark)
            text_col = option.palette.color(option.palette.ColorRole.BrightText)
            painter.setBrush(QBrush(mid))
            painter.setPen(QPen(dark))
            painter.drawEllipse(icon_rect)
            try:
                placeholder_font = QFont(painter.font())
                placeholder_font.setBold(True)
                placeholder_font.setPointSize(
                    max(8, int(self.icon_size.height() * 0.45))
                )
                painter.setFont(placeholder_font)
                painter.setPen(QPen(text_col))
                qmark = "?"
                fm_q = QFontMetrics(placeholder_font)
                tw = fm_q.horizontalAdvance(qmark)
                th = fm_q.ascent()
                cx = icon_rect.left() + (icon_rect.width() - tw) // 2
                cy = icon_rect.top() + (icon_rect.height() + th) // 2 - 2
                painter.drawText(QPoint(cx, cy), qmark)
            except (RuntimeError, ValueError) as e:
                logger.debug("Placeholder '?' draw skipped: %s", e)

        if text:
            # Font size diagnostics removed; sizes are centralized via QSS
            text_rect = QRect(
                rect.left() + self.padding,
                rect.top() + self.padding + self.icon_size.height() + 5,
                rect.width() - 2 * self.padding,
                0,
            )
            fm = QFontMetrics(painter.font())
            layout = QTextLayout(text, painter.font())
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.setTextOption(opt)
            layout.beginLayout()
            lines = []
            y = 0
            available_w = text_rect.width()
            try:
                max_lines = int(app_config.ui.get_tile_text_max_lines())
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug("Invalid max_lines config, fallback to 3: %s", e)
                max_lines = 3
            has_more = False
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_w)
                line.setPosition(QPointF(0.0, float(y)))
                lines.append(line)
                y += int(line.height())
                if len(lines) >= max_lines:
                    probe = layout.createLine()
                    has_more = probe.isValid()
                    break
            layout.endLayout()

            text_rect.setHeight(y)

            painter.setPen(option.palette.color(option.palette.ColorRole.WindowText))

            for idx, line in enumerate(lines):
                line_text = text[
                    line.textStart() : line.textStart() + line.textLength()
                ]
                natural_w = line.naturalTextWidth()
                draw_x = text_rect.x() + max(0, (available_w - int(natural_w)) // 2)
                draw_y = text_rect.y() + int(line.position().y()) + fm.ascent()
                if idx == len(lines) - 1 and has_more:
                    elided = fm.elidedText(
                        line_text, Qt.TextElideMode.ElideRight, available_w
                    )
                    if elided == line_text:
                        ellipsis = "…"
                        ell_w = fm.horizontalAdvance(ellipsis)
                        max_w = max(0, available_w - ell_w)
                        core = fm.elidedText(
                            line_text, Qt.TextElideMode.ElideRight, max_w
                        )
                        text_to_draw = (core if core else "") + ellipsis
                    else:
                        text_to_draw = elided
                    draw_w = fm.horizontalAdvance(text_to_draw)
                    draw_x = text_rect.x() + max(0, (available_w - draw_w) // 2)
                    painter.drawText(QPoint(draw_x, draw_y), text_to_draw)
                else:
                    painter.drawText(QPoint(draw_x, draw_y), line_text)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Simple size calculation for a tile."""
        font = QFont(option.font)  # font size comes from QSS (ui.fonts.tiles_px)
        try:
            max_lines = int(app_config.ui.get_tile_text_max_lines())
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("Invalid max_lines config in sizeHint, fallback to 3: %s", e)
            max_lines = 3
        try:
            text = index.data(Qt.ItemDataRole.DisplayRole)
        except (RuntimeError, AttributeError) as e:
            logger.debug("Failed to read DisplayRole in sizeHint: %s", e)
            text = ""
        available_w = self.tile_size.width() - 2 * self.padding
        layout = QTextLayout(text or "", font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.setTextOption(opt)
        layout.beginLayout()
        y = 0
        lines = 0
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(available_w)
            y += int(line.height())
            lines += 1
            if lines >= max_lines:
                break
        layout.endLayout()
        text_h = y
        height = self.padding + self.icon_size.height() + 5 + text_h + self.padding
        return QSize(self.tile_size.width(), height)

    def helpEvent(self, event: QHelpEvent, view: QAbstractItemView, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        """Show tooltip with full title if text is truncated, or for UX consistency."""
        try:
            if not index.isValid() or event is None:
                return False
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            if not text:
                return super().helpEvent(event, view, option, index)

            try:
                max_lines = int(app_config.ui.get_tile_text_max_lines())
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug(
                    "Invalid max_lines config in helpEvent, fallback to 3: %s", e
                )
                max_lines = 3

            available_w = max(0, option.rect.width() - 2 * self.padding)

            font = QFont(option.font)  # font size is taken from QSS

            layout = QTextLayout(text, font)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.setTextOption(opt)
            layout.beginLayout()
            lines_count = 0
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_w)
                lines_count += 1
                if lines_count >= max_lines:
                    break
            layout.endLayout()

            from PyQt6.QtWidgets import QToolTip

            QToolTip.showText(event.globalPos(), text, view)
            return True
        except (RuntimeError, AttributeError, ValueError) as e:
            logger.warning("helpEvent failed, using default tooltip handling: %s", e)
            return super().helpEvent(event, view, option, index)
