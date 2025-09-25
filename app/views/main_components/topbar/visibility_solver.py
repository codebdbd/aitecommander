from __future__ import annotations

import logging
from typing import Dict

from .layout_context import LayoutContext
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


class VisibilitySolver:
    """Подбирает оптимальное количество видимых кнопок для каждой панели."""

    def __init__(self, width_calculator: WidthCalculator) -> None:
        self._width_calculator = width_calculator
        self._last_solution: Dict[str, int] = {}
        self._solution_count = 0

    def compute_visible_counts(self, ctx: LayoutContext) -> Dict[str, int]:
        """Вычисляет оптимальное количество видимых кнопок для доступной ширины."""
        panel_states = list(ctx.panel_states)
        
        # Начинаем с максимальных значений
        counts: Dict[str, int] = {
            state.definition.label: state.max_visible for state in panel_states
        }
        minimums: Dict[str, int] = {
            state.definition.label: state.min_visible for state in panel_states
        }

        # Вычисляем максимальное количество шагов сокращения
        total_steps = sum(
            counts[label] - minimums[label] for label in counts if counts[label] > 0
        )
        
        steps = 0
        max_iterations = total_steps + 1  # Ограничиваем итерации
        
        # Постепенно сокращаем количество кнопок пока не поместимся
        while steps < max_iterations:
            try:
                total_width = self._width_calculator.total_width(
                    ctx.top_bar,
                    ctx.search,
                    panel_states,
                    counts,
                    ctx.min_search_width,
                )
                
                if total_width <= ctx.width:
                    break  # Поместились!
                    
            except Exception as e:
                logger.warning(f"Width calculation failed: {e}")
                # При ошибке возвращаем минимальные значения
                return minimums.copy()
            
            # Находим первую панель, которую можно сократить
            reduced = False
            for state in panel_states:
                label = state.definition.label
                if counts[label] > minimums[label]:
                    counts[label] -= 1
                    reduced = True
                    break
            
            if not reduced:
                break  # Нечего больше сокращать
            
            steps += 1

        # Проверяем финальный результат
        try:
            final_width = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            
            # Если всё ещё не помещается, сводим к минимуму
            if final_width > ctx.width:
                counts = minimums.copy()
                
        except Exception as e:
            logger.warning(f"Final width check failed: {e}")
            counts = minimums.copy()

        self._last_solution = counts.copy()
        self._solution_count += 1
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"VisibilitySolver solution #{self._solution_count}: {counts} "
                f"(steps: {steps}, width: {ctx.width})"
            )
        
        return counts
    
    def get_stats(self) -> Dict[str, int]:
        """Возвращает статистику решателя видимости."""
        return {
            "solution_count": self._solution_count,
            "last_solution": self._last_solution,
        }
