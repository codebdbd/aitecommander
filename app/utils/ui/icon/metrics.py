"""Module for working with icon cache metrics"""

import time
from collections import deque
from typing import Any

from .lock_manager import acquire_metrics_lock


class CacheMetrics:
    """Icon cache metrics."""

    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.disk_loads = 0  # Counter of successful disk loads
        self.not_found = 0  # Counter of files that were not found
        # Optimize load time storage to reduce load
        self.load_times: deque[float] = deque(maxlen=100)
        # Add aggregated metrics for more accurate average time calculation
        self.total_load_time = 0.0
        self.load_count = 0
        self.start_time = time.time()
        # Use centralized locking system
        # self._lock replaced with lock_manager

    def record_hit(self) -> None:
        """Record a hit."""
        with acquire_metrics_lock():
            self.hits += 1

    def record_miss(self, load_time=0.0) -> None:
        """Record a miss."""
        with acquire_metrics_lock():
            self.misses += 1
            if load_time > 0:
                self.load_times.append(load_time)
                self.total_load_time += load_time
                self.load_count += 1

    def record_miss_without_increment(self, load_time=0.0) -> None:
        """Record load time without incrementing miss counter."""
        with acquire_metrics_lock():
            if load_time > 0:
                self.load_times.append(load_time)
                self.total_load_time += load_time
                self.load_count += 1

    def record_actual_miss(self, load_time=0.0) -> None:
        """Record actual miss (increment miss counter)."""
        with acquire_metrics_lock():
            self.misses += 1
            if load_time > 0:
                self.load_times.append(load_time)
                self.total_load_time += load_time
                self.load_count += 1

    def record_disk_load(self) -> None:
        """Record successful disk load."""
        with acquire_metrics_lock():
            self.disk_loads += 1

    def record_not_found(self) -> None:
        """Record file that was not found."""
        with acquire_metrics_lock():
            self.not_found += 1

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with acquire_metrics_lock():
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

            # Calculate average load time using aggregated metrics
            # This gives a more accurate result, especially with a large number of requests
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
        """Reset metrics."""
        with acquire_metrics_lock():
            self.hits = 0
            self.misses = 0
            self.disk_loads = 0
            self.not_found = 0
            self.load_times.clear()
            self.total_load_time = 0.0
            self.load_count = 0
            self.start_time = time.time()
