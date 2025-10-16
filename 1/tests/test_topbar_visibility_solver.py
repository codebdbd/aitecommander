"""Tests for VisibilitySolver component.

Validates visible button count computation with greedy and binary search strategies.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget

from app.views.main_components.ui.topbar.layout_context import LayoutContext
from app.views.main_components.ui.topbar.panel_state import PanelDefinition, PanelState
from app.views.main_components.ui.topbar.visibility_solver import VisibilitySolver
from app.views.main_components.ui.topbar.width_calculator import WidthCalculator


@pytest.fixture
def calculator():
    """Create a WidthCalculator instance."""
    return WidthCalculator(button_size=32)


@pytest.fixture
def solver_greedy(calculator):
    """Create a VisibilitySolver with greedy strategy."""
    return VisibilitySolver(calculator, use_binary_search=False)


@pytest.fixture
def solver_binary(calculator):
    """Create a VisibilitySolver with binary search strategy."""
    return VisibilitySolver(calculator, use_binary_search=True)


@pytest.fixture
def layout_context(qtbot, calculator):
    """Create a mock LayoutContext for testing."""
    # Create container
    container = QWidget()
    container.setFixedWidth(800)
    qtbot.addWidget(container)
    
    # Create layout
    layout = QHBoxLayout()
    layout.setSpacing(4)
    layout.setContentsMargins(8, 0, 8, 0)
    
    # Create search widget
    search = QLineEdit()
    search.setMinimumWidth(148)
    qtbot.addWidget(search)
    layout.addWidget(search)
    
    # Create panel states
    panel_states = []
    for label in ["recent", "fav", "quick"]:
        panel = QWidget()
        qtbot.addWidget(panel)
        buttons = [QToolButton() for _ in range(10)]
        for btn in buttons:
            btn.setFixedSize(32, 32)
        
        definition = PanelDefinition(
            label=label,
            attr_name=f"{label}_widget",
            button_object_name=f"{label}Button",
            min_attr=f"_min_{label}",
            max_attr=f"_max_{label}",
        )
        state = PanelState(
            definition=definition,
            widget=panel,
            buttons=buttons,
            min_visible=0,
            max_visible=10,
        )
        panel_states.append(state)
        layout.addWidget(panel)
    
    return LayoutContext(
        container=container,
        width=800,
        effective_width=800,
        min_search_width=148,
        top_bar=layout,
        search=search,
        panel_states=tuple(panel_states),
    )


def test_solver_initialization_greedy(solver_greedy):
    """Test VisibilitySolver initialization with greedy strategy."""
    assert solver_greedy._use_binary_search is False


def test_solver_initialization_binary(solver_binary):
    """Test VisibilitySolver initialization with binary search strategy."""
    assert solver_binary._use_binary_search is True


def test_compute_visible_counts_greedy(solver_greedy, layout_context):
    """Test greedy strategy computation."""
    counts = solver_greedy.compute_visible_counts(layout_context)
    
    # Should return counts for all panels
    assert "recent" in counts
    assert "fav" in counts
    assert "quick" in counts
    
    # All counts should be non-negative
    assert all(c >= 0 for c in counts.values())
    
    # Counts should respect max_visible
    for state in layout_context.panel_states:
        assert counts[state.definition.label] <= state.max_visible


def test_compute_visible_counts_binary(solver_binary, layout_context):
    """Test binary search strategy computation."""
    counts = solver_binary.compute_visible_counts(layout_context)
    
    # Should return counts for all panels
    assert "recent" in counts
    assert "fav" in counts
    assert "quick" in counts
    
    # All counts should be non-negative
    assert all(c >= 0 for c in counts.values())
    
    # Counts should respect max_visible
    for state in layout_context.panel_states:
        assert counts[state.definition.label] <= state.max_visible


def test_greedy_respects_minimums(solver_greedy, layout_context):
    """Test that greedy strategy respects minimum visible counts."""
    # Modify panel states to have minimums
    modified_states = []
    for state in layout_context.panel_states:
        modified_state = PanelState(
            definition=state.definition,
            widget=state.widget,
            buttons=state.buttons,
            min_visible=2,  # Set minimum
            max_visible=state.max_visible,
        )
        modified_states.append(modified_state)
    
    ctx = LayoutContext(
        container=layout_context.container,
        width=layout_context.width,
        effective_width=layout_context.effective_width,
        min_search_width=layout_context.min_search_width,
        top_bar=layout_context.top_bar,
        search=layout_context.search,
        panel_states=tuple(modified_states),
    )
    
    counts = solver_greedy.compute_visible_counts(ctx)
    
    # All counts should be >= minimum
    for state in modified_states:
        assert counts[state.definition.label] >= state.min_visible


def test_binary_respects_minimums(solver_binary, layout_context):
    """Test that binary search strategy respects minimum visible counts."""
    # Modify panel states to have minimums
    modified_states = []
    for state in layout_context.panel_states:
        modified_state = PanelState(
            definition=state.definition,
            widget=state.widget,
            buttons=state.buttons,
            min_visible=2,  # Set minimum
            max_visible=state.max_visible,
        )
        modified_states.append(modified_state)
    
    ctx = LayoutContext(
        container=layout_context.container,
        width=layout_context.width,
        effective_width=layout_context.effective_width,
        min_search_width=layout_context.min_search_width,
        top_bar=layout_context.top_bar,
        search=layout_context.search,
        panel_states=tuple(modified_states),
    )
    
    counts = solver_binary.compute_visible_counts(ctx)
    
    # All counts should be >= minimum
    for state in modified_states:
        assert counts[state.definition.label] >= state.min_visible


def test_narrow_width_reduces_counts(solver_greedy, layout_context):
    """Test that narrow width reduces visible counts."""
    # Wide width
    counts_wide = solver_greedy.compute_visible_counts(layout_context)
    total_wide = sum(counts_wide.values())
    
    # Narrow width
    narrow_ctx = LayoutContext(
        container=layout_context.container,
        width=300,  # Much narrower
        effective_width=300,
        min_search_width=layout_context.min_search_width,
        top_bar=layout_context.top_bar,
        search=layout_context.search,
        panel_states=layout_context.panel_states,
    )
    counts_narrow = solver_greedy.compute_visible_counts(narrow_ctx)
    total_narrow = sum(counts_narrow.values())
    
    # Narrow should have fewer visible buttons
    assert total_narrow <= total_wide


def test_strategies_produce_similar_results(solver_greedy, solver_binary, layout_context):
    """Test that both strategies produce reasonable results."""
    counts_greedy = solver_greedy.compute_visible_counts(layout_context)
    counts_binary = solver_binary.compute_visible_counts(layout_context)
    
    # Both should have same panels
    assert set(counts_greedy.keys()) == set(counts_binary.keys())
    
    # Total counts should be similar (within reasonable range)
    total_greedy = sum(counts_greedy.values())
    total_binary = sum(counts_binary.values())
    
    # Allow some difference due to different algorithms
    assert abs(total_greedy - total_binary) <= 5


def test_distribute_buttons(solver_binary, layout_context):
    """Test button distribution helper method."""
    minimums = {"recent": 1, "fav": 1, "quick": 1}
    maximums = {"recent": 10, "fav": 10, "quick": 6}
    
    # Distribute 15 buttons
    counts = solver_binary._distribute_buttons(
        list(layout_context.panel_states), 15, minimums, maximums
    )
    
    # Should sum to 15
    assert sum(counts.values()) == 15
    
    # Should respect minimums and maximums
    for label in counts:
        assert minimums[label] <= counts[label] <= maximums[label]


def test_distribute_buttons_respects_priority(solver_binary, layout_context):
    """Test that distribution respects panel priority order."""
    minimums = {"recent": 0, "fav": 0, "quick": 0}
    maximums = {"recent": 5, "fav": 5, "quick": 5}
    
    # Distribute 10 buttons (more than one panel can hold)
    counts = solver_binary._distribute_buttons(
        list(layout_context.panel_states), 10, minimums, maximums
    )
    
    # First panel (recent) should get filled first
    assert counts["recent"] == 5
    assert counts["fav"] == 5
    assert counts["quick"] == 0


def test_zero_width_returns_minimums(solver_greedy, layout_context):
    """Test that zero width returns minimum counts."""
    zero_ctx = LayoutContext(
        container=layout_context.container,
        width=0,
        effective_width=0,
        min_search_width=layout_context.min_search_width,
        top_bar=layout_context.top_bar,
        search=layout_context.search,
        panel_states=layout_context.panel_states,
    )
    
    counts = solver_greedy.compute_visible_counts(zero_ctx)
    
    # Should return minimums (all 0 in this case)
    for state in layout_context.panel_states:
        assert counts[state.definition.label] == state.min_visible
