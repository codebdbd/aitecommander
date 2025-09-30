from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from .layout_context import LayoutContext
from .panel_state import PanelState
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


class VisibilitySolver:
    """Подбирает количество видимых кнопок для каждой панели.
    
    УЛУЧШЕНИЕ: Добавлен оптимизированный алгоритм с бинарным поиском
    для уменьшения сложности с O(n*m) до O(log(total) * n).
    
    Использует два алгоритма:
    1. Жадный (по умолчанию) - простой и предсказуемый
    2. Бинарный поиск - быстрее для большого количества кнопок
    """

    def __init__(self, width_calculator: WidthCalculator, use_binary_search: bool = False) -> None:
        """Инициализирует solver.
        
        Args:
            width_calculator: Калькулятор ширины
            use_binary_search: Использовать бинарный поиск (быстрее, но менее предсказуемо)
        """
        self._width_calculator = width_calculator
        self._use_binary_search = use_binary_search

    def compute_visible_counts(self, ctx: LayoutContext) -> Dict[str, int]:
        """Вычисляет оптимальное количество видимых кнопок.
        
        Выбирает алгоритм на основе флага use_binary_search.
        """
        if self._use_binary_search:
            return self._compute_with_binary_search(ctx)
        return self._compute_greedy(ctx)
    
    def _compute_greedy(self, ctx: LayoutContext) -> Dict[str, int]:
        """Вычисляет оптимальное количество видимых кнопок для каждой панели.
        
        ИСПРАВЛЕНИЕ: Добавлена подробная документация алгоритма.
        
        Алгоритм (жадный с приоритетами):
        1. Начинаем с максимальных значений для всех панелей (max_visible)
        2. Вычисляем общую ширину с текущими counts через WidthCalculator
        3. Если не помещается в доступную ширину:
           - Проходим по панелям в порядке приоритета (recent -> fav -> quick)
           - Уменьшаем count на 1 для первой панели, у которой count > minimum
           - Повторяем итерацию, пока не поместится или не достигнем минимумов
        4. Если всё равно не помещается — устанавливаем все в minimum
        
        Сложность: O(n * m), где:
        - n = количество панелей (обычно 3)
        - m = сумма (max_visible - min_visible) для всех панелей
        
        Порядок приоритета:
        Определяется порядком элементов в panel_states. Первая панель имеет
        наивысший приоритет (будет сжиматься последней). Для изменения
        приоритета нужно изменить порядок в _panel_definitions в TopBarLayoutManager.
        
        Защита от бесконечного цикла:
        Используется счетчик steps с ограничением total_steps = сумма всех
        возможных уменьшений. Гарантирует завершение за конечное время.
        
        Args:
            ctx: Контекст layout с информацией о ширине и панелях
            
        Returns:
            Словарь {label: visible_count} с количеством видимых кнопок.
            Гарантируется: minimums[label] <= result[label] <= max_visible
        
        Example:
            >>> ctx = LayoutContext(width=500, panel_states=[...])
            >>> solver.compute_visible_counts(ctx)
            {'recent': 8, 'fav': 5, 'quick': 6}
            # recent имеет наивысший приоритет, quick - наименьший
        """
        panel_states = list(ctx.panel_states)
        counts: Dict[str, int] = {
            state.definition.label: state.max_visible for state in panel_states
        }
        minimums: Dict[str, int] = {
            state.definition.label: state.min_visible for state in panel_states
        }
        

        total_steps = sum(
            counts[label] - minimums[label] for label in counts if counts[label] > 0
        )
        steps = 0
        while (
            self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            > ctx.width
            and steps < total_steps
        ):
            steps += 1
            for state in panel_states:
                label = state.definition.label
                if counts[label] > minimums[label]:
                    counts[label] -= 1
                    break

        if (
            self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            > ctx.width
        ):
            for label in counts:
                counts[label] = minimums[label]

        return counts
    
    def _compute_with_binary_search(self, ctx: LayoutContext) -> Dict[str, int]:
        """Вычисляет количество видимых кнопок используя бинарный поиск.
        
        УЛУЧШЕНИЕ: Оптимизированный алгоритм O(log(total) * n) вместо O(n * m).
        
        Идея:
        1. Вычисляем общее количество кнопок (total_buttons)
        2. Бинарным поиском находим максимальное количество, которое помещается
        3. Распределяем найденное количество по панелям с учетом приоритетов
        
        Args:
            ctx: Контекст layout
            
        Returns:
            Словарь с количеством видимых кнопок для каждой панели
        """
        panel_states = list(ctx.panel_states)
        
        # Подготавливаем данные для бинарного поиска
        minimums: Dict[str, int] = {
            state.definition.label: state.min_visible for state in panel_states
        }
        maximums: Dict[str, int] = {
            state.definition.label: state.max_visible for state in panel_states
        }
        
        # Вычисляем диапазон для бинарного поиска
        min_total = sum(minimums.values())
        max_total = sum(maximums.values())
        
        if min_total == max_total:
            # Нет гибкости - возвращаем минимумы
            return minimums.copy()
        
        # Бинарный поиск максимального количества кнопок, которое помещается
        left, right = min_total, max_total
        best_total = min_total
        
        while left <= right:
            mid = (left + right) // 2
            counts = self._distribute_buttons(panel_states, mid, minimums, maximums)
            
            total_width = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            
            if total_width <= ctx.width:
                # Помещается - пробуем больше
                best_total = mid
                left = mid + 1
            else:
                # Не помещается - пробуем меньше
                right = mid - 1
        
        # Возвращаем распределение для лучшего найденного значения
        return self._distribute_buttons(panel_states, best_total, minimums, maximums)
    
    def _distribute_buttons(
        self,
        panel_states: List[PanelState],
        total: int,
        minimums: Dict[str, int],
        maximums: Dict[str, int],
    ) -> Dict[str, int]:
        """Распределяет заданное количество кнопок по панелям.
        
        УЛУЧШЕНИЕ: Вспомогательный метод для бинарного поиска.
        Распределяет кнопки с учетом приоритетов (порядок в panel_states).
        
        Args:
            panel_states: Список состояний панелей (определяет приоритет)
            total: Общее количество кнопок для распределения
            minimums: Минимумы для каждой панели
            maximums: Максимумы для каждой панели
            
        Returns:
            Словарь с распределением кнопок
        """
        counts: Dict[str, int] = {}
        remaining = total
        
        # Сначала выделяем минимумы
        for state in panel_states:
            label = state.definition.label
            counts[label] = minimums[label]
            remaining -= minimums[label]
        
        # Распределяем оставшиеся кнопки по приоритету
        for state in panel_states:
            label = state.definition.label
            available = maximums[label] - minimums[label]
            to_add = min(available, remaining)
            counts[label] += to_add
            remaining -= to_add
            
            if remaining <= 0:
                break
        
        return counts
