"""Service applying hysteresis to top bar layout changes."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.views.main_components.ui.topbar.models.topbar_constants import (
    TOPBAR_CONSTANTS as C,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..models.layout_context import LayoutContext
    from .width_calculator import WidthCalculator


class HysteresisService:
    """Apply hysteresis to reduce layout thrashing on small width changes."""

    def __init__(self, width_calculator: WidthCalculator) -> None:
        """Initialize service.

        Args:
            width_calculator: Helper to compute total layout width.
        """
        self._width_calculator = width_calculator

    def apply_hysteresis(
        self,
        ctx: LayoutContext,
        counts: dict[str, int],
        last_applied: tuple[int, ...] | None,
        panel_labels: tuple[str, ...],
    ) -> dict[str, int]:
        """Return possibly adjusted counts when changes are below a threshold."""
        if last_applied is None:
            return counts

        try:
            prev_counts = {label: last_applied[i] for i, label in enumerate(panel_labels)}
            total_new = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                ctx.panel_states,
                counts,
                ctx.min_search_width,
            )
            total_prev = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                ctx.panel_states,
                prev_counts,
                ctx.min_search_width,
            )

            slack_new = ctx.width - total_new
            slack_prev = ctx.width - total_prev

            try:
                spacing = int(ctx.top_bar.spacing() or 0)
            except (RuntimeError, AttributeError, TypeError):
                spacing = C.LAYOUT_SPACING_FALLBACK

            threshold = max(
                C.HYSTERESIS_THRESHOLD_BASE,
                spacing * C.HYSTERESIS_SPACING_MULTIPLIER,
            )

            if abs(slack_new) < threshold and abs(slack_prev) < threshold:
                return prev_counts
        except (RuntimeError, AttributeError, TypeError, ValueError):
            logger.debug(
                "HysteresisService: hysteresis calculation failed, using new counts"
            )

        return counts
