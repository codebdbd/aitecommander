"""Tests for WidthCalculator component.

Validates panel width calculations, caching behavior, and edge cases.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QToolButton, QWidget, QHBoxLayout, QFrame
from app.views.main_components.ui.topbar.width_calculator import WidthCalculator


class MockPanel(QWidget):
    """Mock panel widget for testing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_frame = QFrame(self)
        layout = QHBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(2, 2, 2, 2)
        self.bg_frame.setLayout(layout)


@pytest.fixture
def calculator():
    """Create a WidthCalculator instance."""
    return WidthCalculator(button_size=32)


@pytest.fixture
def mock_panel(qtbot):
    """Create a mock panel with buttons."""
    panel = MockPanel()
    qtbot.addWidget(panel)
    qtbot.addWidget(panel.bg_frame)
    buttons = []
    for i in range(5):
        btn = QToolButton(panel.bg_frame)
        btn.setFixedSize(32, 32)
        qtbot.addWidget(btn)
        panel.bg_frame.layout().addWidget(btn)
        buttons.append(btn)
    return panel, buttons


def test_calculator_initialization(calculator):
    """Test WidthCalculator initialization."""
    assert calculator._button_size == 32
    assert len(calculator._panel_width_cache) == 0
    assert calculator._cache_hits == 0
    assert calculator._cache_misses == 0


def test_panel_width_basic(calculator, mock_panel):
    """Test basic panel width calculation."""
    panel, buttons = mock_panel
    width = calculator.panel_width(panel, buttons, 3)
    
    # Width should be at least MIN_PANEL_WIDTH
    assert width >= WidthCalculator.MIN_PANEL_WIDTH
    # Should be reasonable for 3 buttons
    assert width > 0


def test_panel_width_caching(calculator, mock_panel):
    """Test that panel width results are cached."""
    panel, buttons = mock_panel
    
    # First call - cache miss
    width1 = calculator.panel_width(panel, buttons, 3)
    assert calculator._cache_misses == 1
    assert calculator._cache_hits == 0
    
    # Second call with same params - cache hit
    width2 = calculator.panel_width(panel, buttons, 3)
    assert calculator._cache_misses == 1
    assert calculator._cache_hits == 1
    assert width1 == width2


def test_panel_width_different_counts(calculator, mock_panel):
    """Test panel width with different button counts."""
    panel, buttons = mock_panel
    
    width_1 = calculator.panel_width(panel, buttons, 1)
    width_3 = calculator.panel_width(panel, buttons, 3)
    width_5 = calculator.panel_width(panel, buttons, 5)
    
    # More buttons should require more width
    assert width_1 < width_3 < width_5


def test_panel_width_zero_count(calculator, mock_panel):
    """Test panel width with zero visible buttons."""
    panel, buttons = mock_panel
    width = calculator.panel_width(panel, buttons, 0)
    assert width == WidthCalculator.MIN_PANEL_WIDTH


def test_panel_width_negative_count_raises(calculator, mock_panel):
    """Test that negative count raises ValueError."""
    panel, buttons = mock_panel
    with pytest.raises(ValueError, match="count must be >= 0"):
        calculator.panel_width(panel, buttons, -1)


def test_panel_width_none_buttons(calculator, mock_panel):
    """Test panel width with None buttons list."""
    panel, _ = mock_panel
    width = calculator.panel_width(panel, None, 3)
    assert width == WidthCalculator.MIN_PANEL_WIDTH


def test_panel_width_none_panel(calculator):
    """Test panel width with None panel."""
    width = calculator.panel_width(None, [], 3)
    assert width == WidthCalculator.MIN_PANEL_WIDTH


def test_clear_cache(calculator, mock_panel):
    """Test cache clearing."""
    panel, buttons = mock_panel
    
    # Populate cache
    calculator.panel_width(panel, buttons, 3)
    assert len(calculator._panel_width_cache) > 0
    
    # Clear cache
    calculator.clear_cache()
    assert len(calculator._panel_width_cache) == 0
    assert calculator._cache_hits == 0
    assert calculator._cache_misses == 0


def test_invalidate_cache_for_panel(calculator, mock_panel):
    """Test selective cache invalidation."""
    panel, buttons = mock_panel
    
    # Populate cache with multiple entries
    calculator.panel_width(panel, buttons, 1)
    calculator.panel_width(panel, buttons, 3)
    initial_size = len(calculator._panel_width_cache)
    assert initial_size == 2
    
    # Invalidate cache for this panel
    removed = calculator.invalidate_cache_for_panel(panel)
    assert removed == 2
    assert len(calculator._panel_width_cache) == 0


def test_get_cache_stats(calculator, mock_panel):
    """Test cache statistics reporting."""
    panel, buttons = mock_panel
    
    # Initial stats
    stats = calculator.get_cache_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["size"] == 0
    assert stats["hit_rate"] == 0
    
    # After some operations
    calculator.panel_width(panel, buttons, 3)  # miss
    calculator.panel_width(panel, buttons, 3)  # hit
    
    stats = calculator.get_cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["size"] == 1
    assert stats["hit_rate"] == 50


def test_cache_eviction(calculator, mock_panel):
    """Test that cache evicts oldest entries when full."""
    panel, buttons = mock_panel
    
    # Fill cache beyond CACHE_MAX_SIZE
    for i in range(WidthCalculator.CACHE_MAX_SIZE + 10):
        calculator.panel_width(panel, buttons, i % 10)
    
    # Cache should not exceed max size
    assert len(calculator._panel_width_cache) <= WidthCalculator.CACHE_MAX_SIZE


def test_total_width_basic(calculator, mock_panel, qtbot):
    """Test total width calculation for top bar."""
    from PyQt6.QtWidgets import QHBoxLayout, QLineEdit
    from app.views.main_components.ui.topbar.panel_state import PanelState, PanelDefinition
    
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
    panel, buttons = mock_panel
    layout.addWidget(panel)
    
    definition = PanelDefinition(
        label="test",
        attr_name="test_widget",
        button_object_name="testButton",
        min_visible=0,
        max_visible=5,
    )
    state = PanelState(
        definition=definition,
        widget=panel,
        buttons=buttons,
        min_visible=0,
        max_visible=5,
    )
    
    counts = {"test": 3}
    total = calculator.total_width(layout, search, [state], counts, 148)
    
    # Total should be positive and reasonable
    assert total > 0
    assert total > 148  # At least search width


def test_panel_width_with_deleted_widget(calculator, mock_panel):
    """Test panel width calculation with deleted widget."""
    panel, buttons = mock_panel
    
    # Calculate width before deletion
    width_before = calculator.panel_width(panel, buttons, 3)
    
    # Delete panel
    panel.deleteLater()
    
    # Should return MIN_PANEL_WIDTH for deleted widget
    width_after = calculator.panel_width(panel, buttons, 3)
    assert width_after == WidthCalculator.MIN_PANEL_WIDTH
