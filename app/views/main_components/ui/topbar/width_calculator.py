from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

from .panel_state import PanelState

logger = logging.getLogger(__name__)


class WidthCalculator:
    """Compute panel widths and the overall top-bar budget.

    Fix: add named constants for former magic numbers and cache results.
    """

    MIN_PANEL_WIDTH = 50  # Minimal panel width in pixels
    DEFAULT_BUTTON_SIZE = 32  # Default button size
    CACHE_MAX_SIZE = 100  # Maximum cache size

    def __init__(self, button_size: int = DEFAULT_BUTTON_SIZE):
        self._button_size = button_size
        # Fix: LRU cache for ``panel_width`` — key: (panel_id, count), value: width
        # ``OrderedDict`` provides O(1) access and preserves insertion order for LRU
        self._panel_width_cache: OrderedDict[tuple[int, int], int] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0

    def _safe_get(self, obj: Any | None, name: str) -> Any | None:
        """Safely read an attribute from ``obj``.

        Fix: use ``Any`` instead of ``object`` for better typing fidelity.
        """
        if obj is None:
            return None
        try:
            return getattr(obj, name, None)
        except (RuntimeError, AttributeError):
            return None

    def _is_deleted(self, obj) -> bool:
        """Check whether a Qt object has been deleted."""
        try:
            from sip import isdeleted

            return isdeleted(obj)
        except ImportError:
            return False

    def clear_cache(self) -> None:
        """Clear the panel-width cache.

        Fix: allow manual cache reset, e.g. after configuration or button-size changes.
        """
        self._panel_width_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def invalidate_cache_for_panel(self, panel: QWidget) -> int:
        """Invalidate cached widths for a specific panel.

        Improvement note: selectively drop cache entries when a panel changes (e.g.
        stylesheet adjustments).

        Args:
            panel: Panel widget whose cache entries should be removed.

        Returns:
            Number of cache records that were removed.
        """
        if not panel or self._is_deleted(panel):
            return 0

        panel_id = id(panel)
        keys_to_remove = [k for k in self._panel_width_cache if k[0] == panel_id]

        for key in keys_to_remove:
            del self._panel_width_cache[key]

        return len(keys_to_remove)

    def get_cache_stats(self) -> dict[str, int]:
        """Return cache-usage statistics.

        Returns:
            Dictionary with keys: ``hits``, ``misses``, ``size``, ``hit_rate``.
        """
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._panel_width_cache),
            "hit_rate": int(hit_rate),
        }

    def _validate_panel_width_params(self, buttons, count):
        """Validate panel_width parameters."""
        if count < 0:
            raise ValueError(f"count must be >= 0, got {count}")

        if buttons is None:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "panel_width called with None buttons, returning MIN_PANEL_WIDTH"
            )
            return False
        return True

    def _get_button_width(self, w):
        """Calculate button width respecting size constraints."""
        try:
            hint_w = int(w.sizeHint().width())
        except (RuntimeError, AttributeError, ValueError):
            hint_w = 0
        try:
            max_w = int(w.maximumWidth()) if w.maximumWidth() > 0 else 0
        except (RuntimeError, AttributeError, ValueError):
            max_w = 0
        try:
            min_w = int(w.minimumWidth()) if w.minimumWidth() > 0 else 0
        except (RuntimeError, AttributeError, ValueError):
            min_w = 0
        btn_w = hint_w
        if max_w and min_w:
            btn_w = max(min_w, max_w)
        elif max_w:
            btn_w = max(btn_w, max_w)
        elif min_w:
            btn_w = max(btn_w, min_w)
        return max(self._button_size, btn_w)

    def _collect_widget_widths(self, layout, btn_set, safe_count):
        """Collect widths of widgets in layout."""
        included_widths: list[int] = []
        taken_target = 0
        count_items = layout.count()
        for i in range(count_items):
            item = layout.itemAt(i)
            w = item.widget()
            if w is None:
                continue
            if w in btn_set:
                if taken_target >= safe_count:
                    continue
                taken_target += 1
                included_widths.append(self._get_button_width(w))
            else:
                if w.isVisible():
                    try:
                        hint_w = int(w.sizeHint().width())
                    except (RuntimeError, AttributeError, ValueError):
                        hint_w = 0
                    included_widths.append(max(0, hint_w))
        return included_widths

    def _add_margins_and_borders(self, total, layout, bg, panel):
        """Add layout margins, frame borders, and panel margins to total."""
        try:
            lm = layout.contentsMargins()
            total += lm.left() + lm.right()
        except Exception:
            pass
        try:
            import PyQt6.QtWidgets as _qtw

            if isinstance(bg, _qtw.QFrame):
                try:
                    fw = int(bg.frameWidth())
                except Exception:
                    fw = 0
                total += max(0, fw * 2)
        except Exception:
            pass
        try:
            pm = panel.contentsMargins()
            total += pm.left() + pm.right()
        except Exception:
            pass
        return total

    def panel_width(
        self, panel: QWidget | None, buttons: list[QToolButton], count: int
    ) -> int:
        """Calculate panel width based on visible buttons.

        Args:
            panel: Panel widget.
            buttons: Panel buttons list (must not be ``None``).
            count: Number of visible buttons (>= 0).

        Returns:
            Panel width in pixels (>= ``MIN_PANEL_WIDTH``).

        Raises:
            ValueError: If ``count`` is negative.
        """
        if not self._validate_panel_width_params(buttons, count):
            return self.MIN_PANEL_WIDTH

        if not panel or self._is_deleted(panel):
            return self.MIN_PANEL_WIDTH

        cache_key = (id(panel), count)
        if cache_key in self._panel_width_cache:
            self._cache_hits += 1
            self._panel_width_cache.move_to_end(cache_key)
            return self._panel_width_cache[cache_key]

        self._cache_misses += 1

        safe_count = max(0, min(count, len(buttons)))
        if safe_count <= 0:
            return self.MIN_PANEL_WIDTH
        bg = self._safe_get(panel, "bg_frame")
        layout = bg.layout() if bg else None
        if not layout:
            return self.MIN_PANEL_WIDTH
        spacing = layout.spacing() or 0

        btn_set = set(buttons or [])
        included_widths = self._collect_widget_widths(layout, btn_set, safe_count)

        if not included_widths:
            return self.MIN_PANEL_WIDTH

        total = sum(included_widths) + spacing * max(0, len(included_widths) - 1)
        total = self._add_margins_and_borders(total, layout, bg, panel)

        result = max(self.MIN_PANEL_WIDTH, total)

        if len(self._panel_width_cache) >= self.CACHE_MAX_SIZE:
            self._panel_width_cache.popitem(last=False)

        self._panel_width_cache[cache_key] = result
        return result

    def total_width(
        self,
        top_bar: QLayout,
        search: QLineEdit | None,
        panel_states: Iterable[PanelState],
        counts: dict[str, int],
        min_search_width: int,
    ) -> int:
        panel_map = {state.widget: state for state in panel_states if state.widget}
        items: list[int] = []
        for index in range(top_bar.count()):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget:
                if widget is search:
                    items.append(min_search_width)
                    continue
                state = panel_map.get(widget)
                if state:
                    requested = counts.get(state.definition.label, 0)
                    # Clamp to available buttons to keep estimation consistent with apply phase
                    visible = max(0, min(requested, len(state.buttons)))
                    items.append(self.panel_width(widget, state.buttons, visible))
                elif widget.isVisible():
                    items.append(widget.sizeHint().width())
            else:
                spacer = item.spacerItem()
                if spacer is not None:
                    items.append(max(0, spacer.sizeHint().width()))
        spacing = top_bar.spacing() or 0
        total = sum(items) + spacing * max(0, len(items) - 1)
        margins = top_bar.contentsMargins()
        total += margins.left() + margins.right()

        return total
