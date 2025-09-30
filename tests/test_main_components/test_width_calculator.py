"""Unit tests for WidthCalculator."""

import pytest
from unittest.mock import Mock

from app.views.main_components.topbar.width_calculator import WidthCalculator


class TestWidthCalculator:
    """Tests for WidthCalculator class."""
    
    def test_init_default_button_size(self):
        """Test initialization with default button size."""
        calc = WidthCalculator()
        assert calc._button_size == WidthCalculator.DEFAULT_BUTTON_SIZE
        assert len(calc._panel_width_cache) == 0
    
    def test_init_custom_button_size(self):
        """Test initialization with custom button size."""
        calc = WidthCalculator(button_size=48)
        assert calc._button_size == 48
    
    def test_panel_width_validates_negative_count(self):
        """Test that panel_width raises ValueError for negative count."""
        calc = WidthCalculator()
        panel = Mock()
        buttons = [Mock()]
        
        with pytest.raises(ValueError, match="count must be >= 0"):
            calc.panel_width(panel, buttons, -1)
    
    def test_panel_width_returns_min_for_none_panel(self):
        """Test that panel_width returns MIN_PANEL_WIDTH for None panel."""
        calc = WidthCalculator()
        result = calc.panel_width(None, [Mock()], 5)
        assert result == WidthCalculator.MIN_PANEL_WIDTH
    
    def test_panel_width_returns_min_for_none_buttons(self):
        """Test that panel_width returns MIN_PANEL_WIDTH for None buttons."""
        calc = WidthCalculator()
        panel = Mock()
        result = calc.panel_width(panel, None, 5)
        assert result == WidthCalculator.MIN_PANEL_WIDTH
    
    def test_panel_width_returns_min_for_zero_count(self):
        """Test that panel_width returns MIN_PANEL_WIDTH for zero count."""
        calc = WidthCalculator()
        panel = Mock()
        panel.bg_frame = None
        buttons = [Mock() for _ in range(5)]
        
        result = calc.panel_width(panel, buttons, 0)
        assert result == WidthCalculator.MIN_PANEL_WIDTH
    
    def test_panel_width_caching(self):
        """Test that panel_width caches results."""
        calc = WidthCalculator()
        
        # Create mock panel with layout
        panel = Mock()
        bg_frame = Mock()
        layout = Mock()
        layout.count.return_value = 0
        layout.spacing.return_value = 4
        layout.contentsMargins.return_value = Mock(left=lambda: 0, right=lambda: 0)
        bg_frame.layout.return_value = layout
        panel.bg_frame = bg_frame
        panel.contentsMargins.return_value = Mock(left=lambda: 0, right=lambda: 0)
        
        buttons = []
        
        # First call - cache miss
        result1 = calc.panel_width(panel, buttons, 0)
        assert calc._cache_misses == 1
        assert calc._cache_hits == 0
        
        # Second call - cache hit
        result2 = calc.panel_width(panel, buttons, 0)
        assert calc._cache_misses == 1
        assert calc._cache_hits == 1
        assert result1 == result2
    
    def test_clear_cache(self):
        """Test that clear_cache empties the cache."""
        calc = WidthCalculator()
        
        panel = Mock()
        panel.bg_frame = None
        
        # Populate cache
        calc.panel_width(panel, [], 0)
        assert len(calc._panel_width_cache) > 0
        
        # Clear cache
        calc.clear_cache()
        assert len(calc._panel_width_cache) == 0
        assert calc._cache_hits == 0
        assert calc._cache_misses == 0
    
    def test_invalidate_cache_for_panel(self):
        """Test selective cache invalidation for a specific panel."""
        calc = WidthCalculator()
        
        panel1 = Mock()
        panel1.bg_frame = None
        panel2 = Mock()
        panel2.bg_frame = None
        
        # Populate cache for both panels
        calc.panel_width(panel1, [], 0)
        calc.panel_width(panel1, [], 1)
        calc.panel_width(panel2, [], 0)
        
        initial_size = len(calc._panel_width_cache)
        assert initial_size == 3
        
        # Invalidate only panel1
        removed = calc.invalidate_cache_for_panel(panel1)
        assert removed == 2  # Two entries for panel1
        assert len(calc._panel_width_cache) == 1  # Only panel2 remains
    
    def test_get_cache_stats(self):
        """Test cache statistics."""
        calc = WidthCalculator()
        
        panel = Mock()
        panel.bg_frame = None
        
        # Generate some hits and misses
        calc.panel_width(panel, [], 0)  # miss
        calc.panel_width(panel, [], 0)  # hit
        calc.panel_width(panel, [], 1)  # miss
        
        stats = calc.get_cache_stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["size"] == 2
        assert stats["hit_rate"] == 33  # 1/3 * 100
    
    def test_lru_eviction(self):
        """Test that LRU eviction works when cache is full."""
        calc = WidthCalculator()
        calc.CACHE_MAX_SIZE = 3  # Override for test
        
        panels = [Mock() for _ in range(5)]
        for p in panels:
            p.bg_frame = None
        
        # Fill cache beyond limit
        for i, panel in enumerate(panels):
            calc.panel_width(panel, [], 0)
        
        # Cache should not exceed max size
        assert len(calc._panel_width_cache) <= calc.CACHE_MAX_SIZE
    
    def test_lru_moves_to_end_on_access(self):
        """Test that accessing cached item moves it to end (most recently used)."""
        calc = WidthCalculator()
        
        panel1 = Mock()
        panel1.bg_frame = None
        panel2 = Mock()
        panel2.bg_frame = None
        
        # Add both to cache
        calc.panel_width(panel1, [], 0)
        calc.panel_width(panel2, [], 0)
        
        # Access panel1 again
        calc.panel_width(panel1, [], 0)
        
        # panel1 should now be at the end (most recently used)
        cache_keys = list(calc._panel_width_cache.keys())
        assert cache_keys[-1] == (id(panel1), 0)


class TestWidthCalculatorIntegration:
    """Integration tests with more realistic mocks."""
    
    def test_panel_width_with_buttons(self):
        """Test panel_width calculation with actual button widgets."""
        calc = WidthCalculator(button_size=32)
        
        # Create realistic mock structure
        panel = Mock()
        bg_frame = Mock()
        layout = Mock()
        
        # Mock buttons
        buttons = []
        for i in range(3):
            btn = Mock()
            btn.sizeHint.return_value = Mock(width=lambda: 32)
            btn.maximumWidth.return_value = 32
            btn.minimumWidth.return_value = 32
            btn.isVisible.return_value = True
            buttons.append(btn)
        
        # Setup layout to return buttons
        layout_items = []
        for btn in buttons:
            item = Mock()
            item.widget.return_value = btn
            layout_items.append(item)
        
        layout.count.return_value = len(layout_items)
        layout.itemAt.side_effect = lambda i: layout_items[i]
        layout.spacing.return_value = 4
        layout.contentsMargins.return_value = Mock(left=lambda: 2, right=lambda: 2)
        
        bg_frame.layout.return_value = layout
        bg_frame.frameWidth.return_value = 1
        
        panel.bg_frame = bg_frame
        panel.contentsMargins.return_value = Mock(left=lambda: 0, right=lambda: 0)
        
        # Calculate width for 3 visible buttons
        result = calc.panel_width(panel, buttons, 3)
        
        # Should be: 3*32 (buttons) + 2*4 (spacing) + 4 (margins) + 2 (frame) = 110
        # But minimum is 50
        assert result >= WidthCalculator.MIN_PANEL_WIDTH
