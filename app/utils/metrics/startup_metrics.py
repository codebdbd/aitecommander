# app/utils/metrics/startup_metrics.py
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class _Span:
    name: str
    start: float
    end: Optional(float) = None  # type: ignore[valid-type]

    @property
    def duration(self) -> Optional[float]:
        if self.end is None:
            return None
        return self.end - self.start


class StartupMetrics:
    """Простой сборщик метрик старта приложения.

    - Поддерживает именованные спаны (start/stop) и контекстный менеджер time_span().
    - Потокобезопасен (на случай фоновых операций).
    - Может вывести сводку в лог в конце старта.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._open_spans: Dict[str, _Span] = {}
        self._completed: List[_Span] = []
        self._marks: List[str] = []
        self._t0 = time.perf_counter()

    def reset(self) -> None:
        with self._lock:
            self._open_spans.clear()
            self._completed.clear()
            self._marks.clear()
            self._t0 = time.perf_counter()

    def start(self, name: str) -> None:
        now = time.perf_counter()
        with self._lock:
            if name in self._open_spans:
                # Позволяем вложенные одинаковые имена: добавляем суффикс
                i = 2
                base = name
                while name in self._open_spans:
                    name = f"{base}#{i}"
                    i += 1
            self._open_spans[name] = _Span(name=name, start=now)

    def stop(self, name: str) -> None:
        now = time.perf_counter()
        with self._lock:
            span = self._open_spans.pop(name, None)
            if span is None:
                return
            span.end = now
            self._completed.append(span)

    @contextmanager
    def time_span(self, name: str):
        self.start(name)
        try:
            yield
        finally:
            self.stop(name)

    def mark(self, label: str) -> None:
        with self._lock:
            self._marks.append(label)

    def flush_log(self, logger: Optional[logging.Logger] = None, *, level: int = logging.INFO) -> None:
        """Вывести сводку метрик старта в лог.

        Формат:
        - Total startup time
        - Список спанов по убыванию времени
        - Маркеры (события)
        """
        lg = logger or logging.getLogger(__name__)
        with self._lock:
            total = time.perf_counter() - self._t0
            # Отсортируем по длительности, неопределённые (незакрытые) в конец
            completed = sorted(
                self._completed,
                key=lambda s: (s.duration if s.duration is not None else -1.0),
                reverse=True,
            )
            lg.log(level, "Startup metrics: total %.1f ms", total * 1000.0)
            if completed:
                for s in completed:
                    if s.duration is None:
                        lg.log(level, "  %-50s : (open)", s.name)
                    else:
                        lg.log(level, "  %-50s : %7.1f ms", s.name, s.duration * 1000.0)
            else:
                lg.log(level, "  (no spans recorded)")
            if self._marks:
                lg.log(level, "Startup marks (%d): %s", len(self._marks), ", ".join(self._marks))


# Глобальный синглтон
_metrics_singleton: Optional[StartupMetrics] = None
_metrics_lock = threading.Lock()


def get_metrics() -> StartupMetrics:
    global _metrics_singleton
    if _metrics_singleton is not None:
        return _metrics_singleton
    with _metrics_lock:
        if _metrics_singleton is None:
            _metrics_singleton = StartupMetrics()
        return _metrics_singleton
