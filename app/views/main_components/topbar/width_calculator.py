from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

from .constants import TopBarConstants
from .panel_state import PanelState

logger = logging.getLogger(__name__)


class WidthCalculator:
    """Базовый калькулятор ширины панелей и общего бюджета topbar."""

    def __init__(self, button_size: int = TopBarConstants.DEFAULT_BUTTON_SIZE):
        self._button_size = button_size
        self._calculation_count = 0
    
    def _safe_get(self, obj: Optional[object], name: str) -> Optional[object]:
        if obj is None:
            return None
        try:
            return getattr(obj, name, None)
        except (RuntimeError, AttributeError):
            return None

    def panel_width(
        self, panel: Optional[QWidget], buttons: List[QToolButton], count: int
    ) -> int:
        """Вычисляет ширину панели для заданного количества кнопок."""
        if not panel or not buttons or count <= 0:
            return 0
        
        try:
            return self._calculate_panel_width_safe(panel, buttons, count)
        except Exception as e:
            logger.warning(f"Panel width calculation failed: {e}")
            # Fallback: простой расчет
            return count * self._button_size
    
    def _calculate_panel_width_safe(
        self, panel: QWidget, buttons: List[QToolButton], count: int
    ) -> int:
        """Безопасный расчет ширины панели."""
        # Получаем layout панели
        bg = self._safe_get(panel, "bg_frame")
        layout = bg.layout() if bg else None
        spacing = layout.spacing() if layout else 0
        
        # Считаем ширину кнопок
        total = 0
        actual_count = min(count, len(buttons))
        
        for index in range(actual_count):
            try:
                button = buttons[index]
                hint_width = int(button.sizeHint().width())
                width = max(self._button_size, hint_width)
            except (RuntimeError, TypeError, ValueError, IndexError):
                width = self._button_size
            
            if index > 0:
                total += spacing
            total += width
        
        # Добавляем отступы layout'а
        if layout:
            try:
                margins = layout.contentsMargins()
                total += margins.left() + margins.right()
            except (RuntimeError, AttributeError):
                pass
        
        # Добавляем отступы панели
        try:
            margins = panel.contentsMargins()
            total += margins.left() + margins.right()
        except (RuntimeError, AttributeError):
            pass
        
        return total

    def total_width(
        self,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
        min_search_width: int,
    ) -> int:
        """Вычисляет общую ширину topbar для заданных количеств кнопок."""
        self._calculation_count += 1
        
        try:
            return self._calculate_total_width_safe(
                top_bar, search, panel_states, counts, min_search_width
            )
        except Exception as e:
            logger.error(f"Total width calculation failed: {e}", exc_info=True)
            # Fallback: примерная оценка
            return self._estimate_total_width(panel_states, counts, min_search_width)
    
    def _calculate_total_width_safe(
        self,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
        min_search_width: int,
    ) -> int:
        """Безопасный расчет общей ширины."""
        panel_map = {state.widget: state for state in panel_states if state.widget}
        items: List[int] = []
        
        # Проходим по всем элементам layout'а
        for index in range(top_bar.count()):
            try:
                item = top_bar.itemAt(index)
                if not item:
                    continue
                    
                widget = item.widget()
                if widget:
                    if widget is search:
                        items.append(min_search_width)
                        continue
                    
                    # Проверяем, является ли это одной из наших панелей
                    state = panel_map.get(widget)
                    if state:
                        visible = counts.get(state.definition.label, 0)
                        panel_width = self.panel_width(widget, state.buttons, visible)
                        items.append(panel_width)
                    elif widget.isVisible():
                        # Обычный виджет (например, разделитель)
                        try:
                            width = widget.sizeHint().width()
                            items.append(max(0, width))
                        except (RuntimeError, AttributeError):
                            items.append(0)
                else:
                    # Spacer элемент
                    spacer = item.spacerItem()
                    if spacer:
                        try:
                            width = spacer.sizeHint().width()
                            items.append(max(0, width))
                        except (RuntimeError, AttributeError):
                            items.append(0)
                            
            except (RuntimeError, AttributeError) as e:
                logger.debug(f"Failed to process layout item {index}: {e}")
                continue
        
        # Вычисляем итоговую ширину
        spacing = top_bar.spacing() or 0
        total = sum(items)
        
        # Добавляем spacing между элементами
        if len(items) > 1:
            total += spacing * (len(items) - 1)
        
        # Добавляем отступы layout'а
        try:
            margins = top_bar.contentsMargins()
            total += margins.left() + margins.right()
        except (RuntimeError, AttributeError):
            pass
        
        return total
    
    def _estimate_total_width(
        self, panel_states: Iterable[PanelState], counts: Dict[str, int], min_search_width: int
    ) -> int:
        """Примерная оценка общей ширины при ошибке."""
        total = min_search_width  # Поле поиска
        
        for state in panel_states:
            visible = counts.get(state.definition.label, 0)
            if visible > 0:
                # Примерная оценка: количество кнопок * размер кнопки + отступы
                total += visible * self._button_size + 20  # 20px на отступы
        
        return total
    
    def get_stats(self) -> Dict[str, int]:
        """Возвращает статистику калькулятора."""
        return {
            "calculation_count": self._calculation_count,
            "button_size": self._button_size,
        }
