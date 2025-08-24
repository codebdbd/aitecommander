"""Модуль для работы с метриками кэша иконок"""

import time
from collections import deque
from typing import Dict

from .lock_manager import acquire_metrics_lock


class CacheMetrics:
    """Метрики кеша иконок."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.disk_loads = 0  # Счетчик успешных загрузок с диска
        self.not_found = 0  # Счетчик файлов, которые не были найдены
        # Оптимизируем хранение времени загрузки для уменьшения нагрузки
        self.load_times = deque(maxlen=100)
        # Добавляем агрегированные метрики для более точного подсчета среднего времени
        self.total_load_time = 0.0
        self.load_count = 0
        self.start_time = time.time()
        # Используем централизованную систему блокировок
        # self._lock заменен на lock_manager

    def record_hit(self) -> None:
        """Записать хит."""
        with acquire_metrics_lock():
            self.hits += 1

    def record_miss(self, load_time=0.0) -> None:
        """Записать промах."""
        with acquire_metrics_lock():
            self.misses += 1
            if load_time > 0:
                self.load_times.append(load_time)
                self.total_load_time += load_time
                self.load_count += 1

    def record_miss_without_increment(self, load_time=0.0) -> None:
        """Записать время загрузки без увеличения счетчика miss."""
        with acquire_metrics_lock():
            if load_time > 0:
                self.load_times.append(load_time)
                self.total_load_time += load_time
                self.load_count += 1

    def record_actual_miss(self, load_time=0.0) -> None:
        """Записать реальный промах (увеличиваем счетчик miss)."""
        with acquire_metrics_lock():
            self.misses += 1
            if load_time > 0:
                self.load_times.append(load_time)
                self.total_load_time += load_time
                self.load_count += 1

    def record_disk_load(self) -> None:
        """Записать успешную загрузку с диска."""
        with acquire_metrics_lock():
            self.disk_loads += 1

    def record_not_found(self) -> None:
        """Записать файл, который не был найден."""
        with acquire_metrics_lock():
            self.not_found += 1

    def get_stats(self) -> Dict[str, any]:
        """Получить статистику кеша."""
        with acquire_metrics_lock():
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

            # Вычисляем среднее время загрузки с использованием агрегированных метрик
            # Это дает более точный результат, особенно при большом количестве запросов
            if self.load_count > 0:
                avg_load_time = self.total_load_time / self.load_count
            else:
                avg_load_time = 0

            uptime = time.time() - self.start_time

            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": f"{hit_rate:.2f}%",
                "disk_loads": self.disk_loads,
                "not_found": self.not_found,
                "avg_load_time": f"{avg_load_time:.4f}s",
                "uptime": f"{uptime:.2f}s",
                "load_count": self.load_count,
            }

    def reset(self) -> None:
        """Сбросить метрики."""
        with acquire_metrics_lock():
            self.hits = 0
            self.misses = 0
            self.disk_loads = 0
            self.not_found = 0
            self.load_times.clear()
            self.total_load_time = 0.0
            self.load_count = 0
            self.start_time = time.time()
