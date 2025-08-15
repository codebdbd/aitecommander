# app/views/effects/neon_effect.py
from __future__ import annotations

from typing import Optional, Type

from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget,
    QGraphicsDropShadowEffect,
    QPushButton,
    QToolButton,
    QLineEdit,
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
    ) -> None:
        super().__init__(parent)
        self._color = color or QColor('#0194F0')
        self._blur = blur_radius
        self._x = x_offset
        self._y = y_offset

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        et = event.type()

        # Интересуют только кнопки и поле ввода
        if isinstance(watched, (QPushButton, QToolButton, QLineEdit)):
            # Наведение / фокус
            if et in (QEvent.Type.Enter, QEvent.Type.FocusIn):
                self._apply_effect(watched)
            # Уход курсора / потеря фокуса
            elif et in (QEvent.Type.Leave, QEvent.Type.FocusOut):
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
        if isinstance(w, (QPushButton, QToolButton, QLineEdit)):
            w.installEventFilter(self)
            self._maybe_connect_toggled(w)
            # Синхронизируем эффект с текущим состоянием checked
            if self._is_active_checked_button(w):
                self._apply_effect(w)
        # Рекурсивно обходим текущих потомков
        for child in w.findChildren(QWidget):
            if isinstance(child, (QPushButton, QToolButton, QLineEdit)):
                child.installEventFilter(self)
                self._maybe_connect_toggled(child)
                if self._is_active_checked_button(child):
                    self._apply_effect(child)

    def _maybe_connect_toggled(self, w: QWidget) -> None:
        try:
            if hasattr(w, 'toggled') and callable(getattr(w, 'toggled')):
                if not getattr(w, '_neon_toggled_connected', False):
                    w.toggled.connect(lambda checked, ww=w: self._on_toggled(ww, checked))
                    setattr(w, '_neon_toggled_connected', True)
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
        eff = getattr(w, '_neon_effect', None)
        if not isinstance(eff, QGraphicsDropShadowEffect):
            eff = QGraphicsDropShadowEffect(w)
            eff.setBlurRadius(self._blur)
            eff.setColor(self._color)
            eff.setOffset(self._x, self._y)
            setattr(w, '_neon_effect', eff)
        return eff

    def _apply_effect(self, w: QWidget) -> None:
        eff = self._ensure_effect(w)
        w.setGraphicsEffect(eff)
        eff.setEnabled(True)

    def _clear_effect(self, w: QWidget) -> None:
        eff = getattr(w, '_neon_effect', None)
        if isinstance(eff, QGraphicsDropShadowEffect):
            eff.setEnabled(False)
            # Эффект оставляем привязанным, чтобы не создавать его заново каждый раз

    def _is_active_checked_button(self, w: QWidget) -> bool:
        return isinstance(w, (QPushButton, QToolButton)) and getattr(w, 'isCheckable', lambda: False)() and getattr(w, 'isChecked', lambda: False)()
