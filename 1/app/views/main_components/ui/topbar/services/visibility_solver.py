from __future__ import annotations

import logging

from ..models.layout_context import LayoutContext
from ..models.panel_state import PanelState
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


class VisibilitySolver:

    def __init__(
        self, width_calculator: WidthCalculator, use_binary_search: bool = False
    ) -> None:
        self._width_calculator = width_calculator
        self._use_binary_search = use_binary_search

    def compute_visible_counts(self, ctx: LayoutContext) -> dict[str, int]:
        if self._use_binary_search:
            return self._compute_with_binary_search(ctx)
        return self._compute_greedy(ctx)

    def _compute_greedy(self, ctx: LayoutContext) -> dict[str, int]:
        panel_states = list(ctx.panel_states)
        counts: dict[str, int] = {
            state.definition.label: state.max_visible for state in panel_states
        }
        minimums: dict[str, int] = {
            state.definition.label: state.min_visible for state in panel_states
        }

        total_steps = sum(
            counts[label] - minimums[label] for label in counts if counts[label] > 0
        )
        steps = 0
        while (
            self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            > ctx.width
            and steps < total_steps
        ):
            steps += 1
            for state in panel_states:
                label = state.definition.label
                if counts[label] > minimums[label]:
                    counts[label] -= 1
                    break

        if (
            self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            > ctx.width
        ):
            for label in counts:
                counts[label] = minimums[label]

        return counts

    def _compute_with_binary_search(self, ctx: LayoutContext) -> dict[str, int]:
        panel_states = list(ctx.panel_states)

        minimums: dict[str, int] = {
            state.definition.label: state.min_visible for state in panel_states
        }
        maximums: dict[str, int] = {
            state.definition.label: state.max_visible for state in panel_states
        }
        min_total = sum(minimums.values())
        max_total = sum(maximums.values())

        if min_total == max_total:
            return minimums.copy()

        left, right = min_total, max_total
        best_total = min_total

        while left <= right:
            mid = (left + right) // 2
            counts = self._distribute_buttons(panel_states, mid, minimums, maximums)

            total_width = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )

            if total_width <= ctx.width:
                best_total = mid
                left = mid + 1
            else:
                right = mid - 1

        return self._distribute_buttons(panel_states, best_total, minimums, maximums)

    def _distribute_buttons(
        self,
        panel_states: list[PanelState],
        total: int,
        minimums: dict[str, int],
        maximums: dict[str, int],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        remaining = total

        for state in panel_states:
            label = state.definition.label
            counts[label] = minimums[label]
            remaining -= minimums[label]

        for state in panel_states:
            label = state.definition.label
            available = maximums[label] - minimums[label]
            to_add = min(available, remaining)
            counts[label] += to_add
            remaining -= to_add

            if remaining <= 0:
                break

        return counts
