from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QStyledItemDelegate, QWidget


def _dpi_scale(widget: QWidget) -> float:
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


class ComboRowHeightDelegate(QStyledItemDelegate):
    """Ensures combo popup items use a 32px logical height scaled by DPI."""

    def sizeHint(self, option, index):  # noqa: N802 (Qt signature)
        size = super().sizeHint(option, index)
        scale = _dpi_scale(option.widget or QWidget())
        target_h = int(round(32 * scale))
        # Preserve width from base, enforce target height
        return QSize(size.width(), target_h)
