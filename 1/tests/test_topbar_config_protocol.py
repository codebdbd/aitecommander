"""Tests for TopBarConfigProtocol implementation."""

import pytest
from app.views.main_components.ui.topbar.models.config_protocol import MockTopBarConfig


def test_mock_config_default_values():
    """Test that MockTopBarConfig provides default values."""
    config = MockTopBarConfig()
    
    # Test new configuration methods
    assert config.get_favorites_min_visible_threshold() == 5
    assert config.get_separator_search_spacing() == 4
    assert config.get_separator_hidden_spacing() == 0
    assert config.get_layout_spacing_fallback() == 6


def test_mock_config_custom_values():
    """Test that MockTopBarConfig accepts custom values."""
    config = MockTopBarConfig()
    
    # Set custom values
    config.set("favorites_min_visible_threshold", 3)
    config.set("separator_search_spacing", 8)
    config.set("separator_hidden_spacing", 2)
    config.set("layout_spacing_fallback", 10)
    
    # Test custom values
    assert config.get_favorites_min_visible_threshold() == 3
    assert config.get_separator_search_spacing() == 8
    assert config.get_separator_hidden_spacing() == 2
    assert config.get_layout_spacing_fallback() == 10


def test_mock_config_mixed_values():
    """Test that MockTopBarConfig handles mixed default and custom values."""
    config = MockTopBarConfig()
    
    # Set only some custom values
    config.set("favorites_min_visible_threshold", 7)
    config.set("separator_search_spacing", 12)
    
    # Test mixed values
    assert config.get_favorites_min_visible_threshold() == 7  # custom
    assert config.get_separator_search_spacing() == 12  # custom
    assert config.get_separator_hidden_spacing() == 0  # default
    assert config.get_layout_spacing_fallback() == 6  # default
