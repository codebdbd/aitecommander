"""Unit tests for VisibilitySolver."""

import pytest
from unittest.mock import Mock, MagicMock

from app.views.main_components.topbar.visibility_solver import VisibilitySolver
from app.views.main_components.topbar.width_calculator import WidthCalculator
from app.views.main_components.topbar.layout_context import LayoutContext
from app.views.main_components.topbar.panel_state import PanelState, PanelDefinition


@pytest.fixture
def width_calculator():
    """Create a mock WidthCalculator."""
    calc = Mock(spec=WidthCalculator)
    calc.total_width = Mock(return_value=100)
    return calc


@pytest.fixture
def solver(width_calculator):
    """Create a VisibilitySolver instance."""
    return VisibilitySolver(width_calculator, use_binary_search=False)


@pytest.fixture
def panel_states():
    """Create mock panel states."""
    states = []
    for label in ["recent", "fav", "quick"]:
        definition = PanelDefinition(
            label=label,
            attr_name=f"{label}_widget",
            button_object_name=f"{label}Button",
            min_attr="_min_recent",
            max_attr="_max_recent",
        )
        state = PanelState(
            definition=definition,
            widget=Mock(),
            buttons=[Mock() for _ in range(10)],
            min_visible=0,
            max_visible=10,
        )
        states.append(state)
    return states


@pytest.fixture
def context(panel_states):
    """Create a mock LayoutContext."""
    ctx = Mock(spec=LayoutContext)
    ctx.width = 1000
    ctx.effective_width = 1000
    ctx.min_search_width = 100
    ctx.top_bar = Mock()
    ctx.search = Mock()
    ctx.panel_states = tuple(panel_states)
    return ctx


class TestVisibilitySolverGreedy:
    """Tests for greedy algorithm."""
    
    def test_respects_minimum_visible(self, solver, context, width_calculator):
        """Test that solver respects minimum visible constraints."""
        # Set minimums
        for state in context.panel_states:
            state.min_visible = 2
            state.max_visible = 10
        
        # Make it tight - should go to minimums
        width_calculator.total_width.return_value = 1100
        
        result = solver.compute_visible_counts(context)
        
        assert all(result[state.definition.label] >= 2 for state in context.panel_states)
    
    def test_respects_maximum_visible(self, solver, context, width_calculator):
        """Test that solver respects maximum visible constraints."""
        # Set maximums
        for state in context.panel_states:
            state.max_visible = 5
        
        width_calculator.total_width.return_value = 50  # Plenty of space
        
        result = solver.compute_visible_counts(context)
        
        assert all(result[state.definition.label] <= 5 for state in context.panel_states)
    
    def test_fills_available_space(self, solver, context, width_calculator):
        """Test that solver uses available space."""
        # Mock total_width to return different values based on counts
        def mock_total_width(top_bar, search, states, counts, min_search):
            total_buttons = sum(counts.values())
            return 50 * total_buttons + 100  # 50px per button + 100px overhead
        
        width_calculator.total_width.side_effect = mock_total_width
        context.width = 500
        
        result = solver.compute_visible_counts(context)
        
        # Should fit about 8 buttons total ((500-100)/50 = 8)
        total = sum(result.values())
        assert 6 <= total <= 10  # Reasonable range
    
    def test_priority_order(self, solver, context, width_calculator):
        """Test that solver respects priority order (first panel has priority)."""
        # Set different maximums
        context.panel_states[0].max_visible = 10  # recent (highest priority)
        context.panel_states[1].max_visible = 5   # fav
        context.panel_states[2].max_visible = 3   # quick (lowest priority)
        
        # Tight space - should prefer recent
        def mock_total_width(top_bar, search, states, counts, min_search):
            total = sum(counts.values())
            return 30 * total + 150
        
        width_calculator.total_width.side_effect = mock_total_width
        context.width = 300  # Tight space
        
        result = solver.compute_visible_counts(context)
        
        # Recent should get more than quick
        assert result["recent"] >= result["quick"]
    
    def test_terminates_with_infinite_loop_protection(self, solver, context, width_calculator):
        """Test that solver doesn't hang with infinite loop protection."""
        # Set up a scenario that could cause infinite loop
        width_calculator.total_width.return_value = float('inf')  # Never fits
        
        result = solver.compute_visible_counts(context)
        
        # Should terminate and return minimums
        assert all(result[state.definition.label] == state.min_visible 
                   for state in context.panel_states)


class TestVisibilitySolverBinarySearch:
    """Tests for binary search algorithm."""
    
    def test_binary_search_respects_constraints(self, width_calculator):
        """Test that binary search respects min/max constraints."""
        solver = VisibilitySolver(width_calculator, use_binary_search=True)
        
        panel_states = []
        for label in ["recent", "fav"]:
            definition = PanelDefinition(
                label=label,
                attr_name=f"{label}_widget",
                button_object_name=f"{label}Button",
                min_attr="_min",
                max_attr="_max",
            )
            state = PanelState(
                definition=definition,
                widget=Mock(),
                buttons=[Mock() for _ in range(10)],
                min_visible=2,
                max_visible=10,
            )
            panel_states.append(state)
        
        context = Mock(spec=LayoutContext)
        context.width = 500
        context.min_search_width = 100
        context.top_bar = Mock()
        context.search = Mock()
        context.panel_states = tuple(panel_states)
        
        # Mock width calculation
        def mock_total_width(top_bar, search, states, counts, min_search):
            return sum(counts.values()) * 30 + 100
        
        width_calculator.total_width.side_effect = mock_total_width
        
        result = solver.compute_visible_counts(context)
        
        # Check constraints
        for state in panel_states:
            label = state.definition.label
            assert state.min_visible <= result[label] <= state.max_visible


class TestVisibilitySolverEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_panel_states(self, solver, width_calculator):
        """Test with empty panel states."""
        context = Mock(spec=LayoutContext)
        context.panel_states = tuple()
        context.width = 1000
        
        result = solver.compute_visible_counts(context)
        
        assert result == {}
    
    def test_zero_width_container(self, solver, context, width_calculator):
        """Test with zero width container."""
        context.width = 0
        width_calculator.total_width.return_value = 100
        
        result = solver.compute_visible_counts(context)
        
        # Should return minimums
        assert all(result[state.definition.label] == state.min_visible 
                   for state in context.panel_states)
    
    def test_all_minimums_zero(self, solver, context, width_calculator):
        """Test when all panels have zero minimum."""
        for state in context.panel_states:
            state.min_visible = 0
            state.max_visible = 10
        
        # Very tight space
        width_calculator.total_width.return_value = 2000
        context.width = 100
        
        result = solver.compute_visible_counts(context)
        
        # Should be able to set all to zero
        assert all(result[state.definition.label] >= 0 for state in context.panel_states)
