#!/usr/bin/env python3
"""Regression test for link table DnD cache rebuild functionality."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, Qt
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


def test_first_run_default_sort_is_order(qapp):
    table = LinksTableView()

    column, order = table._default_sort_from_links(
        [{"id": 1, "name": "B", "last_used": "2026-01-01"}]
    )

    assert column == 2
    assert order == Qt.SortOrder.AscendingOrder


def test_initial_sort_uses_order_even_when_saved_sort_exists(qapp):
    table = LinksTableView()
    table._settings = type(
        "SettingsStub",
        (),
        {"get_table_sort": lambda self: (2, Qt.SortOrder.DescendingOrder)},
    )()

    column, order = table._load_initial_sort()

    assert column == 2
    assert order == Qt.SortOrder.AscendingOrder


def test_order_column_is_wide_enough_for_header(qapp):
    table = LinksTableView()

    assert table.columnWidth(2) >= 112


def test_order_edit_moves_row_and_renumbers(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(
        [
            {"id": 1, "name": "Alpha", "position": 0, "type": "web", "url": "https://a.example", "notes": ""},
            {"id": 2, "name": "Beta", "position": 1, "type": "file", "url": "C:/tmp/b.txt", "notes": ""},
            {"id": 3, "name": "Gamma", "position": 2, "type": "folder", "url": "C:/tmp", "notes": ""},
        ]
    )

    emitted = []
    model.orderEdited.connect(emitted.append)

    assert model.setData(model.index(2, 2), "1", Qt.ItemDataRole.EditRole)

    assert get_current_link_ids(table) == [3, 1, 2]
    assert [model.get_link(row)["position"] for row in range(model.rowCount())] == [0, 1, 2]
    assert emitted == [[3, 1, 2]]
    assert model.data(model.index(0, 2), Qt.ItemDataRole.DisplayRole) == 1
    assert model.data(model.index(0, 5), Qt.ItemDataRole.DisplayRole)


def test_type_column_uses_link_dialog_labels(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(
        [
            {"id": 1, "name": "Web", "position": 0, "type": "web", "url": "https://a.example", "notes": ""},
            {"id": 2, "name": "App", "position": 1, "type": "program", "url": "C:/app.exe", "notes": ""},
        ]
    )

    assert model.data(model.index(0, 5), Qt.ItemDataRole.DisplayRole) == QCoreApplication.translate("LinkDialogUI", "Web link")
    assert model.data(model.index(1, 5), Qt.ItemDataRole.DisplayRole) == QCoreApplication.translate("LinkDialogUI", "Application")


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
