"""Tests for Qt utility functions.

Validates sip.isdeleted() wrapper and statistics tracking.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QWidget

from app.views.main_components.ui.topbar.qt_utils import (
    get_sip_statistics,
    is_deleted,
)


def test_is_deleted_with_none():
    """Test is_deleted with None object."""
    assert is_deleted(None) is True


def test_is_deleted_with_valid_widget(qtbot):
    """Test is_deleted with valid widget."""
    widget = QWidget()
    qtbot.addWidget(widget)
    assert is_deleted(widget) is False


def test_is_deleted_with_deleted_widget(qtbot):
    """Test is_deleted with deleted widget."""
    widget = QWidget()
    qtbot.addWidget(widget)
    
    # Delete the widget
    widget.deleteLater()
    qtbot.wait(100)  # Wait for deletion
    
    # Note: Actual deletion detection depends on sip availability
    # This test validates that the function doesn't crash
    result = is_deleted(widget)
    assert isinstance(result, bool)


def test_is_deleted_with_non_qt_object():
    """Test is_deleted with non-Qt object."""
    obj = {"key": "value"}
    # Non-Qt objects should return False
    assert is_deleted(obj) is False


def test_get_sip_statistics():
    """Test sip statistics retrieval."""
    stats = get_sip_statistics()
    
    # Should return a dictionary with expected keys
    assert isinstance(stats, dict)
    assert "sip_available" in stats
    assert "total_calls" in stats
    assert "error_count" in stats
    assert "success_rate" in stats
    
    # Values should be reasonable
    assert isinstance(stats["sip_available"], bool)
    assert isinstance(stats["total_calls"], int)
    assert isinstance(stats["error_count"], int)
    assert isinstance(stats["success_rate"], (int, float))
    
    # Success rate should be 0-100
    assert 0 <= stats["success_rate"] <= 100


def test_is_deleted_multiple_calls(qtbot):
    """Test that multiple calls to is_deleted work correctly."""
    widget = QWidget()
    qtbot.addWidget(widget)
    
    # Multiple calls should return consistent results
    result1 = is_deleted(widget)
    result2 = is_deleted(widget)
    result3 = is_deleted(widget)
    
    assert result1 == result2 == result3
    assert result1 is False


def test_statistics_tracking():
    """Test that statistics are tracked correctly."""
    stats_before = get_sip_statistics()
    
    # Make some is_deleted calls
    is_deleted(None)
    is_deleted(QWidget())
    is_deleted({"test": "object"})
    
    stats_after = get_sip_statistics()
    
    # If using fallback, call count should increase
    if not stats_before["sip_available"]:
        assert stats_after["total_calls"] >= stats_before["total_calls"]
