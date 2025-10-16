"""Тесты для проверки отсутствия диагностического кода в production."""

import logging
import pytest
from unittest.mock import patch, MagicMock
from app.views.widgets.panels.favorites_panel_widget import FavoritesPanelWidget
from app.views.widgets.panels.recent_panel_widget import RecentPanelWidget


def test_favorites_panel_no_traceback_logging(qtbot, caplog):
    """Проверка что FavoritesPanelWidget не логирует traceback при setVisible."""
    with caplog.at_level(logging.INFO):
        panel = FavoritesPanelWidget()
        qtbot.addWidget(panel)
        
        # Изменить видимость несколько раз
        panel.setVisible(False)
        panel.setVisible(True)
        panel.setVisible(False)
        
        # Проверить что нет логов с traceback
        for record in caplog.records:
            assert "traceback" not in record.message.lower()
            assert "[FavoritesDiag]" not in record.message
            assert "called from:" not in record.message


def test_favorites_panel_no_performance_logging(qtbot, caplog):
    """Проверка что FavoritesPanelWidget не логирует performance metrics."""
    with caplog.at_level(logging.INFO):
        panel = FavoritesPanelWidget()
        qtbot.addWidget(panel)
        
        test_data = [
            {"id": i, "name": f"Fav {i}", "url": f"http://test{i}.com"}
            for i in range(10)
        ]
        panel.set_data(test_data)
        
        # Проверить что нет performance логов
        for record in caplog.records:
            assert "[FavoritesDiag]" not in record.message
            assert "ms" not in record.message or "timeout" in record.message.lower()
            assert "_populate_panel done" not in record.message


def test_recent_panel_no_performance_logging(qtbot, caplog):
    """Проверка что RecentPanelWidget не логирует performance metrics."""
    with caplog.at_level(logging.INFO):
        panel = RecentPanelWidget()
        qtbot.addWidget(panel)
        
        test_data = [
            {"id": i, "name": f"Recent {i}", "url": f"http://test{i}.com"}
            for i in range(5)
        ]
        panel.set_data(test_data)
        
        # Проверить что нет performance логов
        for record in caplog.records:
            assert "[RecentDiag]" not in record.message
            assert "ms" not in record.message or "timeout" in record.message.lower()


def test_panel_initial_visibility_managed_by_topbar(qtbot):
    """Проверка что панели не скрываются при инициализации."""
    fav_panel = FavoritesPanelWidget()
    qtbot.addWidget(fav_panel)
    
    recent_panel = RecentPanelWidget()
    qtbot.addWidget(recent_panel)
    
    # Панели должны быть видимы по умолчанию
    # (видимость управляется TopBarLayoutManager)
    assert fav_panel.isVisible() is True
    assert recent_panel.isVisible() is True


def test_no_time_perf_counter_imports_in_set_data(qtbot):
    """Проверка что set_data не импортирует time.perf_counter."""
    panel = FavoritesPanelWidget()
    qtbot.addWidget(panel)
    
    # Патчим time.perf_counter чтобы убедиться что он не вызывается
    with patch("time.perf_counter") as mock_perf:
        test_data = [{"id": 1, "name": "Test", "url": "http://test.com"}]
        panel.set_data(test_data)
        
        # perf_counter не должен вызываться в set_data
        # (может вызываться в других местах, но не для диагностики)
        assert mock_perf.call_count == 0
