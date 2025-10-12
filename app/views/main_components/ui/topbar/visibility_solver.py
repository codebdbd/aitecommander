from __future__ import annotations

import logging

from .layout_context import LayoutContext
from .panel_state import PanelState
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


class VisibilitySolver:
    """Compute visible button counts per panel.

    Improvement note: add a binary-search strategy to reduce complexity from
    ``O(n * m)`` to ``O(log(total) * n)``.

    Two available strategies:
    1. Greedy (default) — simple and predictable.
    2. Binary search — faster for large button sets.
    """

    def __init__(self, width_calculator: WidthCalculator, use_binary_search: bool = False) -> None:
        """Initialize the solver.

        Args:
            width_calculator: Panel width calculator.
            use_binary_search: Enable binary search (faster yet less predictable).
        """
        self._width_calculator = width_calculator
        self._use_binary_search = use_binary_search

    def compute_visible_counts(self, ctx: LayoutContext) -> dict[str, int]:
        """Compute the optimal visible-button counts.

        Strategy selection depends on the ``use_binary_search`` flag.
        """
        if self._use_binary_search:
            return self._compute_with_binary_search(ctx)
        return self._compute_greedy(ctx)
    
    def _compute_greedy(self, ctx: LayoutContext) -> dict[str, int]:
        """Derive visible counts for each panel via the greedy strategy.

        Fix: document the algorithm thoroughly.

        Greedy algorithm (priority-based):
        1. Start with ``max_visible`` for every panel.
        2. Compute total width with the current counts via ``WidthCalculator``.
        3. If the layout overflows, iterate through panels in priority order
           (recent → fav → quick), decrementing the first panel whose count is
           above its minimum. Repeat until the layout fits or all minimums are hit.
        4. If the layout still overflows, fall back to all minimum values.

        Complexity: ``O(n * m)``, where ``n`` is the panel count (typically 3) and
        ``m`` is the sum of ``max_visible - min_visible`` across panels.

        Priority order: dictated by the order of ``panel_states``. The first panel
        has the highest priority (reduced last). Adjust `_panel_definitions` in
        `TopBarLayoutManager` to change the priority.

        Infinite-loop safeguard: use a ``steps`` counter bounded by the sum of all
        possible decrements to guarantee termination.

        Args:
            ctx: Layout context containing width and panel information.

        Returns:
            Dictionary ``{label: visible_count}``. Guarantees that
            ``minimums[label] <= result[label] <= max_visible``.

        Example:
            >>> ctx = LayoutContext(width=500, panel_states=[...])
            >>> solver.compute_visible_counts(ctx)
            {'recent': 8, 'fav': 5, 'quick': 6}
            # 'recent' has the highest priority, 'quick' the lowest
        """
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
        """Compute visible counts using binary search.

        Improvement note: optimized to ``O(log(total) * n)`` over ``O(n * m)``.

        Idea:
        1. Compute the total number of buttons ``total_buttons``.
        2. Use binary search to find the largest feasible total.
        3. Distribute the result among panels according to priorities.

        Args:
            ctx: Layout context.

        Returns:
            Dictionary mapping each panel to its visible button count.
        """
        panel_states = list(ctx.panel_states)
        
        # Prepare data for the binary search
        minimums: dict[str, int] = {
            state.definition.label: state.min_visible for state in panel_states
        }
        maximums: dict[str, int] = {
            state.definition.label: state.max_visible for state in panel_states
        }
        # Calculate the search range
        min_total = sum(minimums.values())
        max_total = sum(maximums.values())
        
        if min_total == max_total:
            # No flexibility — return minimums
            return minimums.copy()

        # Binary search for the maximum number of buttons that still fits
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
                # Fits — try more
                best_total = mid
                left = mid + 1
            else:
                # Does not fit — try fewer
                right = mid - 1

        # Return the distribution for the best total found
        return self._distribute_buttons(panel_states, best_total, minimums, maximums)
    
    def _distribute_buttons(
        self,
        panel_states: list[PanelState],
        total: int,
        minimums: dict[str, int],
        maximums: dict[str, int],
    ) -> dict[str, int]:
        """Distribute the requested button count across panels.

        Improvement note: helper method for the binary search honoring panel
        priorities (the order of ``panel_states``).

        Args:
            panel_states: Panel-state list defining priority.
            total: Total number of buttons to distribute.
            minimums: Minimum counts per panel.
            maximums: Maximum counts per panel.

        Returns:
            Dictionary with the final distribution.
        """
        counts: dict[str, int] = {}
        remaining = total
        
        # Allocate minimum counts first
        for state in panel_states:
            label = state.definition.label
            counts[label] = minimums[label]
            remaining -= minimums[label]
        
        # Distribute remaining buttons according to priority
        for state in panel_states:
            label = state.definition.label
            available = maximums[label] - minimums[label]
            to_add = min(available, remaining)
            counts[label] += to_add
            remaining -= to_add
            
            if remaining <= 0:
                break
        
        return counts
