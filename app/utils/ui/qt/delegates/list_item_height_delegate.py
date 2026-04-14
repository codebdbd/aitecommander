"""Delegate to enforce uniform 32px row height for QListWidget items."""

from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QStyledItemDelegate, QWidget


def _dpi_scale(widget: QWidget | None) -> float:
    """Calculate DPI scale factor for the given widget."""
    if widget is None:
        return 1.0
    try:
        wh = widget.window().windowHandle() if widget.window() else None
        screen = wh.screen() if wh else None
        if screen is not None:
            return max(1.0, screen.logicalDotsPerInch() / 96.0)
    except Exception:
        pass
    # Fallback
    try:
        return max(1.0, widget.logicalDpiY() / 96.0)
    except Exception:
        return 1.0


class ListItemHeightDelegate(QStyledItemDelegate):
    """Ensures QListWidget items use a 32px logical height scaled by DPI."""

    def sizeHint(self, option, index):  # noqa: N802 (Qt signature)
        """Return size hint with enforced 32px height."""
        size = super().sizeHint(option, index)
        scale = _dpi_scale(option.widget)
        target_h = int(round(32 * scale))
        # Preserve width from base, enforce target height
        return QSize(size.width(), target_h)
