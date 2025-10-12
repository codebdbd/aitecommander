# app/views/effects/neon_effect.py
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDoubleSpinBox,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QTimeEdit,
    QToolButton,
    QWidget,
)

# Constants
DEFAULT_NEON_COLOR = "#0194F0"  # Default neon glow color
DEFAULT_BLUR_RADIUS = 18  # Glow blur radius


class NeonEventFilter(QObject):
    """
    Universal eventFilter that adds/removes neon glow
    (QGraphicsDropShadowEffect) on hover/focus for buttons and input fields.

    Usage:
      filt = NeonEventFilter(color=QColor('#0194F0'), blur_radius=18)
      widget.installEventFilter(filt)
    Or install it on a container to affect eligible child widgets as well.
    """

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        color: QColor | None = None,
        blur_radius: int = 18,
        x_offset: int = 0,
        y_offset: int = 0,
        outline_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._color = color or QColor(DEFAULT_NEON_COLOR)
        self._blur = blur_radius
        self._x = x_offset
        self._y = y_offset
        self._outline_only = outline_only
        self._tracked_widgets: list[QWidget] = []  # Track widgets for cleanup

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        et = event.type()

        # Handle buttons, input fields, and list/table views
        if isinstance(
            watched,
            (
                QPushButton,
                QToolButton,
                QLineEdit,
                QTextEdit,
                QPlainTextEdit,
                QComboBox,
                QSpinBox,
                QDoubleSpinBox,
                QDateEdit,
                QTimeEdit,
                QDateTimeEdit,
                QAbstractItemView,
            ),
        ):
            # Enter/focus (including hover events)
            if et in (
                QEvent.Type.Enter,
                QEvent.Type.FocusIn,
                QEvent.Type.HoverEnter,
                QEvent.Type.HoverMove,
            ):
                self._apply_effect(watched)
            # Leave/lose focus (including hover leave)
            elif et in (
                QEvent.Type.Leave,
                QEvent.Type.FocusOut,
                QEvent.Type.HoverLeave,
            ):
                # Keep glow for active checkable buttons
                if self._is_active_checked_button(watched):
                    self._apply_effect(watched)
                else:
                    self._clear_effect(watched)

        # If installed on a container, automatically attach to newly added
        # eligible child widgets
        if et == QEvent.Type.ChildAdded:
            try:
                child = event.child()
                if isinstance(child, QWidget):
                    self._attach_to_tree(child)
            except Exception:
                pass

        return super().eventFilter(watched, event)

    # ---- helpers ---------------------------------------------------------
    def _attach_to_tree(self, w: QWidget) -> None:
        eligible = (
            QPushButton,
            QToolButton,
            QLineEdit,
            QTextEdit,
            QPlainTextEdit,
            QComboBox,
            QSpinBox,
            QDoubleSpinBox,
            QDateEdit,
            QTimeEdit,
            QDateTimeEdit,
            QAbstractItemView,
        )
        if isinstance(w, eligible):
            w.installEventFilter(self)
            self._tracked_widgets.append(w)  # Track
            self._maybe_connect_toggled(w)
            # Sync effect with current checked state
            if self._is_active_checked_button(w):
                self._apply_effect(w)
        for child in w.findChildren(QWidget):
            if isinstance(child, eligible):
                child.installEventFilter(self)
                self._tracked_widgets.append(child)  # Track
                self._maybe_connect_toggled(child)
                if self._is_active_checked_button(child):
                    self._apply_effect(child)

    def _maybe_connect_toggled(self, w: QWidget) -> None:
        try:
            if hasattr(w, "toggled") and callable(w.toggled):
                if not getattr(w, "_neon_toggled_connected", False):
                    w.toggled.connect(
                        lambda checked, ww=w: self._on_toggled(ww, checked)
                    )
                    w._neon_toggled_connected = True
        except Exception:
            pass

    def _on_toggled(self, w: QWidget, checked: bool) -> None:
        if checked:
            self._apply_effect(w)
        else:
            # If the widget is hovered/focused, the effect remains due to Enter/FocusIn;
            # otherwise, turn it off
            self._clear_effect(w)

    def _ensure_effect(self, w: QWidget) -> QGraphicsDropShadowEffect:
        eff = getattr(w, "_neon_effect", None)
        if not isinstance(eff, QGraphicsDropShadowEffect):
            eff = QGraphicsDropShadowEffect(w)
            eff.setBlurRadius(self._blur)
            eff.setColor(self._color)
            eff.setOffset(self._x, self._y)
            w._neon_effect = eff
        return eff

    def _apply_effect(self, w: QWidget) -> None:
        # In outline_only mode, use real neon ONLY for the selected (checked) button
        if self._outline_only and not self._is_active_checked_button(w):
            # In outline-only mode do not use the graphics effect — switch
            # a dynamic property for QSS instead.
            try:
                w.setProperty("_neon_on", True)
                st = w.style()
                if st is not None:
                    st.unpolish(w)
                    st.polish(w)
                w.update()
            except Exception:
                pass
            return
        eff = self._ensure_effect(w)
        w.setGraphicsEffect(eff)
        eff.setEnabled(True)

    def _clear_effect(self, w: QWidget) -> None:
        if self._outline_only and not self._is_active_checked_button(w):
            try:
                w.setProperty("_neon_on", False)
                st = w.style()
                if st is not None:
                    st.unpolish(w)
                    st.polish(w)
                w.update()
            except Exception:
                pass
            return
        eff = getattr(w, "_neon_effect", None)
        if isinstance(eff, QGraphicsDropShadowEffect):
            eff.setEnabled(False)
            # Keep the effect instance to avoid recreating it every time

    def _is_active_checked_button(self, w: QWidget) -> bool:
        return (
            isinstance(w, (QPushButton, QToolButton))
            and getattr(w, "isCheckable", lambda: False)()
            and getattr(w, "isChecked", lambda: False)()
        )

    def cleanup(self) -> None:
        """Remove all event filters and disconnect signals.

        Call this method before deleting the filter to prevent memory leaks.
        """
        for widget in self._tracked_widgets:
            try:
                widget.removeEventFilter(self)
                # Disconnect from toggled if connected
                if hasattr(widget, "toggled") and getattr(
                    widget, "_neon_toggled_connected", False
                ):
                    widget.toggled.disconnect()
            except (RuntimeError, TypeError):
                # Widget already deleted
                pass
        self._tracked_widgets.clear()

    def __del__(self):
        """Automatic cleanup on deletion."""
        try:
            self.cleanup()
        except Exception:
            pass
