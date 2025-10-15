"""Сервис применения гистерезиса к изменениям layout."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..models.topbar_constants import TOPBAR_CONSTANTS as C

if TYPE_CHECKING:
    from ..models.layout_context import LayoutContext
    from .width_calculator import WidthCalculator


class HysteresisService:
    """Применяет гистерезис для предотвращения частых переключений layout."""

    def __init__(self, width_calculator: WidthCalculator) -> None:
        self._width_calculator = width_calculator

    def apply_hysteresis(
        self,
        ctx: LayoutContext,
        counts: dict[str, int],
        last_applied: tuple[int, ...] | None,
        panel_labels: tuple[str, ...],
    ) -> dict[str, int]:
        """
        Применить гистерезис к новым counts.
        
        Если разница между новым и предыдущим layout меньше порога,
        оставить предыдущий layout.
        """
        if last_applied is None:
            return counts

        try:
            prev_counts = {
                label: last_applied[i] for i, label in enumerate(panel_labels)
            }
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
            except Exception:
                spacing = 6

            threshold = max(
                C.HYSTERESIS_THRESHOLD_BASE,
                spacing * C.HYSTERESIS_SPACING_MULTIPLIER,
            )

            if abs(slack_new) < threshold and abs(slack_prev) < threshold:
                return prev_counts
        except Exception:
            pass

        return counts
