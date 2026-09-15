"""Service applying hysteresis to top bar layout changes."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
        return counts
