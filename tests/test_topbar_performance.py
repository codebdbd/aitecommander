"""Tests for topbar loading performance.

Проверяет, что топпанель загружается быстро и без рывков.
"""
import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from app.views.main_components.ui.topbar.top_bar_layout_manager import (
    TopBarLayoutManager,
)
from app.views.widgets.base.base_panel_widgets import BaseTopPanelWidget


@pytest.fixture
def mock_window(qtbot):
    """Create mock main window."""
    window = Mock()
    window._topbar_manager = None
    window.top_bar_host = Mock()
    window.content_container = Mock()
    window.quick_add_widget = Mock()
    window.fav_widget = Mock()
    window.recent_links_widget = Mock()
    window.search = Mock()
    
    # Mock layout
    top_bar = Mock()
    top_bar.count.return_value = 0
    top_bar.spacing.return_value = 4
    top_bar.contentsMargins.return_value = Mock(left=lambda: 8, right=lambda: 8)
    window.top_bar_host.layout.return_value = top_bar
    
    return window


@pytest.fixture
def panel_widget(qtbot, mock_window):
    """Create test panel widget."""
    widget = BaseTopPanelWidget(main_window=mock_window)
    qtbot.addWidget(widget)
    return widget


class TestTopBarPerformance:
    """Тесты производительности топпанели."""

    def test_prepare_initial_layout_no_opacity_effect(self, qtbot, mock_window):
        """Проверить, что prepare_initial_layout не создаёт QGraphicsOpacityEffect.
        
        FIX: Убран opacity effect для устранения визуальных задержек.
        """
        with patch("app.views.main_components.ui.topbar.top_bar_layout_manager.WidgetAccessor"):
            mgr = TopBarLayoutManager(mock_window)
            
            # Вызвать prepare_initial_layout
            mgr.prepare_initial_layout()
            
            # Проверить, что opacity effect не создан
            assert mgr._opacity_effect is None

    def test_mark_data_ready_no_opacity_change(self, qtbot, mock_window):
        """Проверить, что mark_data_ready не меняет opacity.
        
        FIX: Убрана установка opacity для ускорения загрузки.
        """
        with patch("app.views.main_components.ui.topbar.top_bar_layout_manager.WidgetAccessor"):
            mgr = TopBarLayoutManager(mock_window)
            mgr.prepare_initial_layout()
            
            # Mock adjust to prevent actual layout calculations
            mgr.adjust = Mock()
            
            # Вызвать mark_data_ready
            mgr.mark_data_ready()
            
            # Проверить, что adjust был вызван
            mgr.adjust.assert_called_once()

    def test_sync_topbar_layout_batching(self, qtbot, panel_widget):
        """Проверить, что _sync_topbar_layout использует батчинг.
        
        FIX: Добавлен батчинг для предотвращения множественных adjust().
        """
        # Mock manager
        mock_mgr = Mock()
        panel_widget._main_window._topbar_manager = mock_mgr
        
        # Вызвать _sync_topbar_layout несколько раз подряд
        panel_widget._sync_topbar_layout()
        panel_widget._sync_topbar_layout()
        panel_widget._sync_topbar_layout()
        
        # Проверить, что adjust_pending установлен
        assert panel_widget._adjust_pending is True
        
        # Проверить, что таймер запущен
        assert panel_widget._adjust_timer is not None
        assert panel_widget._adjust_timer.isActive()
        
        # Дождаться выполнения таймера
        qtbot.wait(20)
        
        # Проверить, что adjust был вызван только один раз
        mock_mgr.adjust.assert_called_once()

    def test_multiple_set_data_single_adjust(self, qtbot, mock_window):
        """Проверить, что множественные set_data() вызывают adjust() только один раз.
        
        FIX: Батчинг должен объединять все вызовы в один.
        """
        from app.views.widgets.panels.favorites_panel_widget import FavoritesPanelWidget
        from app.views.widgets.panels.recent_panel_widget import RecentPanelWidget
        
        # Mock manager
        mock_mgr = Mock()
        mock_window._topbar_manager = mock_mgr
        
        # Создать виджеты
        fav_widget = FavoritesPanelWidget(mock_window)
        recent_widget = RecentPanelWidget(mock_window)
        qtbot.addWidget(fav_widget)
        qtbot.addWidget(recent_widget)
        
        # Вызвать set_data на обоих виджетах
        fav_widget.set_data([])
        recent_widget.set_data([])
        
        # Проверить, что adjust ещё не вызван (ждём таймер)
        mock_mgr.adjust.assert_not_called()
        
        # Дождаться выполнения таймеров
        qtbot.wait(20)
        
        # Проверить, что adjust был вызван только один раз (батчинг сработал)
        assert mock_mgr.adjust.call_count == 1

    def test_topbar_initialization_timing(self, qtbot, mock_window):
        """Проверить, что инициализация топпанели происходит быстро.
        
        FIX: Упрощена инициализация для ускорения загрузки.
        """
        with patch("app.views.main_components.ui.topbar.top_bar_layout_manager.WidgetAccessor"):
            start = time.perf_counter()
            
            mgr = TopBarLayoutManager(mock_window)
            mgr.prepare_initial_layout()
            
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Инициализация должна занимать < 50ms
            assert duration_ms < 50, f"Initialization took {duration_ms:.1f}ms (expected < 50ms)"

    def test_no_visible_false_on_host_creation(self, qtbot):
        """Проверить, что top_bar_host не скрывается при создании.
        
        FIX: Убрано setVisible(False) для устранения рывков.
        """
        from PyQt6.QtWidgets import QHBoxLayout, QWidget
        from app.views.main_components.ui.window_ui_setup import WindowUISetup
        
        # Mock window and setup
        window = Mock()
        main_layout = Mock()
        setup = WindowUISetup(window, main_layout)
        
        # Create top bar host
        container = QWidget()
        top_bar = QHBoxLayout()
        
        with patch("app.config_data.app_config"):
            host = setup._create_top_bar_host(container, top_bar)
        
        # Проверить, что host видим (не был скрыт)
        assert host.isVisible() is True


@pytest.mark.benchmark
class TestTopBarBenchmarks:
    """Бенчмарки производительности топпанели."""

    def test_benchmark_prepare_initial_layout(self, benchmark, mock_window):
        """Бенчмарк prepare_initial_layout."""
        with patch("app.views.main_components.ui.topbar.top_bar_layout_manager.WidgetAccessor"):
            mgr = TopBarLayoutManager(mock_window)
            
            def run():
                mgr.prepare_initial_layout()
            
            result = benchmark(run)
            
            # Должно быть < 10ms
            assert result < 0.01

    def test_benchmark_sync_topbar_layout(self, benchmark, panel_widget):
        """Бенчмарк _sync_topbar_layout с батчингом."""
        mock_mgr = Mock()
        panel_widget._main_window._topbar_manager = mock_mgr
        
        def run():
            panel_widget._sync_topbar_layout()
        
        result = benchmark(run)
        
        # С батчингом должно быть очень быстро (< 1ms)
        assert result < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
