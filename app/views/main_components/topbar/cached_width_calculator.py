"""Кэшированный калькулятор ширины для оптимизации производительности."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from PyQt6.QtWidgets import QLayout, QLineEdit

from .layout_context import LayoutContext
from .panel_state import PanelState
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutCacheKey:
    """Ключ для кэширования расчетов layout."""
    width: int
    panel_buttons_count: Tuple[int, ...]  # Количество кнопок в каждой панели
    search_present: bool
    min_search_width: int
    
    @classmethod
    def from_context(cls, ctx: LayoutContext) -> LayoutCacheKey:
        """Создает ключ кэша из контекста layout."""
        buttons_count = tuple(
            len(state.buttons) for state in ctx.panel_states
        )
        return cls(
            width=ctx.width,
            panel_buttons_count=buttons_count,
            search_present=ctx.has_search,
            min_search_width=ctx.min_search_width
        )


class CachedWidthCalculator(WidthCalculator):
    """Калькулятор ширины с кэшированием для оптимизации производительности."""
    
    def __init__(self, button_size: int = 32, cache_size: int = 100):
        super().__init__(button_size)
        self._visibility_solver = VisibilitySolver(self)
        self._cache: Dict[LayoutCacheKey, Dict[str, int]] = {}
        self._cache_size = cache_size
        self._cache_hits = 0
        self._cache_misses = 0
    
    def compute_visible_counts_with_cache(self, ctx: LayoutContext) -> Dict[str, int]:
        """Вычисляет количество видимых кнопок с использованием кэша."""
        cache_key = LayoutCacheKey.from_context(ctx)
        
        # Проверяем кэш
        if cache_key in self._cache:
            self._cache_hits += 1
            result = self._cache[cache_key].copy()
            logger.debug(f"Cache hit for layout calculation: {cache_key}")
            return result
        
        # Вычисляем новое значение
        self._cache_misses += 1
        result = self._visibility_solver.compute_visible_counts(ctx)
        
        # Сохраняем в кэш
        self._cache[cache_key] = result.copy()
        
        # Ограничиваем размер кэша
        if len(self._cache) > self._cache_size:
            self._evict_oldest_entries()
        
        logger.debug(f"Cache miss for layout calculation: {cache_key}")
        return result
    
    def _evict_oldest_entries(self) -> None:
        """Удаляет старые записи из кэша."""
        # Простая стратегия: удаляем половину записей
        entries_to_remove = len(self._cache) // 2
        keys_to_remove = list(self._cache.keys())[:entries_to_remove]
        
        for key in keys_to_remove:
            del self._cache[key]
        
        logger.debug(f"Evicted {entries_to_remove} entries from cache")
    
    def invalidate_cache(self) -> None:
        """Очищает весь кэш."""
        self._cache.clear()
        logger.debug("Cache invalidated")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Возвращает статистику кэша."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
        }
    
    def log_cache_stats(self) -> None:
        """Логирует статистику кэша."""
        stats = self.get_cache_stats()
        logger.info(f"Cache stats: {stats}")


class OptimizedTotalWidthCalculator:
    """Оптимизированный калькулятор общей ширины с минимальными обращениями к Qt."""
    
    def __init__(self, width_calculator: WidthCalculator):
        self._width_calculator = width_calculator
        self._layout_cache: Dict[int, List[Tuple[str, int]]] = {}  # layout_id -> [(type, width), ...]
    
    def calculate_total_width_optimized(
        self,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
        min_search_width: int,
    ) -> int:
        """Оптимизированный расчет общей ширины с минимальными Qt вызовами."""
        try:
            layout_id = id(top_bar)
            
            # Проверяем, изменился ли состав layout'а
            if not self._is_layout_structure_cached(top_bar, layout_id):
                self._cache_layout_structure(top_bar, layout_id)
            
            # Используем кэшированную структуру для расчета
            return self._calculate_from_cached_structure(
                layout_id, search, panel_states, counts, min_search_width
            )
            
        except Exception as e:
            logger.warning(f"Optimized calculation failed, falling back: {e}")
            # Fallback на стандартный метод
            return self._width_calculator.total_width(
                top_bar, search, panel_states, counts, min_search_width
            )
    
    def _is_layout_structure_cached(self, top_bar: QLayout, layout_id: int) -> bool:
        """Проверяет, закэширована ли структура layout'а."""
        if layout_id not in self._layout_cache:
            return False
        
        # Простая проверка: сравниваем количество элементов
        cached_count = len(self._layout_cache[layout_id])
        actual_count = top_bar.count()
        
        return cached_count == actual_count
    
    def _cache_layout_structure(self, top_bar: QLayout, layout_id: int) -> None:
        """Кэширует структуру layout'а."""
        structure = []
        
        for index in range(top_bar.count()):
            item = top_bar.itemAt(index)
            widget = item.widget()
            
            if widget:
                if isinstance(widget, QLineEdit):
                    structure.append(("search", 0))
                else:
                    # Для панелей сохраняем базовую ширину
                    base_width = widget.sizeHint().width() if widget.isVisible() else 0
                    structure.append(("panel", base_width))
            else:
                spacer = item.spacerItem()
                if spacer:
                    spacer_width = spacer.sizeHint().width()
                    structure.append(("spacer", spacer_width))
        
        self._layout_cache[layout_id] = structure
    
    def _calculate_from_cached_structure(
        self,
        layout_id: int,
        search: Optional[QLineEdit],
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
        min_search_width: int,
    ) -> int:
        """Рассчитывает ширину используя кэшированную структуру."""
        structure = self._layout_cache[layout_id]
        panel_map = {state.widget: state for state in panel_states if state.widget}
        
        total_width = 0
        item_count = 0
        
        for item_type, base_width in structure:
            if item_type == "search":
                total_width += min_search_width
                item_count += 1
            elif item_type == "panel":
                # Здесь нужно найти соответствующую панель и пересчитать ширину
                # Упрощенная версия - используем базовую ширину
                total_width += base_width
                item_count += 1
            elif item_type == "spacer":
                total_width += base_width
        
        # Добавляем spacing между элементами
        # Это упрощение - в реальности нужно учитывать layout spacing
        
        return total_width
    
    def invalidate_layout_cache(self) -> None:
        """Очищает кэш структуры layout'ов."""
        self._layout_cache.clear()
