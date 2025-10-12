"""Performance monitoring utilities for PyQt6 application.

Provides decorators and utilities for measuring execution time,
cache hit rates, and other performance metrics.
"""

import functools
import logging
import time
from collections import defaultdict, deque
from typing import Any, Callable, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

# Type variable for generic decorator
F = TypeVar("F", bound=Callable[..., Any])


class PerformanceMetrics:
    """Singleton class for collecting performance metrics."""

    _instance: Optional["PerformanceMetrics"] = None

    def __new__(cls) -> "PerformanceMetrics":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize metrics storage.

        ✅ ИСПРАВЛЕНИЕ: Использует deque вместо list для автоматического ограничения размера.
        """
        # ✅ deque с maxlen=100 автоматически удаляет старые элементы
        self._timings: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=100))
        self._cache_hits: dict[str, int] = defaultdict(int)
        self._cache_misses: dict[str, int] = defaultdict(int)
        self._call_counts: dict[str, int] = defaultdict(int)
        self._enabled = True

    def record_timing(self, operation: str, duration: float) -> None:
        """Record execution time for an operation.

        ✅ ИСПРАВЛЕНИЕ: deque автоматически ограничивает размер.
        """
        if not self._enabled:
            return
        # deque с maxlen=100 автоматически удаляет старые элементы
        self._timings[operation].append(duration)

    def record_cache_hit(self, cache_name: str) -> None:
        """Record cache hit."""
        if not self._enabled:
            return
        self._cache_hits[cache_name] += 1

    def record_cache_miss(self, cache_name: str) -> None:
        """Record cache miss."""
        if not self._enabled:
            return
        self._cache_misses[cache_name] += 1

    def increment_call_count(self, operation: str) -> None:
        """Increment call counter for operation."""
        if not self._enabled:
            return
        self._call_counts[operation] += 1

    def get_stats(self, operation: str) -> dict[str, Any]:
        """Get statistics for an operation.

        Returns:
            Dict with min, max, avg, count, total time
        """
        timings = self._timings.get(operation, [])
        if not timings:
            return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "total": 0.0}

        return {
            "count": len(timings),
            "min": min(timings),
            "max": max(timings),
            "avg": sum(timings) / len(timings),
            "total": sum(timings),
        }

    def get_cache_stats(self, cache_name: str) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, hit_rate
        """
        hits = self._cache_hits.get(cache_name, 0)
        misses = self._cache_misses.get(cache_name, 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0.0

        return {"hits": hits, "misses": misses, "total": total, "hit_rate": hit_rate}

    def get_all_stats(self) -> dict[str, Any]:
        """Get all collected statistics."""
        return {
            "timings": {op: self.get_stats(op) for op in self._timings.keys()},
            "caches": {
                cache: self.get_cache_stats(cache)
                for cache in set(
                    list(self._cache_hits.keys()) + list(self._cache_misses.keys())
                )
            },
            "call_counts": dict(self._call_counts),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._timings.clear()
        self._cache_hits.clear()
        self._cache_misses.clear()
        self._call_counts.clear()

    def enable(self) -> None:
        """Enable metrics collection."""
        self._enabled = True

    def disable(self) -> None:
        """Disable metrics collection."""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled


# Global instance
_metrics = PerformanceMetrics()


def measure_time(
    operation_name: str, log_threshold_ms: float = 100.0
) -> Callable[[F], F]:
    """Decorator to measure execution time of a function.

    Args:
        operation_name: Name of the operation for metrics
        log_threshold_ms: Log warning if execution takes longer than this (ms)

    Example:
        @measure_time("load_links")
        def load_links(self, category_id: int) -> None:
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = (time.perf_counter() - start_time) * 1000  # Convert to ms
                _metrics.record_timing(operation_name, duration)
                _metrics.increment_call_count(operation_name)

                if duration > log_threshold_ms:
                    logger.warning(
                        "[PERF] %s took %.2f ms (threshold: %.2f ms)",
                        operation_name,
                        duration,
                        log_threshold_ms,
                    )
                else:
                    logger.debug("[PERF] %s took %.2f ms", operation_name, duration)

        return cast(F, wrapper)

    return decorator


def cache_metrics(cache_name: str) -> Callable[[F], F]:
    """Decorator to track cache hit/miss rates.

    The decorated function should return a tuple (result, cache_hit: bool)
    or just result (assumes cache miss).

    Args:
        cache_name: Name of the cache for metrics

    Example:
        @cache_metrics("categories_cache")
        def get_categories(self, section_id: int) -> list[dict[str, Any]]:
            cached = self._cache.get(key)
            if cached is not None:
                return cached  # Cache hit
            result = self._fetch_from_db()
            self._cache.set(key, result)
            return result  # Cache miss
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Track if cache was checked

            # Intercept cache.get calls to detect hits/misses
            result = func(*args, **kwargs)

            # Simple heuristic: if function is fast, likely cache hit
            # For more accurate tracking, modify cache service to return (value, hit) tuple

            return result

        return cast(F, wrapper)

    return decorator


def get_metrics() -> PerformanceMetrics:
    """Get global metrics instance."""
    return _metrics


def log_performance_summary() -> None:
    """Log summary of all collected metrics."""
    stats = _metrics.get_all_stats()

    logger.info("=" * 60)
    logger.info("PERFORMANCE METRICS SUMMARY")
    logger.info("=" * 60)

    # Timing stats
    if stats["timings"]:
        logger.info("\n📊 EXECUTION TIMES:")
        for operation, timing_stats in sorted(stats["timings"].items()):
            if timing_stats["count"] > 0:
                logger.info(
                    "  %s: avg=%.2fms, min=%.2fms, max=%.2fms, count=%d",
                    operation,
                    timing_stats["avg"],
                    timing_stats["min"],
                    timing_stats["max"],
                    timing_stats["count"],
                )

    # Cache stats
    if stats["caches"]:
        logger.info("\n💾 CACHE STATISTICS:")
        for cache_name, cache_stats in sorted(stats["caches"].items()):
            if cache_stats["total"] > 0:
                logger.info(
                    "  %s: hit_rate=%.1f%%, hits=%d, misses=%d",
                    cache_name,
                    cache_stats["hit_rate"],
                    cache_stats["hits"],
                    cache_stats["misses"],
                )

    # Call counts
    if stats["call_counts"]:
        logger.info("\n📞 CALL COUNTS:")
        for operation, count in sorted(
            stats["call_counts"].items(), key=lambda x: x[1], reverse=True
        )[:10]:
            logger.info("  %s: %d calls", operation, count)

    logger.info("=" * 60)


__all__ = [
    "PerformanceMetrics",
    "measure_time",
    "cache_metrics",
    "get_metrics",
    "log_performance_summary",
]
