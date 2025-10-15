from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from ..models.layout_context import LayoutContext
from ..models.panel_state import PanelState
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutComputationResult:
    """Result of a layout computation cycle."""

    counts: Mapping[str, int]
    is_narrow: bool


class TopBarLayoutService:
    """Encapsulate top-bar layout computation rules.

    This service keeps heavy decision logic away from the UI-facing
    ``TopBarLayoutManager`` and allows the computation paths to be unit-tested in
    isolation.
    """

    def __init__(
        self,
        width_calculator: WidthCalculator,
        visibility_solver: VisibilitySolver,
        *,
        hysteresis_threshold_base: int,
        hysteresis_spacing_multiplier: int,
    ) -> None:
        self._width_calculator = width_calculator
        self._visibility_solver = visibility_solver
        self._hysteresis_threshold_base = hysteresis_threshold_base
        self._hysteresis_spacing_multiplier = hysteresis_spacing_multiplier

    def compute(
        self,
        ctx: LayoutContext,
        *,
        panel_states: Iterable[PanelState],
        panel_labels: Sequence[str],
        last_applied: tuple[int, ...] | None,
        narrow_threshold: int,
    ) -> LayoutComputationResult:
        states = tuple(panel_states)
        if ctx.effective_width <= narrow_threshold:
            counts = self._compute_narrow_counts(states)
            return LayoutComputationResult(counts=counts, is_narrow=True)

        counts = self._visibility_solver.compute_visible_counts(ctx)
        counts = self._ensure_panel_keys(counts, states)
        counts = self._apply_hysteresis(
            ctx,
            counts,
            panel_labels=panel_labels,
            last_applied=last_applied,
            panel_states=states,
        )
        counts = self._apply_business_rules(counts)
        return LayoutComputationResult(counts=counts, is_narrow=False)

    def _compute_narrow_counts(self, states: Sequence[PanelState]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for state in states:
            if state.definition.label == "quick":
                counts[state.definition.label] = len(state.buttons)
            else:
                counts[state.definition.label] = state.min_visible
        return counts

    def _ensure_panel_keys(
        self, counts: Mapping[str, int], states: Sequence[PanelState]
    ) -> dict[str, int]:
        enriched = {state.definition.label: counts.get(state.definition.label, 0) for state in states}
        return enriched

    def _apply_business_rules(self, counts: Mapping[str, int]) -> dict[str, int]:
        adjusted = dict(counts)
        fav_count = adjusted.get("fav")
        if fav_count is not None and 0 < fav_count < 5:
            adjusted["fav"] = 0
        return adjusted

    def _apply_hysteresis(
        self,
        ctx: LayoutContext,
        counts: Mapping[str, int],
        *,
        panel_labels: Sequence[str],
        last_applied: tuple[int, ...] | None,
        panel_states: Sequence[PanelState],
    ) -> dict[str, int]:
        if last_applied is None:
            return dict(counts)
        try:
            prev_counts = {
                label: last_applied[index]
                for index, label in enumerate(panel_labels)
            }
            total_new = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                counts,
                ctx.min_search_width,
            )
            total_prev = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                panel_states,
                prev_counts,
                ctx.min_search_width,
            )

            slack_new = ctx.width - total_new
            slack_prev = ctx.width - total_prev

            try:
                spacing = int(ctx.top_bar.spacing() or 0)
            except Exception:  # pragma: no cover - defensive fallback
                spacing = 6

            threshold = max(
                self._hysteresis_threshold_base,
                spacing * self._hysteresis_spacing_multiplier,
            )

            if abs(slack_new) < threshold and abs(slack_prev) < threshold:
                return prev_counts
        except Exception:  # pragma: no cover - logging and fallback to new counts
            logger.debug("TopBarLayoutService: hysteresis fallback engaged", exc_info=True)
        return dict(counts)
