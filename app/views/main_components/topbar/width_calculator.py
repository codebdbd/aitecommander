from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

from .panel_state import PanelState

logger = logging.getLogger(__name__)


class WidthCalculator:
    """Вычисляет ширины панелей и общий бюджет топбара.
    
    ИСПРАВЛЕНИЕ: Добавлены константы для магических чисел и кэширование результатов.
    """
    
    MIN_PANEL_WIDTH = 50  # Минимальная ширина панели в пикселях
    DEFAULT_BUTTON_SIZE = 32  # Размер кнопки по умолчанию
    CACHE_MAX_SIZE = 100  # Максимальный размер кэша

    def __init__(self, button_size: int = DEFAULT_BUTTON_SIZE):
        self._button_size = button_size
        # ИСПРАВЛЕНИЕ: LRU кэш для panel_width - ключ: (panel_id, count), значение: width
        # OrderedDict обеспечивает O(1) доступ и сохраняет порядок вставки для LRU
        self._panel_width_cache: OrderedDict[Tuple[int, int], int] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _safe_get(self, obj: Optional[Any], name: str) -> Optional[Any]:
        """Безопасное получение атрибута объекта.
        
        ИСПРАВЛЕНИЕ: Заменен object на Any для лучшей типизации.
        """
        if obj is None:
            return None
        try:
            return getattr(obj, name, None)
        except (RuntimeError, AttributeError):
            return None
    
    def _is_deleted(self, obj) -> bool:
        """Проверяет, удален ли Qt-объект."""
        try:
            from sip import isdeleted
            return isdeleted(obj)
        except ImportError:
            return False

    def clear_cache(self) -> None:
        """Очищает кэш вычислений ширины панелей.
        
        ИСПРАВЛЕНИЕ: Добавлен метод для принудительной очистки кэша.
        Вызывается при изменении конфигурации или размеров кнопок.
        """
        self._panel_width_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
    
    def invalidate_cache_for_panel(self, panel: QWidget) -> int:
        """Инвалидирует кэш для конкретной панели.
        
        УЛУЧШЕНИЕ: Селективная инвалидация кэша при изменении размеров
        конкретной панели (например, при изменении stylesheet).
        
        Args:
            panel: Виджет панели для инвалидации
            
        Returns:
            Количество удаленных записей из кэша
        """
        if not panel or self._is_deleted(panel):
            return 0
        
        panel_id = id(panel)
        keys_to_remove = [k for k in self._panel_width_cache if k[0] == panel_id]
        
        for key in keys_to_remove:
            del self._panel_width_cache[key]
        
        return len(keys_to_remove)
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Возвращает статистику использования кэша.
        
        Returns:
            Словарь с ключами: hits, misses, size, hit_rate
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._panel_width_cache),
            "hit_rate": int(hit_rate),
        }

    def panel_width(
        self, panel: Optional[QWidget], buttons: List[QToolButton], count: int
    ) -> int:
        """Вычисляет ширину панели на основе видимых кнопок.
        
        ИСПРАВЛЕНИЕ: Добавлена валидация параметров и кэширование результатов.
        
        Args:
            panel: Виджет панели
            buttons: Список кнопок панели (не должен быть None)
            count: Количество видимых кнопок (>= 0)
            
        Returns:
            Ширина панели в пикселях (>= MIN_PANEL_WIDTH)
            
        Raises:
            ValueError: Если count < 0
        """
        # ИСПРАВЛЕНИЕ: Валидация параметров
        if count < 0:
            raise ValueError(f"count must be >= 0, got {count}")
        
        if buttons is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("panel_width called with None buttons, returning MIN_PANEL_WIDTH")
            return self.MIN_PANEL_WIDTH
        
        if not panel or self._is_deleted(panel):
            return self.MIN_PANEL_WIDTH
        
        # ИСПРАВЛЕНИЕ: Проверяем LRU кэш
        cache_key = (id(panel), count)
        if cache_key in self._panel_width_cache:
            self._cache_hits += 1
            # ИСПРАВЛЕНИЕ: LRU - перемещаем в конец (most recently used)
            self._panel_width_cache.move_to_end(cache_key)
            return self._panel_width_cache[cache_key]
        
        self._cache_misses += 1
        
        # Clamp desired visible count to available buttons to avoid IndexError
        safe_count = max(0, min(count, len(buttons)))
        if safe_count <= 0:
            return self.MIN_PANEL_WIDTH
        # Используем layout, учитывая и дополнительные виджеты панели (которые не входят в 'buttons')
        bg = self._safe_get(panel, "bg_frame")
        layout = bg.layout() if bg else None
        if not layout:
            return self.MIN_PANEL_WIDTH
        spacing = layout.spacing() or 0

        # Быстрое множество целевых кнопок для панели (например, favoriteButton)
        btn_set = set(buttons or [])
        included_widths: List[int] = []
        taken_target = 0

        count_items = layout.count()
        for i in range(count_items):
            item = layout.itemAt(i)
            w = item.widget()
            if w is None:
                continue
            # Если это целевая кнопка панели — учитываем только первые 'safe_count'
            if w in btn_set:
                if taken_target >= safe_count:
                    continue
                taken_target += 1
                try:
                    hint_w = int(w.sizeHint().width())
                except (RuntimeError, AttributeError, ValueError):
                    hint_w = 0
                # Учитываем фиксированные ограничения кнопки, если заданы через setFixedSize
                try:
                    max_w = int(w.maximumWidth()) if w.maximumWidth() > 0 else 0
                except (RuntimeError, AttributeError, ValueError):
                    max_w = 0
                try:
                    min_w = int(w.minimumWidth()) if w.minimumWidth() > 0 else 0
                except (RuntimeError, AttributeError, ValueError):
                    min_w = 0
                btn_w = hint_w
                if max_w and min_w:
                    # setFixedSize устанавливает min==max==fixed; используем это как истину
                    btn_w = max(min_w, max_w)
                elif max_w:
                    btn_w = max(btn_w, max_w)
                elif min_w:
                    btn_w = max(btn_w, min_w)
                included_widths.append(max(self._button_size, btn_w))
            else:
                # Прочие виджеты панели (например, служебные кнопки) учитываем, если они видимы
                if w.isVisible():
                    try:
                        hint_w = int(w.sizeHint().width())
                    except (RuntimeError, AttributeError, ValueError):
                        hint_w = 0
                    included_widths.append(max(0, hint_w))

        if not included_widths:
            return self.MIN_PANEL_WIDTH

        total = sum(included_widths) + spacing * max(0, len(included_widths) - 1)

        # Добавляем внешние отступы layout, рамку QFrame(bg) и отступы панели
        try:
            lm = layout.contentsMargins()
            total += lm.left() + lm.right()
        except Exception:
            pass
        # Учёт рамки самого bg_frame (QFrame) — без повторного сложения его contentsMargins,
        # чтобы не дублировать отступы вместе с layout.contentsMargins.
        try:
            import PyQt6.QtWidgets as _qtw
            if isinstance(bg, _qtw.QFrame):
                try:
                    fw = int(bg.frameWidth())
                except Exception:
                    fw = 0
                total += max(0, fw * 2)
        except Exception:
            pass
        try:
            pm = panel.contentsMargins()
            total += pm.left() + pm.right()
        except Exception:
            pass

        # Enforce minimal width
        result = max(self.MIN_PANEL_WIDTH, total)
        
        # ИСПРАВЛЕНИЕ: LRU eviction - удаляем самый старый элемент при переполнении
        if len(self._panel_width_cache) >= self.CACHE_MAX_SIZE:
            # OrderedDict.popitem(last=False) удаляет первый (самый старый) элемент
            self._panel_width_cache.popitem(last=False)
        
        # Добавляем в конец (most recently used)
        self._panel_width_cache[cache_key] = result
        return result

    def total_width(
        self,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
        min_search_width: int,
    ) -> int:
        panel_map = {state.widget: state for state in panel_states if state.widget}
        items: List[int] = []
        for index in range(top_bar.count()):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget:
                if widget is search:
                    items.append(min_search_width)
                    continue
                state = panel_map.get(widget)
                if state:
                    requested = counts.get(state.definition.label, 0)
                    # Clamp to available buttons to keep estimation consistent with apply phase
                    visible = max(0, min(requested, len(state.buttons)))
                    items.append(self.panel_width(widget, state.buttons, visible))
                elif widget.isVisible():
                    items.append(widget.sizeHint().width())
            else:
                spacer = item.spacerItem()
                if spacer is not None:
                    items.append(max(0, spacer.sizeHint().width()))
        spacing = top_bar.spacing() or 0
        total = sum(items) + spacing * max(0, len(items) - 1)
        margins = top_bar.contentsMargins()
        total += margins.left() + margins.right()
        
        return total
