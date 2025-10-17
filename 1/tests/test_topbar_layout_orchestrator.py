"""Tests for LayoutOrchestrator favorites threshold behaviour (lightweight)."""

from unittest.mock import Mock

from app.views.main_components.ui.topbar.models.topbar_constants import (
    TOPBAR_CONSTANTS as C,
)
from app.views.main_components.ui.topbar.services.layout_orchestrator import (
    LayoutOrchestrator,
)


def _build_orchestrator(favorites_threshold: int | None = None):
    widget_accessor = Mock()
    visibility_manager = Mock()
    visibility_manager.apply_counts.side_effect = lambda states, counts: counts
    visibility_solver = Mock()
    search_manager = Mock()
    search_manager.enforce_stretches.return_value = None
    search_manager.clamp_width.return_value = None
    separator_service = Mock()
    separator_service.build_panel_widgets_map.return_value = {}
    separator_service.update_separators.return_value = None
    hysteresis_service = Mock()
    hysteresis_service.apply_hysteresis.side_effect = lambda ctx, counts, *_: counts
    narrow_mode_service = Mock()
    narrow_mode_service.apply_narrow_mode.return_value = None
    narrow_mode_service.set_top_bar_margins.return_value = None

    orchestrator = LayoutOrchestrator(
        window=Mock(),
        widget_accessor=widget_accessor,
        visibility_manager=visibility_manager,
        visibility_solver=visibility_solver,
        search_manager=search_manager,
        separator_service=separator_service,
        hysteresis_service=hysteresis_service,
        narrow_mode_service=narrow_mode_service,
        panel_definitions=(),
        panel_labels=("fav",),
        min_search_width=148,
        narrow_threshold=600,
        log_info=False,
        slow_adjust_threshold_ms=50.0,
        side_spacing=8,
        favorites_min_visible_threshold=favorites_threshold,
    )
    return orchestrator, visibility_solver


class DummyContext:
    def __init__(self) -> None:
        self.panel_states = []
        self.top_bar = Mock()
        self.search = Mock()


def test_handle_normal_mode_with_custom_favorites_threshold():
    orchestrator, visibility_solver = _build_orchestrator(favorites_threshold=3)
    visibility_solver.compute_visible_counts.return_value = {"fav": 2}
    ctx = DummyContext()

    result = orchestrator._handle_normal_mode(ctx)

    assert result["fav"] == 0


def test_handle_normal_mode_with_default_favorites_threshold():
    orchestrator, visibility_solver = _build_orchestrator()
    visibility_solver.compute_visible_counts.return_value = {
        "fav": C.FAVORITES_MIN_VISIBLE_THRESHOLD
    }
    ctx = DummyContext()

    result = orchestrator._handle_normal_mode(ctx)

    assert result["fav"] == C.FAVORITES_MIN_VISIBLE_THRESHOLD

