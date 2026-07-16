#!/usr/bin/env python3
"""Regression test for link table DnD cache rebuild functionality."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.views.widgets.link.base_table import LinksTableView


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    app.quit()


def get_current_link_ids(table):
    """Helper to get current link IDs in order from model."""
    model = table.model()
    ids = []
    for row in range(model.rowCount()):
        link = model.get_link(row)
        if link and "id" in link:
            ids.append(link["id"])
    return ids


def get_cached_link_ids(table):
    """Helper to get current link IDs in order from cache."""
    cache = table._link_cache
    # Get sorted keys to ensure correct order
    sorted_rows = sorted(cache.keys())
    ids = []
    for row in sorted_rows:
        link = cache.get(row)
        if link and "id" in link:
            ids.append(link["id"])
    return ids


def test_single_row_move_cache_rebuild(qapp):
    """Test that moving a single row triggers exactly one cache rebuild and correct order."""
    # Create test data
    test_links = [
        {"id": 1, "name": "Link 1", "last_used": "2024-01-01", "notes": ""},
        {"id": 2, "name": "Link 2", "last_used": "2024-01-02", "notes": ""},
        {"id": 3, "name": "Link 3", "last_used": "2024-01-03", "notes": ""},
        {"id": 4, "name": "Link 4", "last_used": "2024-01-04", "notes": ""},
        {"id": 5, "name": "Link 5", "last_used": "2024-01-05", "notes": ""},
    ]

    table = LinksTableView()
    model = table.model()
    model.set_links(test_links)
    
    # Initially rebuild cache to ensure it's populated
    table.rebuild_cache_from_items()

    # Verify initial order
    assert get_current_link_ids(table) == [1, 2, 3, 4, 5]
    assert get_cached_link_ids(table) == [1, 2, 3, 4, 5]

    # Test moving one row with spy (keeps original method)
    with patch.object(
        table, "rebuild_cache_from_items", wraps=table.rebuild_cache_from_items
    ) as mock_rebuild:
        model.move_rows([1], 3)  # Move row 1 (link 2) to position 3
        qapp.processEvents()  # Process Qt events
        mock_rebuild.assert_called_once()

    # Verify order after move
    expected_order = [1, 3, 2, 4, 5]
    assert get_current_link_ids(table) == expected_order
    assert get_cached_link_ids(table) == expected_order


def test_contiguous_range_move_cache_rebuild(qapp):
    """Test that moving a contiguous range triggers exactly one cache rebuild and correct order."""
    test_links = [
        {"id": 1, "name": "Link 1", "last_used": "2024-01-01", "notes": ""},
        {"id": 2, "name": "Link 2", "last_used": "2024-01-02", "notes": ""},
        {"id": 3, "name": "Link 3", "last_used": "2024-01-03", "notes": ""},
        {"id": 4, "name": "Link 4", "last_used": "2024-01-04", "notes": ""},
        {"id": 5, "name": "Link 5", "last_used": "2024-01-05", "notes": ""},
    ]

    table = LinksTableView()
    model = table.model()
    model.set_links(test_links)
    
    # Initially rebuild cache to ensure it's populated
    table.rebuild_cache_from_items()

    assert get_current_link_ids(table) == [1, 2, 3, 4, 5]
    assert get_cached_link_ids(table) == [1, 2, 3, 4, 5]

    with patch.object(
        table, "rebuild_cache_from_items", wraps=table.rebuild_cache_from_items
    ) as mock_rebuild:
        model.move_rows([0, 1], 4)  # Move rows 0-1 to position 4
        qapp.processEvents()
        mock_rebuild.assert_called_once()

    expected_order = [3, 4, 1, 2, 5]
    assert get_current_link_ids(table) == expected_order
    assert get_cached_link_ids(table) == expected_order


def test_non_contiguous_rows_move_cache_rebuild(qapp):
    """Test that moving non-contiguous rows triggers exactly one cache rebuild and correct order."""
    test_links = [
        {"id": 1, "name": "Link 1", "last_used": "2024-01-01", "notes": ""},
        {"id": 2, "name": "Link 2", "last_used": "2024-01-02", "notes": ""},
        {"id": 3, "name": "Link 3", "last_used": "2024-01-03", "notes": ""},
        {"id": 4, "name": "Link 4", "last_used": "2024-01-04", "notes": ""},
        {"id": 5, "name": "Link 5", "last_used": "2024-01-05", "notes": ""},
    ]

    table = LinksTableView()
    model = table.model()
    model.set_links(test_links)
    
    # Initially rebuild cache to ensure it's populated
    table.rebuild_cache_from_items()

    assert get_current_link_ids(table) == [1, 2, 3, 4, 5]
    assert get_cached_link_ids(table) == [1, 2, 3, 4, 5]

    with patch.object(
        table, "rebuild_cache_from_items", wraps=table.rebuild_cache_from_items
    ) as mock_rebuild:
        model.move_rows([0, 2], 5)  # Move rows 0 and 2 to position 5
        qapp.processEvents()
        mock_rebuild.assert_called_once()

    expected_order = [2, 4, 5, 1, 3]
    assert get_current_link_ids(table) == expected_order
    assert get_cached_link_ids(table) == expected_order
