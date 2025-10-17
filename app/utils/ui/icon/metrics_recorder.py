"""Icon metrics recording and reporting.

Separates metrics collection from path service for better modularity.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

try:
    from PyQt6.QtCore import QTimer
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

logger = logging.getLogger(__name__)


class IconMetricsRecorder:
    """Records and reports icon loading metrics.
    
    Supports both manual logging and automatic periodic logging via QTimer.
    """

    def __init__(self, report_interval: float = 60.0, use_qtimer: bool = False):
        """Initialize metrics recorder.
        
        Args:
            report_interval: Interval in seconds between automatic reports.
            use_qtimer: If True and Qt is available, use QTimer for periodic logging.
                       Note: QTimer will be created lazily when QApplication is available.
        """
        self._metrics_lock = threading.Lock()
        self._report_interval = report_interval
        self._last_report_time: float = 0.0
        self._timer: Optional[QTimer] = None
        self._timer_pending = False
        self._use_qtimer = use_qtimer
        
        # Metrics storage (delegates to CacheMetrics internally)
        from .metrics import CacheMetrics
        self._cache_metrics = CacheMetrics()
        
        # QTimer will be created lazily on first use (when QApplication exists)
        self._ensure_qtimer()

    def record_hit(self) -> None:
        """Record cache hit."""
        self._cache_metrics.record_hit()

    def record_miss(self) -> None:
        """Record cache miss."""
        self._cache_metrics.record_miss()

    def record_miss_without_increment(self, load_time: float = 0.0) -> None:
        """Record load time without incrementing miss counter.
        
        Args:
            load_time: Time taken to load in seconds.
        """
        self._cache_metrics.record_miss_without_increment(load_time)

    def record_actual_miss(self, load_time: float = 0.0) -> None:
        """Record actual miss (increment miss counter).
        
        Args:
            load_time: Time taken to load in seconds.
        """
        self._cache_metrics.record_actual_miss(load_time)

    def record_disk_load(self, load_time: float = 0.0) -> None:
        """Record disk load operation.
        
        Args:
            load_time: Time taken to load from disk in seconds (optional).
        """
        # CacheMetrics.record_disk_load() doesn't take load_time parameter
        self._cache_metrics.record_disk_load()
        # Record load time separately if provided
        if load_time > 0:
            self._cache_metrics.record_miss_without_increment(load_time)

    def record_not_found(self) -> None:
        """Record icon not found."""
        self._cache_metrics.record_not_found()

    def get_stats(self) -> dict[str, Any]:
        """Get current metrics statistics.
        
        Returns:
            Dictionary with metrics data.
        """
        return self._cache_metrics.get_stats()

    def maybe_log_metrics(self, config: Any | None = None) -> None:
        """Log metrics if interval has passed.
        
        Also sets up QTimer lazily if use_qtimer was requested.
        
        Args:
            config: Optional config object for interval. If None, uses default.
        """
        # Lazy QTimer setup (after QApplication is created)
        self._ensure_qtimer()
        
        # Get interval from config or use default
        if config is not None:
            try:
                interval = float(getattr(config, "icon_metrics_report_interval_s", self._report_interval))
            except (TypeError, ValueError, AttributeError):
                interval = self._report_interval
        else:
            interval = self._report_interval

        now = time.time()
        
        should_log = False
        with self._metrics_lock:
            if now - self._last_report_time >= interval:
                self._last_report_time = now
                should_log = True
        if not should_log:
            # Retry QTimer setup later in case QApplication appears after initial call.
            self._ensure_qtimer()
            return

        # Log outside lock to avoid blocking
        try:
            stats = self.get_stats()
            logger.info(
                "Icon metrics: hits=%s misses=%s hit_rate=%s disk_loads=%s "
                "not_found=%s avg_load_time=%s load_count=%s uptime=%s",
                stats.get("hits"),
                stats.get("misses"),
                stats.get("hit_rate"),
                stats.get("disk_loads"),
                stats.get("not_found"),
                stats.get("avg_load_time"),
                stats.get("load_count"),
                stats.get("uptime"),
            )
        except Exception:
            logger.exception("Failed to log icon metrics")

    def reset(self) -> None:
        """Reset all metrics."""
        self._cache_metrics.reset()
        with self._metrics_lock:
            self._last_report_time = 0.0

    def _setup_qtimer(self) -> None:
        """Setup QTimer for periodic logging (called from GUI thread).
        
        Must be called after QApplication is created.
        """
        if not QT_AVAILABLE or not self._use_qtimer:
            return
        
        # Check if QApplication exists
        try:
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                logger.debug("IconMetricsRecorder: QApplication not yet created, deferring QTimer setup")
                return
            if QThread.currentThread() != app.thread():
                logger.debug("IconMetricsRecorder: QTimer setup requested outside GUI thread, deferring")
                return
        except Exception:
            return
        
        try:
            self._timer = QTimer(parent=app)
            self._timer.timeout.connect(self._on_timer)
            self._timer.start(int(self._report_interval * 1000))  # Convert to ms
            logger.debug("IconMetricsRecorder: QTimer started with interval %.1fs", self._report_interval)
        except Exception:
            logger.exception("Failed to setup QTimer for metrics logging")

    def _on_timer(self) -> None:
        """Timer callback - log metrics without checking interval."""
        try:
            stats = self.get_stats()
            logger.info(
                "Icon metrics (QTimer): hits=%s misses=%s hit_rate=%s disk_loads=%s "
                "not_found=%s avg_load_time=%s load_count=%s uptime=%s",
                stats.get("hits"),
                stats.get("misses"),
                stats.get("hit_rate"),
                stats.get("disk_loads"),
                stats.get("not_found"),
                stats.get("avg_load_time"),
                stats.get("load_count"),
                stats.get("uptime"),
            )
        except Exception:
            logger.exception("Failed to log icon metrics from QTimer")

    def stop_timer(self) -> None:
        """Stop QTimer if running."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
            logger.debug("IconMetricsRecorder: QTimer stopped")

    def _ensure_qtimer(self) -> None:
        """Ensure QTimer is created when requested."""
        if not self._use_qtimer or self._timer is not None or not QT_AVAILABLE:
            return
        try:
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
            from app.utils.ui.qt.gui_exec import run_in_gui_thread_sync

            app = QApplication.instance()
            if app is None:
                logger.debug("IconMetricsRecorder: QApplication not yet created, deferring timer setup")
                return
            if QThread.currentThread() == app.thread():
                self._setup_qtimer()
                return
            if self._timer_pending:
                return

            def _start_timer() -> None:
                self._timer_pending = False
                self._setup_qtimer()

            self._timer_pending = True
            run_in_gui_thread_sync(_start_timer)
        except Exception:
            logger.debug("IconMetricsRecorder: failed to schedule QTimer setup", exc_info=True)
            self._timer_pending = False
