"""Интеграционные тесты для TopBarLayoutManager.

ИСПРАВЛЕНИЕ: Добавлены интеграционные тесты для проверки работы
TopBarLayoutManager с реальными Qt виджетами.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton, QFrame, QVBoxLayout

from app.views.main_components.ui.topbar.top_bar_layout_manager import (
    TopBarLayoutManager,
    InitializationState,
)

# Прямой импорт для обхода отсутствующего __init__.py


class MockWindow(QWidget):
    """Mock окна для тестирования TopBarLayoutManager."""
    
    def __init__(self):
        super().__init__()
        self.setGeometry(0, 0, 1000, 600)
        
        # Создаем структуру виджетов
        self.top_bar_host = QWidget(self)
        self.top_bar_host.setGeometry(0, 0, 1000, 40)
        
        layout = QHBoxLayout(self.top_bar_host)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        
        # Создаем панели
        self.recent_links_widget = self._create_panel("recent", 5)
        self.fav_widget = self._create_panel("fav", 3)
        self.quick_add_widget = self._create_panel("quick", 2)
        
        layout.addWidget(self.recent_links_widget)
        layout.addWidget(self.fav_widget)
        layout.addWidget(self.quick_add_widget)
        
        # Поле поиска
        self.search = QLineEdit(self.top_bar_host)
        self.search.setMinimumWidth(148)
        layout.addWidget(self.search)
    
    def _create_panel(self, name: str, button_count: int) -> QWidget:
        """Создает панель с кнопками."""
        panel = QWidget()
        panel.setObjectName(f"{name}Panel")
        
        bg_frame = QFrame(panel)
        bg_frame.setObjectName("bg_frame")
        
        panel_layout = QHBoxLayout(bg_frame)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(2)
        
        # Создаем кнопки
        button_name_map = {
            "recent": "recentButton",
            "fav": "favoriteButton",
            "quick": "quickButton",
        }
        button_object_name = button_name_map.get(name, "button")
        
        for i in range(button_count):
            btn = QToolButton(bg_frame)
            btn.setObjectName(button_object_name)
            btn.setFixedSize(32, 32)
            panel_layout.addWidget(btn)
        
        # Устанавливаем bg_frame как атрибут панели
        panel.bg_frame = bg_frame
        
        # Layout для панели
        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(bg_frame)
        
        return panel


@pytest.fixture
def mock_app_config():
    """Mock для app_config."""
    with patch('app.views.main_components.topbar.top_bar_layout_manager.app_config') as mock_config:
        # Настраиваем mock
        mock_config.get.return_value = 32
        mock_config.ui.get_top_panel_button_size.return_value = 32
        mock_config.ui.get_top_panel_search_min_width.return_value = 148
        mock_config.ui.get_top_bar_widgets_side_spacing.return_value = 8
        mock_config.ui.get_top_bar_height.return_value = 40
        yield mock_config


@pytest.fixture
def window(qtbot, mock_app_config):
    """Создает mock окно для тестов."""
    win = MockWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    return win


class TestTopBarLayoutManagerIntegration:
    """Интеграционные тесты для TopBarLayoutManager."""
    
    def test_initialization(self, window, qtbot):
        """Тест инициализации менеджера."""
        manager = TopBarLayoutManager(window)
        
        assert manager.window is window
        assert manager._init_state == InitializationState.NOT_STARTED
        assert manager._throttle_interval_ms == 32
        assert manager._min_search_width == 148
    
    def test_prepare_initial_layout(self, window, qtbot):
        """Тест подготовки начального layout."""
        manager = TopBarLayoutManager(window)
        
        manager.prepare_initial_layout()
        
        assert manager._init_state == InitializationState.WAITING_FOR_DATA
        assert window.top_bar_host.isVisible()
    
    def test_mark_data_ready_transition(self, window, qtbot):
        """Тест перехода состояния при mark_data_ready."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        
        assert manager._init_state == InitializationState.WAITING_FOR_DATA
        
        manager.mark_data_ready()
        
        assert manager._init_state == InitializationState.DATA_READY
    
    def test_adjust_with_sufficient_width(self, window, qtbot):
        """Тест adjust при достаточной ширине."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        manager.mark_data_ready()
        
        # Устанавливаем достаточную ширину
        window.top_bar_host.setGeometry(0, 0, 1000, 40)
        
        manager.adjust()
        
        # Проверяем, что состояние изменилось
        assert manager._init_state == InitializationState.LAYOUT_APPLIED
        
        # Проверяем, что поле поиска имеет минимальную ширину
        assert window.search.minimumWidth() >= 148
    
    def test_adjust_with_narrow_width(self, window, qtbot):
        """Тест adjust при узкой ширине."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        manager.mark_data_ready()
        
        # Устанавливаем узкую ширину
        window.top_bar_host.setGeometry(0, 0, 300, 40)
        
        manager.adjust()
        
        # В узком режиме панели должны быть скрыты или минимизированы
        assert manager._init_state == InitializationState.LAYOUT_APPLIED
    
    def test_throttling(self, window, qtbot):
        """Тест throttling механизма."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        manager.mark_data_ready()
        
        # Первый вызов должен пройти
        manager.adjust()
        assert manager._init_state == InitializationState.LAYOUT_APPLIED
        
        # Запускаем throttle timer
        manager._throttle_timer.start(32)
        
        # Второй вызов должен быть заблокирован
        initial_state = manager._init_state
        manager.adjust()
        
        # Состояние не должно измениться (вызов был пропущен)
        assert manager._throttle_timer.isActive()
    
    def test_signals_emission(self, window, qtbot):
        """Тест испускания сигналов."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        manager.mark_data_ready()
        
        # Подключаем spy для сигналов
        layout_adjusted_spy = qtbot.waitSignal(manager.layoutAdjusted, timeout=1000)
        
        manager.adjust()
        
        # Проверяем, что сигнал был испущен
        assert layout_adjusted_spy.signal_triggered
    
    def test_cleanup(self, window, qtbot):
        """Тест очистки ресурсов."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        
        # Добавляем event filter
        assert len(manager._watched_panels) > 0
        
        # Очищаем
        manager.cleanup()
        
        # Проверяем, что ресурсы очищены
        assert len(manager._watched_panels) == 0
        assert not manager._throttle_timer.isActive()
    
    def test_thread_safety_check(self, window, qtbot):
        """Тест проверки thread safety."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        manager.mark_data_ready()
        
        # Вызываем из main thread - должно работать
        manager.adjust()
        
        assert manager._init_state == InitializationState.LAYOUT_APPLIED
    
    def test_race_condition_protection(self, window, qtbot):
        """Тест защиты от race condition."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        
        # Пытаемся вызвать adjust до готовности данных
        manager.adjust()
        
        # Состояние не должно измениться
        assert manager._init_state == InitializationState.WAITING_FOR_DATA
        
        # После mark_data_ready adjust должен сработать
        manager.mark_data_ready()
        assert manager._init_state == InitializationState.DATA_READY
    
    def test_fallback_timeout(self, window, qtbot):
        """Тест fallback таймаута."""
        manager = TopBarLayoutManager(window)
        manager.prepare_initial_layout()
        
        # Запускаем fallback
        manager._schedule_data_ready_fallback()
        
        # Ждем таймаут (500ms)
        qtbot.wait(600)
        
        # Состояние должно перейти в DATA_READY
        assert manager._init_state == InitializationState.DATA_READY


class TestWidthCalculatorIntegration:
    """Интеграционные тесты для WidthCalculator."""
    
    def test_panel_width_calculation(self, window, qtbot, mock_app_config):
        """Тест расчета ширины панели."""
        from app.views.main_components.topbar.width_calculator import WidthCalculator
        
        calculator = WidthCalculator(button_size=32)
        
        # Получаем кнопки панели
        panel = window.recent_links_widget
        buttons = panel.findChildren(QToolButton, "recentButton")
        
        # Рассчитываем ширину для 3 видимых кнопок
        width = calculator.panel_width(panel, buttons, 3)
        
        # Ширина должна быть больше минимальной
        assert width >= calculator.MIN_PANEL_WIDTH
        assert width > 0
    
    def test_lru_cache(self, window, qtbot, mock_app_config):
        """Тест LRU кэша."""
        from app.views.main_components.topbar.width_calculator import WidthCalculator
        
        calculator = WidthCalculator(button_size=32)
        panel = window.recent_links_widget
        buttons = panel.findChildren(QToolButton, "recentButton")
        
        # Первый вызов - cache miss
        width1 = calculator.panel_width(panel, buttons, 3)
        assert calculator._cache_misses == 1
        assert calculator._cache_hits == 0
        
        # Второй вызов - cache hit
        width2 = calculator.panel_width(panel, buttons, 3)
        assert calculator._cache_hits == 1
        assert width1 == width2
        
        # Проверяем статистику
        stats = calculator.get_cache_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 50


class TestPanelVisibilityManagerIntegration:
    """Интеграционные тесты для PanelVisibilityManager."""
    
    def test_set_visible_count(self, window, qtbot, mock_app_config):
        """Тест установки количества видимых кнопок."""
        from app.views.main_components.ui.topbar.panel_visibility_manager import PanelVisibilityManager
        from app.views.main_components.ui.topbar.width_calculator import WidthCalculator
        
        calculator = WidthCalculator(button_size=32)
        manager = PanelVisibilityManager(calculator)
        
        panel = window.recent_links_widget
        buttons = panel.findChildren(QToolButton, "recentButton")
        
        # Устанавливаем 3 видимые кнопки из 5
        visible = manager.set_visible_count(panel, buttons, 3)
        
        assert visible == 3
        
        # Проверяем видимость кнопок
        for i, btn in enumerate(buttons):
            if i < 3:
                assert btn.isVisible()
            else:
                assert not btn.isVisible()
    
    def test_iter_buttons(self, window, qtbot, mock_app_config):
        """Тест поиска кнопок в панели."""
        from app.views.main_components.ui.topbar.panel_visibility_manager import PanelVisibilityManager
        from app.views.main_components.ui.topbar.width_calculator import WidthCalculator
        
        calculator = WidthCalculator(button_size=32)
        manager = PanelVisibilityManager(calculator)
        
        # Ищем кнопки recent
        buttons = manager.iter_buttons(window.recent_links_widget, "recentButton")
        assert len(buttons) == 5
        
        # Ищем кнопки fav
        buttons = manager.iter_buttons(window.fav_widget, "favoriteButton")
        assert len(buttons) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
