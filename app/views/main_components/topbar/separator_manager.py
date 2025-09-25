"""Менеджер разделителей для упрощения сложной логики видимости."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy, QWidget

from .constants import SeparatorInfo, TopBarConstants

logger = logging.getLogger(__name__)


class SeparatorManager:
    """Управляет видимостью разделителей и spacer'ов в topbar."""
    
    def __init__(self):
        self._panel_attr_map = {
            "recent_links_widget": "recent",
            "fav_widget": "fav", 
            "quick_add_widget": "quick",
        }
    
    def update_separators(
        self, 
        top_bar: QLayout, 
        applied_counts: Dict[str, int], 
        has_search: bool,
        window: object
    ) -> None:
        """Обновляет видимость всех разделителей в layout."""
        try:
            separators = self._find_separators(top_bar)
            for sep_info in separators:
                should_show = self._should_show_separator(
                    sep_info, applied_counts, has_search, window
                )
                self._apply_separator_visibility(sep_info, should_show)
        except Exception as e:
            logger.error(f"Failed to update separators: {e}", exc_info=True)
    
    def _find_separators(self, top_bar: QLayout) -> List[SeparatorInfo]:
        """Находит все разделители в layout и собирает информацию о них."""
        separators: List[SeparatorInfo] = []
        count = top_bar.count()
        
        for index in range(count):
            item = top_bar.itemAt(index)
            widget = item.widget()
            
            if widget is None or widget.objectName() != "vSeparator":
                continue
            
            # Находим соседние виджеты
            left_widget = self._find_adjacent_widget(top_bar, index, -1)
            right_widget = self._find_adjacent_widget(top_bar, index, 1)
            
            # Находим соседние spacer'ы
            left_spacer = self._find_adjacent_spacer(top_bar, index, -1)
            right_spacer = self._find_adjacent_spacer(top_bar, index, 1)
            
            separators.append(SeparatorInfo(
                index=index,
                widget=widget,
                left_widget=left_widget,
                right_widget=right_widget,
                left_spacer=left_spacer,
                right_spacer=right_spacer
            ))
        
        return separators
    
    def _find_adjacent_widget(self, top_bar: QLayout, index: int, direction: int) -> Optional[QWidget]:
        """Находит ближайший виджет в указанном направлении."""
        count = top_bar.count()
        current = index + direction
        
        while 0 <= current < count:
            item = top_bar.itemAt(current)
            widget = item.widget()
            if widget is not None:
                return widget
            current += direction
        
        return None
    
    def _find_adjacent_spacer(self, top_bar: QLayout, index: int, direction: int) -> Optional[object]:
        """Находит ближайший spacer в указанном направлении."""
        target_index = index + direction
        if 0 <= target_index < top_bar.count():
            item = top_bar.itemAt(target_index)
            return item.spacerItem()
        return None
    
    def _should_show_separator(
        self, 
        sep_info: SeparatorInfo, 
        applied_counts: Dict[str, int], 
        has_search: bool,
        window: object
    ) -> bool:
        """Определяет, должен ли разделитель быть видимым."""
        left_visible = self._is_panel_logically_visible(
            sep_info.left_widget, applied_counts, window
        )
        right_visible = (
            self._is_panel_logically_visible(sep_info.right_widget, applied_counts, window)
            or (has_search and isinstance(sep_info.right_widget, QLineEdit))
        )
        
        return left_visible and right_visible
    
    def _is_panel_logically_visible(
        self, 
        widget: Optional[QWidget], 
        applied_counts: Dict[str, int],
        window: object
    ) -> bool:
        """Проверяет, логически ли видима панель."""
        if not widget:
            return False
        
        # Проверяем физическую видимость
        try:
            if not widget.isVisible():
                return False
        except (RuntimeError, AttributeError):
            return False
        
        # Проверяем логическую видимость через applied_counts
        for attr_name, state_label in self._panel_attr_map.items():
            try:
                panel_widget = getattr(window, attr_name, None)
                if widget is panel_widget:
                    return applied_counts.get(state_label, 0) > 0
            except (RuntimeError, AttributeError):
                continue
        
        return True  # Для неизвестных виджетов считаем видимыми
    
    def _apply_separator_visibility(self, sep_info: SeparatorInfo, visible: bool) -> None:
        """Применяет видимость разделителя и управляет spacer'ами."""
        try:
            # Устанавливаем видимость разделителя
            sep_info.widget.setVisible(visible)
            
            # Управляем spacer'ами
            if visible:
                self._set_spacer_size(sep_info.left_spacer, TopBarConstants.DEFAULT_SPACER_SIZE)
                self._set_spacer_size(sep_info.right_spacer, TopBarConstants.DEFAULT_SPACER_SIZE)
            else:
                # При скрытом разделителе управляем отступами
                is_search_right = isinstance(sep_info.right_widget, QLineEdit)
                
                left_size = 0 if is_search_right else TopBarConstants.DEFAULT_SPACER_SIZE
                right_size = TopBarConstants.DEFAULT_SPACER_SIZE if is_search_right else 0
                
                self._set_spacer_size(sep_info.left_spacer, left_size)
                self._set_spacer_size(sep_info.right_spacer, right_size)
                
        except Exception as e:
            logger.warning(f"Failed to apply separator visibility: {e}")
    
    def _set_spacer_size(self, spacer: Optional[object], size: int) -> None:
        """Безопасно устанавливает размер spacer'а."""
        if spacer is None:
            return
        
        try:
            spacer.changeSize(
                size, 0,
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed
            )
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Failed to change spacer size: {e}")
