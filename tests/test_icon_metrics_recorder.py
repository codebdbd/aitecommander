# test_icon_metrics_recorder.py
"""Тесты для IconMetricsRecorder."""

from __future__ import annotations

import time

import pytest

from app.utils.ui.icon.metrics_recorder import IconMetricsRecorder


class TestIconMetricsRecorder:
    """Тесты базовой функциональности IconMetricsRecorder."""

    def test_record_hit(self):
        """Должен записывать cache hits."""
        recorder = IconMetricsRecorder()
        
        recorder.record_hit()
        recorder.record_hit()
        
        stats = recorder.get_stats()
        assert stats["hits"] == 2

    def test_record_miss(self):
        """Должен записывать cache misses."""
        recorder = IconMetricsRecorder()
        
        recorder.record_miss()
        recorder.record_miss()
        recorder.record_miss()
        
        stats = recorder.get_stats()
        assert stats["misses"] == 3

    def test_record_disk_load(self):
        """Должен записывать disk loads."""
        recorder = IconMetricsRecorder()
        
        recorder.record_disk_load(0.1)
        recorder.record_disk_load(0.2)
        
        stats = recorder.get_stats()
        assert stats["disk_loads"] == 2
        # avg_load_time is formatted as string
        assert "0." in stats["avg_load_time"]

    def test_record_not_found(self):
        """Должен записывать not found."""
        recorder = IconMetricsRecorder()
        
        recorder.record_not_found()
        
        stats = recorder.get_stats()
        assert stats["not_found"] == 1

    def test_get_stats(self):
        """Должен возвращать полную статистику."""
        recorder = IconMetricsRecorder()
        
        recorder.record_hit()
        recorder.record_miss()
        recorder.record_disk_load(0.5)
        
        stats = recorder.get_stats()
        
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "disk_loads" in stats
        assert "avg_load_time" in stats
        assert "uptime" in stats

    def test_reset(self):
        """Должен сбрасывать все метрики."""
        recorder = IconMetricsRecorder()
        
        recorder.record_hit()
        recorder.record_miss()
        recorder.reset()
        
        stats = recorder.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestMetricsLogging:
    """Тесты логирования метрик."""

    def test_maybe_log_metrics_respects_interval(self):
        """Должен логировать только после истечения интервала."""
        recorder = IconMetricsRecorder(report_interval=0.1)
        
        # Первый вызов должен залогировать
        recorder.maybe_log_metrics()
        
        # Второй вызов сразу - не должен
        # (проверяем через внутреннее состояние)
        first_time = recorder._last_report_time
        recorder.maybe_log_metrics()
        assert recorder._last_report_time == first_time
        
        # После ожидания - должен залогировать
        time.sleep(0.15)
        recorder.maybe_log_metrics()
        assert recorder._last_report_time > first_time

    def test_maybe_log_metrics_with_custom_config(self):
        """Должен использовать интервал из config."""
        from unittest.mock import Mock
        
        mock_config = Mock()
        mock_config.icon_metrics_report_interval_s = 0.05
        
        recorder = IconMetricsRecorder(report_interval=10.0)  # Большой дефолт
        
        recorder.maybe_log_metrics(mock_config)
        first_time = recorder._last_report_time
        
        # С интервалом 0.05 из config должен быстро залогировать снова
        time.sleep(0.06)
        recorder.maybe_log_metrics(mock_config)
        assert recorder._last_report_time > first_time


class TestQTimerIntegration:
    """Тесты интеграции с QTimer."""

    def test_qtimer_not_created_by_default(self):
        """QTimer не должен создаваться по умолчанию."""
        recorder = IconMetricsRecorder()
        assert recorder._timer is None

    def test_qtimer_created_when_requested(self, qapp):
        """QTimer должен создаваться при use_qtimer=True."""
        recorder = IconMetricsRecorder(report_interval=1.0, use_qtimer=True)
        
        # QTimer должен быть создан
        assert recorder._timer is not None
        assert recorder._timer.isActive()
        
        # Cleanup
        recorder.stop_timer()

    def test_stop_timer(self, qapp):
        """Должен останавливать QTimer."""
        recorder = IconMetricsRecorder(report_interval=1.0, use_qtimer=True)
        
        assert recorder._timer is not None
        assert recorder._timer.isActive()
        
        recorder.stop_timer()
        
        assert recorder._timer is None


@pytest.fixture
def qapp():
    """Фикстура для QApplication."""
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
