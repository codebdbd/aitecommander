from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import pytest

from app.views.main_components.ui.topbar.models.layout_context import LayoutContext
from app.views.main_components.ui.topbar.models.panel_state import PanelDefinition, PanelState
from app.views.main_components.ui.topbar.models.types import PanelLabel
from app.views.main_components.ui.topbar.services.layout_service import TopBarLayoutService
from app.views.main_components.ui.topbar.services.visibility_solver import VisibilitySolver
from app.views.main_components.ui.topbar.services.width_calculator import WidthCalculator
from app.views.main_components.ui.topbar.models.config_protocol import MockTopBarConfig

class DummyLayout:
    """Minimal layout stub that exposes only the APIs used by the service."""

    def __init__(self, spacing: int = 4) -> None:
        self._spacing = spacing

    def spacing(self) -> int:
        return self._spacing


@dataclass
class FakeSolver:
    counts: Mapping[str, int]

    def compute_visible_counts(self, ctx: LayoutContext) -> Mapping[str, int]:  # noqa: D401
        return dict(self.counts)


class FakeWidthCalculator:
    def __init__(self, totals: Mapping[tuple[tuple[str, int], ...], int] | None = None) -> None:
        self._totals = dict(totals or {})

    def total_width(
        self,
        top_bar,
        search,
        panel_states: Iterable[PanelState],
        counts: Mapping[str, int],
        min_search_width: int,
    ) -> int:
        key = tuple(sorted(counts.items()))
        return self._totals.get(key, 0)


def _make_panel_state(label: PanelLabel, *, minimum: int, maximum: int, buttons: int) -> PanelState:
    definition = PanelDefinition(
        label=label.value,
        attr_name=f"{label.value}_widget",
        button_object_name=f"{label.value}Button",
        min_visible=minimum,
        max_visible=maximum,
    )
    dummy_buttons = [object() for _ in range(buttons)]
    return PanelState(
        definition=definition,
        widget=None,
        buttons=dummy_buttons,
        min_visible=minimum,
        max_visible=maximum,
    )


def _make_context(
    *,
    width: int,
    effective_width: int,
    panel_states: Sequence[PanelState],
) -> LayoutContext:
    return LayoutContext(
        container=object(),
        width=width,
        effective_width=effective_width,
        min_search_width=120,
        top_bar=DummyLayout(),
        search=None,
        panel_states=tuple(panel_states),
    )


def test_compute_narrow_counts_uses_minimums() -> None:
    recent = _make_panel_state(PanelLabel.RECENT, minimum=1, maximum=5, buttons=5)
    fav = _make_panel_state(PanelLabel.FAVORITES, minimum=2, maximum=6, buttons=6)
    quick = _make_panel_state(PanelLabel.QUICK, minimum=3, maximum=3, buttons=3)
    panel_states = (recent, fav, quick)

    service = TopBarLayoutService(
        width_calculator=FakeWidthCalculator(),
        visibility_solver=FakeSolver(counts={}),
        hysteresis_threshold_base=12,
        hysteresis_spacing_multiplier=2,
    )

    ctx = _make_context(width=200, effective_width=200, panel_states=panel_states)
    result = service.compute(
        ctx,
        panel_states=panel_states,
        panel_labels=[p.definition.label for p in panel_states],
        last_applied=None,
        narrow_threshold=300,
    )

    assert result.is_narrow is True
    assert result.counts[PanelLabel.RECENT.value] == 1
    assert result.counts[PanelLabel.FAVORITES.value] == 2
    assert result.counts[PanelLabel.QUICK.value] == len(quick.buttons)


def test_business_rule_hides_small_favorites() -> None:
    panel_states = (
        _make_panel_state(PanelLabel.RECENT, minimum=0, maximum=6, buttons=6),
        _make_panel_state(PanelLabel.FAVORITES, minimum=0, maximum=6, buttons=6),
        _make_panel_state(PanelLabel.QUICK, minimum=0, maximum=6, buttons=6),
    )

    service = TopBarLayoutService(
        width_calculator=FakeWidthCalculator(),
        visibility_solver=FakeSolver(
            counts={
                PanelLabel.RECENT.value: 3,
                PanelLabel.FAVORITES.value: 2,
                PanelLabel.QUICK.value: 1,
            }
        ),
        hysteresis_threshold_base=12,
        hysteresis_spacing_multiplier=2,
    )

    ctx = _make_context(width=800, effective_width=800, panel_states=panel_states)
    result = service.compute(
        ctx,
        panel_states=panel_states,
        panel_labels=[p.definition.label for p in panel_states],
        last_applied=None,
        narrow_threshold=300,
    )

    assert result.is_narrow is False
    assert result.counts[PanelLabel.FAVORITES.value] == 0


def test_hysteresis_reuses_previous_counts() -> None:
    panel_states = (
        _make_panel_state(PanelLabel.RECENT, minimum=0, maximum=6, buttons=6),
        _make_panel_state(PanelLabel.FAVORITES, minimum=0, maximum=6, buttons=6),
        _make_panel_state(PanelLabel.QUICK, minimum=0, maximum=6, buttons=6),
    )
    prev_counts = {
        PanelLabel.RECENT.value: 3,
        PanelLabel.FAVORITES.value: 0,
        PanelLabel.QUICK.value: 0,
    }
    totals = {
        tuple(sorted({PanelLabel.RECENT.value: 0, PanelLabel.FAVORITES.value: 0, PanelLabel.QUICK.value: 0}.items())): 97,
        tuple(sorted(prev_counts.items())): 96,
    }

    service = TopBarLayoutService(
        width_calculator=FakeWidthCalculator(totals=totals),
        visibility_solver=FakeSolver(
            counts={
                PanelLabel.RECENT.value: 0,
                PanelLabel.FAVORITES.value: 0,
                PanelLabel.QUICK.value: 0,
            }
        ),
        hysteresis_threshold_base=12,
        hysteresis_spacing_multiplier=2,
    )

    ctx = _make_context(width=100, effective_width=100, panel_states=panel_states)
    result = service.compute(
        ctx,
        panel_states=panel_states,
        panel_labels=[p.definition.label for p in panel_states],
        last_applied=(3, 0, 0),
        narrow_threshold=50,
    )

    assert result.is_narrow is False
    assert result.counts == prev_counts
