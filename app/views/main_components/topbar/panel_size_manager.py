"""Менеджер размеров панелей для устранения конфликтов."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PyQt6.QtWidgets import QSizePolicy, QToolButton, QWidget

from .constants import SizeConstraint, TopBarConstants
from .exceptions import SizeConstraintError

logger = logging.getLogger(__name__)


class PanelSizeManager:
    """Управляет размерами панелей, устраняя конфликты установки размеров."""
    
    def __init__(self, button_size: int = TopBarConstants.DEFAULT_BUTTON_SIZE):
        self._button_size = button_size
        self._size_constraints: Dict[QWidget, SizeConstraint] = {}
        self._applied_constraints: Dict[QWidget, SizeConstraint] = {}
    
    def set_panel_constraint(self, widget: QWidget, constraint: SizeConstraint) -> None:
        """Единственный способ изменения размеров панелей."""
        if not isinstance(widget, QWidget):
            raise SizeConstraintError(f"Expected QWidget, got {type(widget)}")
        
        # Проверяем, нужно ли обновление
        current = self._size_constraints.get(widget)
        if current == constraint:
            return
        
        self._size_constraints[widget] = constraint
        self._apply_constraint_safely(widget, constraint)
    
    def calculate_panel_constraint(
        self, 
        panel: Optional[QWidget], 
        buttons: List[QToolButton], 
        visible_count: int
    ) -> SizeConstraint:
        """Вычисляет ограничения размера для панели на основе видимых кнопок."""
        if not panel or not buttons or visible_count <= 0:
            return SizeConstraint(min_width=0, max_width=0, visible=False)
        
        visible_count = max(0, min(visible_count, len(buttons)))
        if visible_count == 0:
            return SizeConstraint(min_width=0, max_width=0, visible=False)
        
        width = self._calculate_panel_width(panel, buttons, visible_count)
        return SizeConstraint(min_width=width, max_width=width, visible=True)
    
    def _calculate_panel_width(
        self, 
        panel: QWidget, 
        buttons: List[QToolButton], 
        count: int
    ) -> int:
        """Вычисляет ширину панели для заданного количества кнопок."""
        if count <= 0:
            return 0
        
        # Получаем layout панели
        bg = getattr(panel, "bg_frame", None)
        layout = bg.layout() if bg else None
        spacing = layout.spacing() if layout else 0
        
        # Считаем ширину кнопок
        total = 0
        for index in range(min(count, len(buttons))):
            try:
                hint_width = int(buttons[index].sizeHint().width())
                width = max(self._button_size, hint_width)
            except (RuntimeError, TypeError, ValueError):
                width = self._button_size
            
            if index > 0:
                total += spacing
            total += width
        
        # Добавляем отступы layout'а
        if layout:
            margins = layout.contentsMargins()
            total += margins.left() + margins.right()
        
        # Добавляем отступы панели
        try:
            margins = panel.contentsMargins()
            total += margins.left() + margins.right()
        except (RuntimeError, AttributeError):
            pass
        
        return total
    
    def _apply_constraint_safely(self, widget: QWidget, constraint: SizeConstraint) -> None:
        """Безопасно применяет ограничения размера к виджету."""
        try:
            # Сначала устанавливаем видимость
            widget.setVisible(constraint.visible)
            
            if not constraint.visible:
                # Для невидимых панелей устанавливаем нулевые размеры
                widget.setFixedSize(0, widget.height())
                widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            else:
                # Для видимых панелей используем декларативный подход
                widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                widget.setMinimumWidth(constraint.min_width)
                widget.setMaximumWidth(constraint.max_width)
            
            self._applied_constraints[widget] = constraint
            
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"Failed to apply size constraint to panel: {e}")
        except Exception as e:
            logger.error(f"Unexpected error applying size constraint: {e}", exc_info=True)
    
    def get_current_constraint(self, widget: QWidget) -> Optional[SizeConstraint]:
        """Возвращает текущие ограничения для виджета."""
        return self._size_constraints.get(widget)
    
    def clear_constraints(self) -> None:
        """Очищает все ограничения размеров."""
        self._size_constraints.clear()
        self._applied_constraints.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """Возвращает статистику менеджера размеров."""
        return {
            "total_constraints": len(self._size_constraints),
            "applied_constraints": len(self._applied_constraints),
            "pending_constraints": len(self._size_constraints) - len(self._applied_constraints),
        }
