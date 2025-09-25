"""Тесты для проверки улучшений topbar модуля."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock, patch

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication, QLayout, QLineEdit, QToolButton, QWidget

from .cached_width_calculator import CachedWidthCalculator, LayoutCacheKey
from .constants import AdjustmentReason, SizeConstraint, TopBarConstants
from .exceptions import LayoutCalculationError, SizeConstraintError
from .layout_context import LayoutContext
from .panel_size_manager import PanelSizeManager
from .panel_state import PanelDefinition, PanelState
from .separator_manager import SeparatorManager
from .top_bar_layout_manager import TopBarLayoutManager
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator


class TestTopBarConstants(unittest.TestCase):
    """Тесты централизованных констант."""
    
    def test_default_values(self):
        """Проверяет корректность значений по умолчанию."""
        self.assertEqual(TopBarConstants.DEFAULT_BUTTON_SIZE, 32)
        self.assertEqual(TopBarConstants.DEFAULT_MIN_SEARCH_WIDTH, 148)
        self.assertEqual(TopBarConstants.DEFAULT_THROTTLE_MS, 32)
        self.assertEqual(TopBarConstants.DEFAULT_NARROW_THRESHOLD, 380)
    
    def test_config_keys(self):
        """Проверяет наличие всех ключей конфигурации."""
        self.assertIsInstance(TopBarConstants.CONFIG_THROTTLE, str)
        self.assertIsInstance(TopBarConstants.CONFIG_LOG_INFO, str)
        self.assertIsInstance(TopBarConstants.CONFIG_SIDE_SPACING, str)


class TestSizeConstraint(unittest.TestCase):
    """Тесты ограничений размера."""
    
    def test_valid_constraint(self):
        """Проверяет создание валидного ограничения."""
        constraint = SizeConstraint(min_width=100, max_width=200, visible=True)
        self.assertEqual(constraint.min_width, 100)
        self.assertEqual(constraint.max_width, 200)
        self.assertTrue(constraint.visible)
    
    def test_invalid_constraint(self):
        """Проверяет валидацию некорректных ограничений."""
        with self.assertRaises(ValueError):
            SizeConstraint(min_width=-10, max_width=200)
        
        with self.assertRaises(ValueError):
            SizeConstraint(min_width=200, max_width=100)


class TestPanelSizeManager(unittest.TestCase):
    """Тесты менеджера размеров панелей."""
    
    def setUp(self):
        self.manager = PanelSizeManager(button_size=32)
        self.mock_widget = Mock(spec=QWidget)
        self.mock_buttons = [Mock(spec=QToolButton) for _ in range(3)]
    
    def test_calculate_panel_constraint_zero_count(self):
        """Проверяет расчет ограничений для нулевого количества кнопок."""
        constraint = self.manager.calculate_panel_constraint(
            self.mock_widget, self.mock_buttons, 0
        )
        self.assertEqual(constraint.min_width, 0)
        self.assertEqual(constraint.max_width, 0)
        self.assertFalse(constraint.visible)
    
    def test_calculate_panel_constraint_valid_count(self):
        """Проверяет расчет ограничений для валидного количества кнопок."""
        # Настраиваем mock'и
        for button in self.mock_buttons:
            button.sizeHint.return_value.width.return_value = 32
        
        self.mock_widget.bg_frame = Mock()
        self.mock_widget.bg_frame.layout.return_value = None
        self.mock_widget.contentsMargins.return_value.left.return_value = 0
        self.mock_widget.contentsMargins.return_value.right.return_value = 0
        
        constraint = self.manager.calculate_panel_constraint(
            self.mock_widget, self.mock_buttons, 2
        )
        
        self.assertGreater(constraint.min_width, 0)
        self.assertEqual(constraint.min_width, constraint.max_width)
        self.assertTrue(constraint.visible)
    
    def test_set_panel_constraint_invalid_widget(self):
        """Проверяет обработку некорректного виджета."""
        with self.assertRaises(SizeConstraintError):
            self.manager.set_panel_constraint("not_a_widget", SizeConstraint(0, 0))


class TestCachedWidthCalculator(unittest.TestCase):
    """Тесты кэшированного калькулятора ширины."""
    
    def setUp(self):
        self.calculator = CachedWidthCalculator(button_size=32, cache_size=10)
    
    def test_cache_key_creation(self):
        """Проверяет создание ключа кэша."""
        mock_ctx = Mock()
        mock_ctx.width = 800
        mock_ctx.panel_states = [Mock(), Mock()]
        mock_ctx.panel_states[0].buttons = [Mock(), Mock()]
        mock_ctx.panel_states[1].buttons = [Mock()]
        mock_ctx.has_search = True
        mock_ctx.min_search_width = 148
        
        key = LayoutCacheKey.from_context(mock_ctx)
        
        self.assertEqual(key.width, 800)
        self.assertEqual(key.panel_buttons_count, (2, 1))
        self.assertTrue(key.search_present)
        self.assertEqual(key.min_search_width, 148)
    
    def test_cache_hit_miss(self):
        """Проверяет работу кэша (попадания и промахи)."""
        mock_ctx = Mock()
        mock_ctx.width = 800
        mock_ctx.panel_states = []
        mock_ctx.has_search = False
        mock_ctx.min_search_width = 148
        
        # Первый вызов - промах
        with patch.object(self.calculator._visibility_solver, 'compute_visible_counts') as mock_compute:
            mock_compute.return_value = {"test": 1}
            result1 = self.calculator.compute_visible_counts_with_cache(mock_ctx)
            self.assertEqual(mock_compute.call_count, 1)
        
        # Второй вызов с тем же контекстом - попадание
        with patch.object(self.calculator._visibility_solver, 'compute_visible_counts') as mock_compute:
            result2 = self.calculator.compute_visible_counts_with_cache(mock_ctx)
            self.assertEqual(mock_compute.call_count, 0)  # Не должен вызываться
            self.assertEqual(result1, result2)
    
    def test_cache_stats(self):
        """Проверяет статистику кэша."""
        stats = self.calculator.get_cache_stats()
        self.assertIn("cache_size", stats)
        self.assertIn("cache_hits", stats)
        self.assertIn("cache_misses", stats)
        self.assertIn("hit_rate_percent", stats)


class TestTopBarLayoutManagerBatching(unittest.TestCase):
    """Тесты батчинга в TopBarLayoutManager."""
    
    def setUp(self):
        self.mock_window = Mock(spec=QObject)
        self.manager = TopBarLayoutManager(self.mock_window)
    
    def test_request_adjustment_batching(self):
        """Проверяет, что множественные запросы батчируются."""
        # Первый запрос
        self.manager.request_adjustment(AdjustmentReason.WINDOW_RESIZE)
        self.assertTrue(self.manager._adjustment_pending)
        
        # Второй запрос должен игнорироваться
        with patch.object(self.manager, '_batch_timer') as mock_timer:
            self.manager.request_adjustment(AdjustmentReason.PANEL_CHANGE)
            # Таймер не должен перезапускаться
            mock_timer.start.assert_not_called()
    
    def test_force_adjustment_overrides_batching(self):
        """Проверяет, что принудительный запрос игнорирует батчинг."""
        # Устанавливаем pending состояние
        self.manager._adjustment_pending = True
        
        with patch.object(self.manager, '_batch_timer') as mock_timer:
            self.manager.force_adjustment(AdjustmentReason.MANUAL_REQUEST)
            mock_timer.stop.assert_called_once()
            self.assertFalse(self.manager._adjustment_pending)


class TestSeparatorManager(unittest.TestCase):
    """Тесты менеджера разделителей."""
    
    def setUp(self):
        self.manager = SeparatorManager()
        self.mock_layout = Mock(spec=QLayout)
        self.mock_window = Mock()
    
    def test_find_separators_empty_layout(self):
        """Проверяет поиск разделителей в пустом layout."""
        self.mock_layout.count.return_value = 0
        separators = self.manager._find_separators(self.mock_layout)
        self.assertEqual(len(separators), 0)
    
    def test_update_separators_safe_execution(self):
        """Проверяет безопасное выполнение обновления разделителей."""
        applied_counts = {"recent": 2, "fav": 1, "quick": 0}
        
        # Не должно вызывать исключений даже при ошибках
        self.manager.update_separators(
            self.mock_layout, applied_counts, True, self.mock_window
        )


class TestVisibilitySolverImprovements(unittest.TestCase):
    """Тесты улучшений решателя видимости."""
    
    def setUp(self):
        self.calculator = Mock(spec=WidthCalculator)
        self.solver = VisibilitySolver(self.calculator)
    
    def test_solution_tracking(self):
        """Проверяет отслеживание решений."""
        initial_count = self.solver._solution_count
        
        # Создаем mock контекст
        mock_ctx = Mock()
        mock_ctx.panel_states = []
        mock_ctx.width = 800
        
        self.calculator.total_width.return_value = 700  # Помещается
        
        result = self.solver.compute_visible_counts(mock_ctx)
        
        self.assertEqual(self.solver._solution_count, initial_count + 1)
        self.assertEqual(self.solver._last_solution, result)
    
    def test_error_handling_in_calculation(self):
        """Проверяет обработку ошибок при расчете."""
        mock_ctx = Mock()
        mock_ctx.panel_states = [Mock()]
        mock_ctx.panel_states[0].definition.label = "test"
        mock_ctx.panel_states[0].max_visible = 5
        mock_ctx.panel_states[0].min_visible = 0
        mock_ctx.width = 800
        
        # Калькулятор выбрасывает исключение
        self.calculator.total_width.side_effect = RuntimeError("Test error")
        
        result = self.solver.compute_visible_counts(mock_ctx)
        
        # Должен вернуть минимальные значения
        self.assertEqual(result["test"], 0)


if __name__ == "__main__":
    # Создаем QApplication для тестов Qt
    import sys
    app = QApplication(sys.argv)
    
    # Запускаем тесты
    unittest.main()
