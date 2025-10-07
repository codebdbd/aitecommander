"""Compatibility layer for legacy import `app.views.main_components.topbar.width_calculator`."""

from __future__ import annotations

from app.views.main_components.ui.topbar.width_calculator import (
    WidthCalculator as _ModernWidthCalculator,
)


class WidthCalculator(_ModernWidthCalculator):
    """Wrapper that restores legacy caching behavior."""

    def panel_width(self, panel, buttons, count):  # type: ignore[override]
        if count < 0:
            raise ValueError(f"count must be >= 0, got {count}")

        if panel is None or self._is_deleted(panel):
            return self.MIN_PANEL_WIDTH

        cache_key = (id(panel), count)

        if cache_key in self._panel_width_cache:
            self._cache_hits += 1
            self._panel_width_cache.move_to_end(cache_key)
            return self._panel_width_cache[cache_key]

        self._cache_misses += 1

        # Preserve counters before calling super() to avoid double counting
        saved_hits = self._cache_hits
        saved_misses = self._cache_misses

        result = super().panel_width(panel, buttons, count)

        # Restore counters after calling super()
        self._cache_hits = saved_hits
        self._cache_misses = saved_misses

        if len(self._panel_width_cache) >= self.CACHE_MAX_SIZE:
            self._panel_width_cache.popitem(last=False)

        self._panel_width_cache[cache_key] = result
        return result


__all__ = ["WidthCalculator"]
