"""Service for managing search widget constraints and layout behavior."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from PyQt6.QtWidgets import QLayout, QLineEdit

from ..models.layout_context import LayoutContext
from ..models.panel_state import PanelState
from ..models.topbar_constants import TOPBAR_CONSTANTS as C

logger = logging.getLogger(__name__)


class SearchWidgetManager:
    """Manage search widget width constraints and stretch behavior.
    
    Responsibilities:
    - Clamp search widget width based on available space
    - Freeze search width when container is hidden
    - Enforce stretch factors in layout
    """

    def __init__(self, width_calculator) -> None:
        self._width_calculator = width_calculator
        self._max_widget_width = C.MAX_WIDGET_WIDTH
        self._min_panel_width = C.MIN_PANEL_WIDTH

    def clamp_width(
        self,
        ctx: LayoutContext,
        applied_counts: Mapping[str, int],
        min_search_width: int,
    ) -> int | None:
        """Clamp search widget width based on occupied space.
        
        Args:
            ctx: Layout context with search widget and panel states
            applied_counts: Visible button counts per panel
            min_search_width: Minimum allowed search width
            
        Returns:
            New minimum search width if changed, None otherwise
        """
        search = ctx.search
        if not isinstance(search, QLineEdit):
            return None

        try:
            state_map = self._build_state_map(ctx)
            occupied, search_index = self._calculate_occupied_space(
                ctx, applied_counts, state_map, search
            )

            min_search = int(min_search_width)
            cur_min = int(search.minimumWidth()) if search.minimumWidth() > 0 else 0
            if cur_min > 0:
                min_search = max(min_search, cur_min)

            self._apply_constraints(search, search_index, ctx.top_bar, min_search)
            return min_search
        except Exception:
            logger.debug("SearchWidgetManager: failed to clamp width", exc_info=True)
            return None

    def freeze_width(self, search: QLineEdit | None, width: int) -> None:
        """Freeze search widget to a fixed width.
        
        Args:
            search: Search widget to freeze
            width: Fixed width to apply
        """
        if not isinstance(search, QLineEdit):
            return
        try:
            search.setMaximumWidth(width)
            search.setMinimumWidth(width)
        except Exception:
            pass

    def enforce_stretches(self, top_bar: QLayout, search: QLineEdit | None) -> None:
        """Enforce stretch factors: search=1, all others=0.
        
        Args:
            top_bar: Layout to update
            search: Search widget that should stretch
        """
        try:
            count = top_bar.count()
            search_index = -1
            for i in range(count):
                it = top_bar.itemAt(i)
                w = it.widget()
                if w is not None and isinstance(search, QLineEdit) and w is search:
                    search_index = i
                try:
                    top_bar.setStretch(i, 0)
                except Exception:
                    logger.debug(
                        "SearchWidgetManager: setStretch(0) failed at index %s",
                        i,
                        exc_info=True,
                    )
            if search_index >= 0:
                try:
                    top_bar.setStretch(search_index, 1)
                except Exception:
                    logger.debug(
                        "SearchWidgetManager: setStretch(1) failed at index %s",
                        search_index,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("SearchWidgetManager: enforce_stretches failed", exc_info=True)

    def _build_state_map(self, ctx: LayoutContext) -> dict:
        """Build mapping of panel widgets to their states."""
        return {
            state.widget: state
            for state in ctx.panel_states
            if state.widget is not None
        }

    def _calculate_spacer_width(self, item) -> int:
        """Calculate width of a spacer item."""
        spacer = item.spacerItem()
        if spacer is not None:
            sp_w = max(0, spacer.sizeHint().width())
            if sp_w > 0:
                return sp_w
        return 0

    def _calculate_panel_width(
        self, state: PanelState, applied_counts: Mapping[str, int]
    ) -> int:
        """Calculate width of a panel based on visible buttons."""
        vis = max(0, applied_counts.get(state.definition.label, 0))
        if vis <= 0:
            return 0
        try:
            w_panel = int(
                self._width_calculator.panel_width(state.widget, state.buttons, vis)
            )
        except Exception:
            w_panel = 0
        return max(self._min_panel_width, w_panel)

    def _calculate_widget_width(self, widget) -> int:
        """Calculate width of a non-panel widget."""
        if not widget.isVisible():
            return 0
        try:
            w_hint = int(widget.sizeHint().width())
        except Exception:
            w_hint = 0
        return w_hint if w_hint > 0 else 0

    def _calculate_occupied_space(
        self,
        ctx: LayoutContext,
        applied_counts: Mapping[str, int],
        state_map: dict,
        search: QLineEdit,
    ) -> tuple[int, int]:
        """Calculate total occupied space excluding search widget.
        
        Returns:
            Tuple of (occupied_width, search_index)
        """
        occupied = 0
        top_bar = ctx.top_bar
        count = top_bar.count()
        occupy_items = 0
        search_index = -1

        for index in range(count):
            item = top_bar.itemAt(index)
            widget = item.widget()

            if widget is None:
                sp_w = self._calculate_spacer_width(item)
                if sp_w > 0:
                    occupied += sp_w
                    occupy_items += 1
                continue

            if widget is search:
                search_index = index
                continue

            state = state_map.get(widget)
            if state:
                w_use = self._calculate_panel_width(state, applied_counts)
            else:
                w_use = self._calculate_widget_width(widget)

            if w_use > 0:
                occupied += w_use
                occupy_items += 1

        spacing = top_bar.spacing() or 0
        occupied += spacing * max(0, occupy_items - 1)
        margins = top_bar.contentsMargins()
        occupied += margins.left() + margins.right()

        return occupied, search_index

    def _apply_constraints(
        self, search: QLineEdit, search_index: int, top_bar: QLayout, min_search: int
    ) -> None:
        """Apply width and stretch constraints to search widget."""
        if search_index >= 0:
            try:
                top_bar.setStretch(search_index, 1)
            except Exception:
                pass

        if search.minimumWidth() != min_search:
            search.setMinimumWidth(min_search)
        if search.maximumWidth() != self._max_widget_width:
            search.setMaximumWidth(self._max_widget_width)
