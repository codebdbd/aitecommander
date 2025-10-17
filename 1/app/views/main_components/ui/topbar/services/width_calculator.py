from __future__ import annotations

import logging
import weakref
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

from ..models.panel_state import PanelState
from ..models.topbar_constants import TOPBAR_CONSTANTS as C
from ..utils.qt_utils import is_deleted

logger = logging.getLogger(__name__)


class WidthCalculator(QObject):
    """Compute panel widths and the overall top-bar budget.

    Fix: add named constants for former magic numbers and cache results.
    Uses weakref for automatic widget lifetime tracking.
    """

    # Use centralized constants
    MIN_PANEL_WIDTH = C.MIN_PANEL_WIDTH
    DEFAULT_BUTTON_SIZE = C.DEFAULT_BUTTON_SIZE
    CACHE_MAX_SIZE = C.CACHE_MAX_SIZE

    def __init__(
        self, button_size: int = DEFAULT_BUTTON_SIZE, parent: QObject | None = None
    ):
        super().__init__(parent)
        self._button_size = button_size
        # Use weakref-based cache: key is (weakref, count), value is width
        # weakref automatically becomes dead when widget is destroyed
        self._panel_width_cache: OrderedDict[tuple[Any, int], int] = OrderedDict()
        # Track finalizers for cleanup
        self._finalizers: dict[int, weakref.finalize] = {}
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
        if isinstance(obj, weakref.ref):
            return obj() is None
        return is_deleted(obj)

    def clear_cache(self) -> None:
        """Clear the panel-width cache.

        Fix: allow manual cache reset, e.g. after configuration or button-size changes.
        """
        self._panel_width_cache.clear()
        # Clear all finalizers
        for finalizer in self._finalizers.values():
            finalizer.detach()
        self._finalizers.clear()
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

        # Find keys where the weakref points to this panel
        keys_to_remove = [
            k
            for k in self._panel_width_cache
            if isinstance(k[0], weakref.ref) and k[0]() is panel
        ]

        for key in keys_to_remove:
            del self._panel_width_cache[key]

        # Remove finalizer if exists
        panel_id = id(panel)
        if panel_id in self._finalizers:
            self._finalizers[panel_id].detach()
            del self._finalizers[panel_id]

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
        except (RuntimeError, AttributeError):
            # Layout deleted or contentsMargins() unavailable
            pass
        try:
            import PyQt6.QtWidgets as _qtw

            if isinstance(bg, _qtw.QFrame):
                try:
                    fw = int(bg.frameWidth())
                except (RuntimeError, AttributeError, TypeError):
                    # Frame deleted, frameWidth() unavailable, or conversion failed
                    fw = 0
                total += max(0, fw * 2)
        except (ImportError, RuntimeError, AttributeError):
            # Import failed, bg deleted, or isinstance check failed
            pass
        try:
            pm = panel.contentsMargins()
            total += pm.left() + pm.right()
        except (RuntimeError, AttributeError):
            # Panel deleted or contentsMargins() unavailable
            pass
        return total

    def _register_panel_cleanup(self, panel: QWidget, panel_ref: weakref.ref) -> None:
        """Register cleanup callback for when panel is destroyed."""
        panel_id = id(panel)
        if panel_id in self._finalizers:
            return  # Already registered

        def cleanup():
            """Remove all cache entries for this panel."""
            keys_to_remove = [
                k for k in list(self._panel_width_cache.keys()) if k[0] is panel_ref
            ]
            for key in keys_to_remove:
                self._panel_width_cache.pop(key, None)
            self._finalizers.pop(panel_id, None)
            logger.debug(
                "Auto-cleaned %d cache entries for destroyed panel", len(keys_to_remove)
            )

        # Use weakref.finalize for automatic cleanup
        finalizer = weakref.finalize(panel, cleanup)
        self._finalizers[panel_id] = finalizer

    def panel_width(
        self, panel: QWidget | None, buttons: list[QToolButton], count: int
    ) -> int:
        """Calculate panel width based on visible buttons."""
        # Этап 1: Валидация параметров
        if not self._validate_and_prepare(panel, buttons, count):
            return self.MIN_PANEL_WIDTH
        
        # Этап 2: Работа с кэшем
        panel_ref, cache_key = self._prepare_cache_key(panel, count)
        cached_result = self._check_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Этап 3: Регистрация очистки кэша
        self._register_panel_cleanup(panel, panel_ref)
        
        # Этап 4: Вычисление ширины
        result = self._calculate_panel_width(panel, buttons, count)
        
        # Этап 5: Сохранение в кэш
        self._save_to_cache(cache_key, result)
        
        return result

    def _validate_and_prepare(self, panel: QWidget | None, buttons: list[QToolButton], count: int) -> bool:
        """Validate parameters and check if calculation can proceed."""
        if not self._validate_panel_width_params(buttons, count):
            return False
        
        if not panel or is_deleted(panel):
            return False
            
        return True
    
    def _prepare_cache_key(self, panel: QWidget, count: int) -> tuple[weakref.ref, int]:
        """Prepare cache key and clean stale entries."""
        panel_ref = weakref.ref(panel)
        cache_key = (panel_ref, count)
        self._clean_stale_entries()
        return panel_ref, cache_key
    
    def _check_cache(self, cache_key: tuple[weakref.ref, int]) -> int | None:
        """Check if result is in cache."""
        if cache_key in self._panel_width_cache:
            self._cache_hits += 1
            self._panel_width_cache.move_to_end(cache_key)
            return self._panel_width_cache[cache_key]
        self._cache_misses += 1
        return None
    
    def _calculate_panel_width(self, panel: QWidget, buttons: list[QToolButton], count: int) -> int:
        """Calculate panel width based on visible buttons."""
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

        return max(self.MIN_PANEL_WIDTH, total)
    
    def _save_to_cache(self, cache_key: tuple[weakref.ref, int], result: int) -> None:
        """Save result to cache."""
        # Evict oldest entry if cache is full
        if len(self._panel_width_cache) >= self.CACHE_MAX_SIZE:
            self._panel_width_cache.popitem(last=False)

        self._panel_width_cache[cache_key] = result

    def _clean_stale_entries(self) -> None:
        """Remove cache entries where weakref is dead (widget destroyed)."""
        keys_to_remove = [
            k
            for k in self._panel_width_cache
            if isinstance(k[0], weakref.ref) and k[0]() is None
        ]
        for key in keys_to_remove:
            del self._panel_width_cache[key]
        if keys_to_remove:
            logger.debug("Cleaned %d stale cache entries", len(keys_to_remove))

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        """Event filter to auto-invalidate cache on style/font changes."""
        if event is None:
            return False

        # Invalidate cache on events that affect widget geometry
        if event.type() in (
            QEvent.Type.StyleChange,
            QEvent.Type.FontChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationFontChange,
        ):
            if isinstance(watched, QWidget):
                removed = self.invalidate_cache_for_panel(watched)
                if removed > 0:
                    logger.debug(
                        "Auto-invalidated %d cache entries for panel after %s",
                        removed,
                        event.type().name,
                    )

        return super().eventFilter(watched, event)

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
                    # Clamp to available buttons to keep estimation
                    # consistent with apply phase
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
