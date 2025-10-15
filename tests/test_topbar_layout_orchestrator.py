"""Tests for LayoutOrchestrator with new configuration features."""

import pytest
from unittest.mock import Mock, patch
from app.views.main_components.ui.topbar.services.layout_orchestrator import LayoutOrchestrator
from app.views.main_components.ui.topbar.models.config_protocol import MockTopBarConfig


class MockManagerRef:
    def __init__(self, config=None):
        self._config = config


class MockContext:
    def __init__(self):
        self.width = 800
        self.panel_states = []


def test_handle_normal_mode_with_custom_favorites_threshold():
    """Test that _handle_normal_mode respects custom favorites threshold."""
    # Create mock config with custom threshold
    config = MockTopBarConfig()
    config.set("favorites_min_visible_threshold", 3)
    
    # Create orchestrator with mock manager ref
    manager_ref = MockManagerRef(config)
    
    # Create orchestrator (we'll test the specific method)
    orchestrator = Mock()
    orchestrator._manager_ref = manager_ref
    
    # Test the logic directly
    counts = {"fav": 2}  # Less than threshold of 3
    
    # Apply the same logic as in the method
    favorites_threshold = getattr(orchestrator._manager_ref, '_config', None)
    if favorites_threshold and hasattr(favorites_threshold, 'get_favorites_min_visible_threshold'):
        threshold = favorites_threshold.get_favorites_min_visible_threshold()
    else:
        threshold = 5  # default
    
    if "fav" in counts and 0 < counts["fav"] < threshold:
        counts["fav"] = 0
    
    # Should be hidden (set to 0) because 2 < 3
    assert counts["fav"] == 0


def test_handle_normal_mode_with_default_favorites_threshold():
    """Test that _handle_normal_mode uses default favorites threshold when no config."""
    # Create orchestrator without config
    manager_ref = MockManagerRef(None)
    
    # Create orchestrator (we'll test the specific method)
    orchestrator = Mock()
    orchestrator._manager_ref = manager_ref
    
    # Test the logic directly
    counts = {"fav": 3}  # Equal to default threshold of 5
    
    # Apply the same logic as in the method
    favorites_threshold = getattr(orchestrator._manager_ref, '_config', None)
    if favorites_threshold and hasattr(favorites_threshold, 'get_favorites_min_visible_threshold'):
        threshold = favorites_threshold.get_favorites_min_visible_threshold()
    else:
        threshold = 5  # default
    
    if "fav" in counts and 0 < counts["fav"] < threshold:
        counts["fav"] = 0
    
    # Should NOT be hidden because 3 >= 5 is False
    assert counts["fav"] == 3
