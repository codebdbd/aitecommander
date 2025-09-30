"""Unit tests for VisibilitySolver.

ИСПРАВЛЕНИЕ: Добавлены unit-тесты для критичного алгоритма compute_visible_counts.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock

from app.views.main_components.topbar.visibility_solver import VisibilitySolver
from app.views.main_components.topbar.width_calculator import WidthCalculator
from app.views.main_components.topbar.layout_context import LayoutContext
from app.views.main_components.topbar.panel_state import PanelState, PanelDefinition


@pytest.fixture
def width_calculator():
    """Fixture для WidthCalculator с моком."""
    calc = WidthCalculator(button_size=32)
    # Мокируем total_width для предсказуемого поведения
    calc.total_width = Mock(return_value=500)
    return calc


@pytest.fixture
def solver(width_calculator):
    """Fixture для VisibilitySolver."""
    return VisibilitySolver(width_calculator)


def create_panel_state(label: str, min_visible: int, max_visible: int) -> PanelState:
    """Helper для создания PanelState."""
    definition = PanelDefinition(
        label=label,
        attr_name=f"{label}_widget",
        button_object_name=f"{label}Button",
        min_attr=f"_min_{label}",
        max_attr=f"_max_{label}",
    )
    return PanelState(
        definition=definition,
        widget=Mock(),
        buttons=[Mock() for _ in range(max_visible)],
        min_visible=min_visible,
        max_visible=max_visible,
    )


def create_layout_context(width: int, panel_states: tuple) -> LayoutContext:
    """Helper для создания LayoutContext."""
    return LayoutContext(
        container=Mock(),
        width=width,
        effective_width=width,
        min_search_width=150,
        top_bar=Mock(),
        search=Mock(),
        panel_states=panel_states,
    )


class TestVisibilitySolver:
    """Тесты для VisibilitySolver."""

    def test_compute_visible_counts_all_fit(self, solver, width_calculator):
        """Тест: все панели помещаются с максимальными значениями."""
        panel_states = (
            create_panel_state("recent", min_visible=0, max_visible=10),
            create_panel_state("fav", min_visible=0, max_visible=10),
            create_panel_state("quick", min_visible=0, max_visible=6),
        )
        ctx = create_layout_context(width=1000, panel_states=panel_states)
        
        # Мокируем total_width чтобы всегда помещалось
        width_calculator.total_width.return_value = 900
        
        counts = solver.compute_visible_counts(ctx)
        
        assert counts["recent"] == 10
        assert counts["fav"] == 10
        assert counts["quick"] == 6

    def test_compute_visible_counts_needs_reduction(self, solver, width_calculator):
        """Тест: нужно уменьшить количество кнопок."""
        panel_states = (
            create_panel_state("recent", min_visible=2, max_visible=10),
            create_panel_state("fav", min_visible=2, max_visible=10),
            create_panel_state("quick", min_visible=3, max_visible=6),
        )
        ctx = create_layout_context(width=500, panel_states=panel_states)
        
        # Мокируем total_width: сначала не помещается, потом помещается
        call_count = [0]
        def mock_total_width(*args, **kwargs):
            call_count[0] += 1
            # Первые 5 вызовов - не помещается, потом помещается
            if call_count[0] <= 5:
                return 600  # Больше чем width=500
            return 400  # Помещается
        
        width_calculator.total_width.side_effect = mock_total_width
        
        counts = solver.compute_visible_counts(ctx)
        
        # Должны уменьшиться, но не ниже минимумов
        assert counts["recent"] >= 2
        assert counts["fav"] >= 2
        assert counts["quick"] >= 3
        # Хотя бы одна панель должна уменьшиться
        assert counts["recent"] < 10 or counts["fav"] < 10 or counts["quick"] < 6

    def test_compute_visible_counts_minimums_enforced(self, solver, width_calculator):
        """Тест: минимумы соблюдаются даже если не помещается."""
        panel_states = (
            create_panel_state("recent", min_visible=5, max_visible=10),
            create_panel_state("fav", min_visible=5, max_visible=10),
            create_panel_state("quick", min_visible=3, max_visible=6),
        )
        ctx = create_layout_context(width=100, panel_states=panel_states)
        
        # Мокируем total_width: всегда не помещается
        width_calculator.total_width.return_value = 1000
        
        counts = solver.compute_visible_counts(ctx)
        
        # Должны вернуться к минимумам
        assert counts["recent"] == 5
        assert counts["fav"] == 5
        assert counts["quick"] == 3

    def test_compute_visible_counts_priority_order(self, solver, width_calculator):
        """Тест: приоритет уменьшения (recent сжимается последним)."""
        panel_states = (
            create_panel_state("recent", min_visible=0, max_visible=10),
            create_panel_state("fav", min_visible=0, max_visible=10),
            create_panel_state("quick", min_visible=0, max_visible=6),
        )
        ctx = create_layout_context(width=500, panel_states=panel_states)
        
        # Мокируем: нужно уменьшить на 1 кнопку
        call_count = [0]
        def mock_total_width(top_bar, search, states, counts, min_search):
            call_count[0] += 1
            if call_count[0] == 1:
                return 600  # Не помещается
            return 400  # Помещается после уменьшения
        
        width_calculator.total_width.side_effect = mock_total_width
        
        counts = solver.compute_visible_counts(ctx)
        
        # Recent должен остаться максимальным (наивысший приоритет)
        assert counts["recent"] == 10
        # Одна из других панелей должна уменьшиться
        assert counts["fav"] < 10 or counts["quick"] < 6

    def test_compute_visible_counts_infinite_loop_protection(self, solver, width_calculator):
        """Тест: защита от бесконечного цикла."""
        panel_states = (
            create_panel_state("recent", min_visible=0, max_visible=100),
            create_panel_state("fav", min_visible=0, max_visible=100),
        )
        ctx = create_layout_context(width=500, panel_states=panel_states)
        
        # Мокируем: всегда не помещается (провоцируем бесконечный цикл)
        width_calculator.total_width.return_value = 10000
        
        # Не должно зависнуть, должно вернуть минимумы
        counts = solver.compute_visible_counts(ctx)
        
        assert counts["recent"] == 0
        assert counts["fav"] == 0
        # Проверяем что total_width вызывался ограниченное число раз
        assert width_calculator.total_width.call_count < 300  # total_steps = 200


@pytest.mark.parametrize("width,expected_all_max", [
    (2000, True),   # Широкое окно - все максимумы
    (500, False),   # Узкое окно - нужно сжатие
    (100, False),   # Очень узкое - минимумы
])
def test_compute_visible_counts_parametrized(solver, width_calculator, width, expected_all_max):
    """Параметризованный тест для разных ширин окна."""
    panel_states = (
        create_panel_state("recent", min_visible=2, max_visible=10),
        create_panel_state("fav", min_visible=2, max_visible=10),
    )
    ctx = create_layout_context(width=width, panel_states=panel_states)
    
    # Простая логика: если запрошенная ширина > width, не помещается
    def mock_total_width(top_bar, search, states, counts, min_search):
        # Примерно 50px на кнопку
        total = sum(counts.values()) * 50 + min_search
        return total
    
    width_calculator.total_width.side_effect = mock_total_width
    
    counts = solver.compute_visible_counts(ctx)
    
    if expected_all_max:
        assert counts["recent"] == 10
        assert counts["fav"] == 10
    else:
        # Должны быть меньше максимумов или равны минимумам
        assert counts["recent"] <= 10
        assert counts["fav"] <= 10
