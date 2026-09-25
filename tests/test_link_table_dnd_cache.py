#!/usr/bin/env python3
"""Regression test for link table DnD cache rebuild functionality."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.views.widgets.link.base_table import LinksTableView
from app.views.widgets.link.columns import LinkTableColumn, sortable_columns
from app.views.widgets.link.sort_utils import sorted_links


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


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

    assert column == int(LinkTableColumn.ORDER)
    assert order == Qt.SortOrder.AscendingOrder


def test_initial_sort_uses_order_even_when_saved_sort_exists(qapp):
    table = LinksTableView()
    table._settings = type(
        "SettingsStub",
        (),
        {"get_table_sort": lambda self: (int(LinkTableColumn.ORDER), Qt.SortOrder.DescendingOrder)},
    )()

    column, order = table._load_initial_sort()

    assert column == int(LinkTableColumn.ORDER)
    assert order == Qt.SortOrder.AscendingOrder


def test_order_column_is_wide_enough_for_header(qapp):
    table = LinksTableView()

    assert table.columnWidth(int(LinkTableColumn.ORDER)) >= 112


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

    assert model.setData(
        model.index(2, int(LinkTableColumn.ORDER)), "1", Qt.ItemDataRole.EditRole
    )

    assert get_current_link_ids(table) == [3, 1, 2]
    assert [model.get_link(row)["position"] for row in range(model.rowCount())] == [0, 1, 2]
    assert emitted == [[3, 1, 2]]
    assert model.data(
        model.index(0, int(LinkTableColumn.ORDER)), Qt.ItemDataRole.DisplayRole
    ) == 1
    assert model.data(
        model.index(0, int(LinkTableColumn.TYPE)), Qt.ItemDataRole.DisplayRole
    )


def test_type_column_uses_link_dialog_labels(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(
        [
            {"id": 1, "name": "Web", "position": 0, "type": "web", "url": "https://a.example", "notes": ""},
            {"id": 2, "name": "App", "position": 1, "type": "program", "url": "C:/app.exe", "notes": ""},
        ]
    )

    assert model.data(
        model.index(0, int(LinkTableColumn.TYPE)), Qt.ItemDataRole.DisplayRole
    ) == QCoreApplication.translate("LinkDialogUI", "Web")
    assert model.data(
        model.index(1, int(LinkTableColumn.TYPE)), Qt.ItemDataRole.DisplayRole
    ) == QCoreApplication.translate("LinkDialogUI", "Application")


def test_header_labels_and_tooltips_are_localized(qapp):
    table = LinksTableView()
    model = table.model()

    assert model.headerData(
        int(LinkTableColumn.NAME),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.DisplayRole,
    ) == QCoreApplication.translate("LinksTableModel", "Name")
    assert model.headerData(
        int(LinkTableColumn.ORDER),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.DisplayRole,
    ) == QCoreApplication.translate("LinksTableModel", "Order")
    assert model.headerData(
        int(LinkTableColumn.LAUNCH),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.DisplayRole,
    ) == QCoreApplication.translate("LinksTableModel", "Launch")
    assert model.headerData(
        int(LinkTableColumn.NOTES),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.DisplayRole,
    ) == QCoreApplication.translate("LinksTableModel", "Notes")
    assert model.headerData(
        int(LinkTableColumn.TYPE),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.DisplayRole,
    ) == QCoreApplication.translate("LinksTableModel", "Type")

    assert model.headerData(
        int(LinkTableColumn.ORDER),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.ToolTipRole,
    ) == QCoreApplication.translate("LinksTableModel", "Custom order")
    assert model.headerData(
        int(LinkTableColumn.LAUNCH),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.ToolTipRole,
    ) == QCoreApplication.translate("LinksTableModel", "Last launch")
    assert model.headerData(
        int(LinkTableColumn.TYPE),
        Qt.Orientation.Horizontal,
        Qt.ItemDataRole.ToolTipRole,
    ) == QCoreApplication.translate("LinksTableModel", "Resource type")


def test_table_cell_tooltips_match_column_contract(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(
        [
            {
                "id": 1,
                "name": "Web",
                "position": 2,
                "type": "web",
                "url": "https://example.test/full",
                "notes": "Full note",
                "last_used": "2026-02-02T14:30:53",
            },
        ]
    )

    assert model.data(
        model.index(0, int(LinkTableColumn.ORDER)),
        Qt.ItemDataRole.ToolTipRole,
    ) == QCoreApplication.translate("LinksTableModel", "Position: {position}").format(
        position=3
    )
    assert model.data(
        model.index(0, int(LinkTableColumn.LAUNCH)),
        Qt.ItemDataRole.ToolTipRole,
    ) == "02.02.2026 14:30:53"
    assert "example.test" in model.data(
        model.index(0, int(LinkTableColumn.TYPE)),
        Qt.ItemDataRole.ToolTipRole,
    )


def test_body_cell_font_size_is_unified(qapp):
    table = LinksTableView()
    delegate = table.itemDelegate()

    sizes = {
        delegate._body_font_size_for_column(int(column))
        for column in (
            LinkTableColumn.NAME,
            LinkTableColumn.ORDER,
            LinkTableColumn.LAUNCH,
            LinkTableColumn.NOTES,
            LinkTableColumn.TYPE,
        )
    }

    assert len(sizes) == 1
    assert delegate._body_font_size_for_column(int(LinkTableColumn.GROUP_LAUNCH)) is None


def test_body_cell_color_roles_are_consistent(qapp):
    table = LinksTableView()
    delegate = table.itemDelegate()

    assert delegate._color_attr_for_column(int(LinkTableColumn.NAME)) == "primaryCellTextColor"
    assert delegate._color_attr_for_column(int(LinkTableColumn.NOTES)) == "primaryCellTextColor"
    assert delegate._color_attr_for_column(int(LinkTableColumn.ORDER)) == "secondaryCellTextColor"
    assert delegate._color_attr_for_column(int(LinkTableColumn.LAUNCH)) == "secondaryCellTextColor"
    assert delegate._color_attr_for_column(int(LinkTableColumn.TYPE)) == "secondaryCellTextColor"


def test_legacy_table_colors_populate_new_roles(qapp):
    table = LinksTableView()
    primary = QColor("#112233")
    secondary = QColor("#445566")

    table._set_notes_col_color(primary)
    table._set_opened_col_color(secondary)

    assert table.primaryCellTextColor == primary
    assert table.secondaryCellTextColor == secondary


def test_header_text_color_role_drives_header_glyphs(qapp):
    table = LinksTableView()
    header_color = QColor("#778899")

    table._set_table_header_text_color(header_color)

    assert table.tableHeaderTextColor == header_color
    assert table.horizontalHeader()._resolve_header_text_color() == header_color


def test_all_sortable_columns_sort_through_table_model(qapp):
    table = LinksTableView()
    model = table.model()
    links = [
        {
            "id": 1,
            "name": "Zulu",
            "position": 2,
            "last_used": "2026-03-01T10:00:00",
            "notes": "charlie",
            "type": "web",
        },
        {
            "id": 2,
            "name": "Alpha",
            "position": 0,
            "last_used": "",
            "notes": "bravo",
            "type": "program",
        },
        {
            "id": 3,
            "name": "Bravo",
            "position": 1,
            "last_used": "2026-01-01T10:00:00",
            "notes": "alpha",
            "type": "file",
        },
    ]
    model.set_links(links)

    expected_ids_by_column = {
        column: [
            int(link["id"])
            for link in sorted_links(
                links,
                column,
                type_label_getter=model._type_display_text,
            )
        ]
        for column in sortable_columns()
    }

    assert sortable_columns() == set(expected_ids_by_column)

    for column, expected_ids in expected_ids_by_column.items():
        model.set_links(links)
        table.sortByColumn(column, Qt.SortOrder.AscendingOrder)

        assert get_current_link_ids(table) == expected_ids, column


def test_category_switch_resets_to_default_order_sort(qapp):
    table = LinksTableView()
    first_category = [
        {"id": 1, "name": "Zulu", "position": 1, "type": "web", "url": "", "notes": ""},
        {"id": 2, "name": "Alpha", "position": 0, "type": "file", "url": "", "notes": ""},
    ]
    second_category = [
        {"id": 3, "name": "Alpha", "position": 2, "type": "web", "url": "", "notes": ""},
        {"id": 4, "name": "Zulu", "position": 0, "type": "file", "url": "", "notes": ""},
        {"id": 5, "name": "Bravo", "position": 1, "type": "folder", "url": "", "notes": ""},
    ]

    table.populate(first_category, mode="normal")
    table.sortByColumn(int(LinkTableColumn.NAME), Qt.SortOrder.AscendingOrder)
    assert get_current_link_ids(table) == [2, 1]

    table.reset_default_sort_for_next_populate()
    table.populate(second_category, mode="normal")

    assert get_current_link_ids(table) == [4, 5, 3]
    assert table.horizontalHeader().sortIndicatorSection() == int(LinkTableColumn.ORDER)
    assert table.horizontalHeader().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder


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
        mock_rebuild.assert_called_once()

    expected_order = [2, 4, 5, 1, 3]
    assert get_current_link_ids(table) == expected_order
    assert get_cached_link_ids(table) == expected_order
