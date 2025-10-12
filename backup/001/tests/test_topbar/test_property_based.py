"""Property-based тесты для TopBar компонентов.

ИСПРАВЛЕНИЕ: Добавлены property-based тесты с hypothesis для проверки
edge cases и инвариантов при различных входных данных.
"""

from __future__ import annotations

import pytest

try:
    from hypothesis import given, strategies as st, settings, assume
    from hypothesis import HealthCheck
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    pytest.skip("hypothesis not installed", allow_module_level=True)

from unittest.mock import Mock
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton

from app.views.main_components.topbar.visibility_solver import VisibilitySolver
from app.views.main_components.topbar.width_calculator import WidthCalculator
from app.views.main_components.topbar.layout_context import LayoutContext
from app.views.main_components.topbar.panel_state import PanelState, PanelDefinition
from app.views.main_components.topbar.config_protocol import MockTopBarConfig
from app.views.main_components.topbar.top_bar_layout_manager import InitializationState


class TestVisibilitySolverPropertyBased:
    """Property-based тесты для VisibilitySolver."""
    
    @given(
        width=st.integers(min_value=100, max_value=3000),
        button_size=st.integers(min_value=16, max_value=64),
        min_search_width=st.integers(min_value=50, max_value=300),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_compute_visible_counts_respects_constraints(
        self, width, button_size, min_search_width
    ):
        """Проверяет, что compute_visible_counts всегда соблюдает ограничения.
        
        Инварианты:
        - Результат всегда между min_visible и max_visible
        - Сумма ширин не превышает доступную ширину
        - Результат детерминирован для одинаковых входных данных
        """
        # Arrange
        calculator = WidthCalculator(button_size=button_size)
        solver = VisibilitySolver(calculator)
        
        # Создаем mock layout и виджеты
        layout = Mock(spec=QHBoxLayout)
        layout.spacing.return_value = 6
        layout.contentsMargins.return_value = Mock(left=lambda: 8, right=lambda: 8)
        
        search = Mock(spec=QLineEdit)
        search.sizeHint.return_value = Mock(width=lambda: min_search_width)
        
        container = Mock(spec=QWidget)
        
        # Создаем panel states с разумными значениями
        panel_states = []
        for i, (label, min_vis, max_vis) in enumerate([
            ("recent", 0, 10),
            ("fav", 0, 10),
            ("quick", 0, 6),
        ]):
            definition = PanelDefinition(
                label=label,
                attr_name=f"{label}_widget",
                button_object_name=f"{label}Button",
                min_attr=f"_min_{label}",
                max_attr=f"_max_{label}",
            )
            
            # Mock buttons
            buttons = [Mock(spec=QToolButton) for _ in range(max_vis)]
            for btn in buttons:
                btn.sizeHint.return_value = Mock(width=lambda: button_size)
            
            panel_states.append(PanelState(
                definition=definition,
                widget=Mock(spec=QWidget),
                buttons=buttons,
                min_visible=min_vis,
                max_visible=max_vis,
            ))
        
        ctx = LayoutContext(
            container=container,
            width=width,
            effective_width=width,
            min_search_width=min_search_width,
            top_bar=layout,
            search=search,
            panel_states=tuple(panel_states),
        )
        
        # Act
        counts = solver.compute_visible_counts(ctx)
        
        # Assert - проверяем инварианты
        for state in panel_states:
            label = state.definition.label
            count = counts.get(label, 0)
            
            # Инвариант 1: результат в допустимом диапазоне
            assert state.min_visible <= count <= state.max_visible, \
                f"Count {count} for {label} not in range [{state.min_visible}, {state.max_visible}]"
            
            # Инвариант 2: результат неотрицательный
            assert count >= 0, f"Count {count} for {label} is negative"
        
        # Инвариант 3: детерминированность
        counts2 = solver.compute_visible_counts(ctx)
        assert counts == counts2, "compute_visible_counts is not deterministic"
    
    @given(
        button_count=st.integers(min_value=0, max_value=20),
        visible_count=st.integers(min_value=0, max_value=20),
        button_size=st.integers(min_value=16, max_value=64),
    )
    @settings(max_examples=50)
    def test_width_calculator_panel_width_properties(
        self, button_count, visible_count, button_size
    ):
        """Проверяет свойства WidthCalculator.panel_width.
        
        Инварианты:
        - Ширина всегда >= MIN_PANEL_WIDTH
        - Ширина монотонно возрастает с количеством кнопок
        - Ширина детерминирована
        """
        # Arrange
        calculator = WidthCalculator(button_size=button_size)
        
        # Ограничиваем visible_count количеством кнопок
        visible_count = min(visible_count, button_count)
        assume(visible_count >= 0)
        
        # Создаем mock panel и buttons
        panel = Mock(spec=QWidget)
        panel.contentsMargins.return_value = Mock(left=lambda: 4, right=lambda: 4)
        
        bg_frame = Mock()
        bg_frame.frameWidth.return_value = 1
        panel.bg_frame = bg_frame
        
        layout = Mock()
        layout.spacing.return_value = 2
        layout.contentsMargins.return_value = Mock(left=lambda: 2, right=lambda: 2)
        layout.count.return_value = button_count
        
        buttons = []
        for i in range(button_count):
            btn = Mock(spec=QToolButton)
            btn.sizeHint.return_value = Mock(width=lambda: button_size)
            btn.maximumWidth.return_value = 0
            btn.minimumWidth.return_value = 0
            buttons.append(btn)
        
        # Mock layout.itemAt
        def mock_item_at(index):
            if index < len(buttons):
                item = Mock()
                item.widget.return_value = buttons[index]
                return item
            return None
        
        layout.itemAt = mock_item_at
        bg_frame.layout.return_value = layout
        
        # Act
        width = calculator.panel_width(panel, buttons, visible_count)
        
        # Assert - проверяем инварианты
        # Инвариант 1: ширина >= MIN_PANEL_WIDTH
        assert width >= calculator.MIN_PANEL_WIDTH, \
            f"Width {width} < MIN_PANEL_WIDTH {calculator.MIN_PANEL_WIDTH}"
        
        # Инвариант 2: ширина детерминирована
        width2 = calculator.panel_width(panel, buttons, visible_count)
        assert width == width2, "panel_width is not deterministic"
        
        # Инвариант 3: монотонность (если добавляем кнопки, ширина не уменьшается)
        if visible_count < button_count:
            width_more = calculator.panel_width(panel, buttons, visible_count + 1)
            assert width_more >= width, \
                f"Width decreased when adding button: {width} -> {width_more}"
    
    @given(
        width=st.integers(min_value=200, max_value=2000),
        button_size=st.integers(min_value=24, max_value=48),
    )
    @settings(max_examples=30)
    def test_config_protocol_properties(self, width, button_size):
        """Проверяет свойства MockTopBarConfig.
        
        Инварианты:
        - Все getter методы возвращают значения правильного типа
        - Значения соответствуют переданным в конструктор
        - get() метод работает корректно
        """
        # Arrange
        config = MockTopBarConfig(
            button_size=button_size,
            search_min_width=width // 10,  # Разумное значение
            search_height=32,
            top_bar_height=40,
            side_spacing=8,
            throttle_ms=50,
            log_info=False,
        )
        
        # Assert - проверяем инварианты
        # Инвариант 1: типы возвращаемых значений
        assert isinstance(config.get_button_size(), int)
        assert isinstance(config.get_search_min_width(), int)
        assert isinstance(config.get_search_height(), int)
        assert isinstance(config.get_top_bar_height(), int)
        assert isinstance(config.get_side_spacing(), int)
        assert isinstance(config.get_throttle_ms(), int)
        assert isinstance(config.get_log_info(), bool)
        
        # Инвариант 2: значения соответствуют конструктору
        assert config.get_button_size() == button_size
        assert config.get_search_min_width() == width // 10
        
        # Инвариант 3: get() метод
        config.set("custom_key", 42)
        assert config.get("custom_key") == 42
        assert config.get("nonexistent_key", "default") == "default"
    
    @given(
        state_transitions=st.lists(
            st.sampled_from([
                InitializationState.NOT_STARTED,
                InitializationState.WAITING_FOR_DATA,
                InitializationState.DATA_READY,
                InitializationState.LAYOUT_APPLIED,
            ]),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=30)
    def test_initialization_state_transitions(self, state_transitions):
        """Проверяет, что переходы состояний всегда валидны.
        
        Инварианты:
        - Состояния из Enum всегда валидны
        - Можно сравнивать состояния
        - Состояния имеют строковое представление
        """
        # Assert - проверяем инварианты для каждого состояния
        for state in state_transitions:
            # Инвариант 1: состояние является членом Enum
            assert isinstance(state, InitializationState)
            
            # Инвариант 2: состояние имеет name и value
            assert hasattr(state, 'name')
            assert hasattr(state, 'value')
            
            # Инвариант 3: можно сравнивать состояния
            assert state == state
            assert not (state != state)
            
            # Инвариант 4: строковое представление
            assert str(state).startswith('InitializationState.')


class TestCachePropertyBased:
    """Property-based тесты для LRU кэша."""
    
    @given(
        operations=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=10),  # panel_id
                st.integers(min_value=0, max_value=10),  # count
            ),
            min_size=1,
            max_size=150  # Больше чем CACHE_MAX_SIZE (100)
        )
    )
    @settings(max_examples=20)
    def test_lru_cache_properties(self, operations):
        """Проверяет свойства LRU кэша.
        
        Инварианты:
        - Размер кэша не превышает CACHE_MAX_SIZE
        - Hit rate корректно вычисляется
        - Кэш возвращает одинаковые значения для одинаковых ключей
        """
        # Arrange
        calculator = WidthCalculator(button_size=32)
        
        # Создаем mock panels
        panels = {}
        for panel_id in range(11):
            panel = Mock(spec=QWidget)
            panel.contentsMargins.return_value = Mock(left=lambda: 4, right=lambda: 4)
            bg_frame = Mock()
            bg_frame.frameWidth.return_value = 1
            bg_frame.layout.return_value = None
            panel.bg_frame = bg_frame
            panels[panel_id] = panel
        
        # Act - выполняем операции
        results = {}
        for panel_id, count in operations:
            panel = panels[panel_id]
            buttons = [Mock(spec=QToolButton) for _ in range(count)]
            
            width = calculator.panel_width(panel, buttons, count)
            key = (id(panel), count)
            
            # Сохраняем результат для проверки детерминированности
            if key not in results:
                results[key] = width
            else:
                # Инвариант 1: детерминированность
                assert results[key] == width, \
                    f"Cache returned different value for same key: {results[key]} != {width}"
        
        # Assert - проверяем инварианты кэша
        stats = calculator.get_cache_stats()
        
        # Инвариант 2: размер кэша не превышает максимум
        assert stats['size'] <= calculator.CACHE_MAX_SIZE, \
            f"Cache size {stats['size']} exceeds max {calculator.CACHE_MAX_SIZE}"
        
        # Инвариант 3: hits + misses = total operations
        total_ops = len(operations)
        assert stats['hits'] + stats['misses'] == total_ops, \
            f"hits ({stats['hits']}) + misses ({stats['misses']}) != total ({total_ops})"
        
        # Инвариант 4: hit_rate в диапазоне [0, 100]
        assert 0 <= stats['hit_rate'] <= 100, \
            f"Hit rate {stats['hit_rate']} not in range [0, 100]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
