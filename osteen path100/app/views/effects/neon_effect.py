# app/views/effects/neon_effect.py
from __future__ import annotations

from typing import Optional

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


class NeonEventFilter(QObject):
    """
    Универсальный eventFilter, добавляющий/убирающий неоновое свечение
    (QGraphicsDropShadowEffect) при hover/focus для кнопок и полей ввода.

    Использование:
      filt = NeonEventFilter(color=QColor('#0194F0'), blur_radius=18)
      widget.installEventFilter(filt)
    или установить на контейнер, тогда фильтр будет работать и на его дочерних виджетах.
    """

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        color: QColor | None = None,
        blur_radius: int = 18,
        x_offset: int = 0,
        y_offset: int = 0,
        outline_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._color = color or QColor("#0194F0")
        self._blur = blur_radius
        self._x = x_offset
        self._y = y_offset
        self._outline_only = outline_only

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        et = event.type()

        # Интересуют кнопки, поля ввода и представления списков/таблиц
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
            # Наведение / фокус (включая hover события)
            if et in (
                QEvent.Type.Enter,
                QEvent.Type.FocusIn,
                QEvent.Type.HoverEnter,
                QEvent.Type.HoverMove,
            ):
                self._apply_effect(watched)
            # Уход курсора / потеря фокуса (включая hover leave)
            elif et in (
                QEvent.Type.Leave,
                QEvent.Type.FocusOut,
                QEvent.Type.HoverLeave,
            ):
                # Для checkable-активных кнопок оставляем свечение
                if self._is_active_checked_button(watched):
                    self._apply_effect(watched)
                else:
                    self._clear_effect(watched)

        # Если фильтр поставлен на контейнер, автоматически навешиваем фильтр
        # на добавленных дочерних виджетов подходящих типов
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
            self._maybe_connect_toggled(w)
            # Синхронизируем эффект с текущим состоянием checked
            if self._is_active_checked_button(w):
                self._apply_effect(w)
        # Рекурсивно обходим текущих потомков
        for child in w.findChildren(QWidget):
            if isinstance(child, eligible):
                child.installEventFilter(self)
                self._maybe_connect_toggled(child)
                if self._is_active_checked_button(child):
                    self._apply_effect(child)

    def _maybe_connect_toggled(self, w: QWidget) -> None:
        try:
            if hasattr(w, "toggled") and callable(getattr(w, "toggled")):
                if not getattr(w, "_neon_toggled_connected", False):
                    w.toggled.connect(
                        lambda checked, ww=w: self._on_toggled(ww, checked)
                    )
                    setattr(w, "_neon_toggled_connected", True)
        except Exception:
            pass

    def _on_toggled(self, w: QWidget, checked: bool) -> None:
        if checked:
            self._apply_effect(w)
        else:
            # если виджет под курсором или в фокусе — эффект останется активным из-за Enter/FocusIn
            # иначе выключаем
            self._clear_effect(w)

    def _ensure_effect(self, w: QWidget) -> QGraphicsDropShadowEffect:
        eff = getattr(w, "_neon_effect", None)
        if not isinstance(eff, QGraphicsDropShadowEffect):
            eff = QGraphicsDropShadowEffect(w)
            eff.setBlurRadius(self._blur)
            eff.setColor(self._color)
            eff.setOffset(self._x, self._y)
            setattr(w, "_neon_effect", eff)
        return eff

    def _apply_effect(self, w: QWidget) -> None:
        # В режиме outline_only настоящий неон используем ТОЛЬКО для выбранной (checked) кнопки
        if self._outline_only and not self._is_active_checked_button(w):
            # В режиме только обводки не используем графический эффект —
            # переключаем динамическое свойство для QSS.
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
            # Эффект оставляем привязанным, чтобы не создавать его заново каждый раз

    def _is_active_checked_button(self, w: QWidget) -> bool:
        return (
            isinstance(w, (QPushButton, QToolButton))
            and getattr(w, "isCheckable", lambda: False)()
            and getattr(w, "isChecked", lambda: False)()
        )
