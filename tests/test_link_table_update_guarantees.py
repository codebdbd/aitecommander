#!/usr/bin/env python3
"""Regression tests for targeted link table updates."""

import sys
from types import SimpleNamespace
from time import perf_counter
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.views.widgets.link.base_table import LinksTableView
from app.views.widgets.link.columns import LinkTableColumn
from app.core.database_manager import DatabaseManager
from app.controllers.ui.links.table_controller import LinksTableController
from app.controllers.ui.links.handlers import LinksUIHandlers

LARGE_CATEGORY_POPULATE_BUDGET_SECONDS = 2.0
TARGETED_ROW_UPDATE_BUDGET_SECONDS = 0.15


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _links():
    return [
        {
            "id": 1,
            "name": "Alpha",
            "position": 0,
            "type": "web",
            "url": "https://alpha.example",
            "notes": "first",
            "group_launch": False,
        },
        {
            "id": 2,
            "name": "Beta",
            "position": 1,
            "type": "file",
            "url": "C:/tmp/beta.txt",
            "notes": "second",
            "group_launch": True,
        },
    ]


def _many_links(count: int, *, start_id: int = 1) -> list[dict]:
    return [
        {
            "id": start_id + index,
            "name": f"Link {start_id + index:04d}",
            "position": index,
            "type": "web",
            "url": f"https://example.test/{start_id + index}",
            "notes": "",
            "group_launch": False,
        }
        for index in range(count)
    ]


def _link_ids(table: LinksTableView) -> list[int]:
    model = table.model()
    return [
        int(model.get_link(row)["id"])
        for row in range(model.rowCount())
        if model.get_link(row) is not None
    ]


def test_targeted_row_update_preserves_cached_row_shape_without_rebuild(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(_links())
    table.rebuild_cache_from_items()

    emitted_roles = []
    model.dataChanged.connect(
        lambda _top_left, _bottom_right, roles: emitted_roles.append(list(roles))
    )

    with patch.object(
        table, "rebuild_cache_from_items", wraps=table.rebuild_cache_from_items
    ) as rebuild_spy:
        assert table.update_link_by_id({"id": 2, "name": "Beta updated"})

    rebuild_spy.assert_not_called()
    qapp.processEvents()

    assert len(emitted_roles) == 1
    model_link = model.get_link(1)
    cached_link = table._link_cache[1]
    assert model_link["name"] == "Beta updated"
    assert model_link["url"] == "C:/tmp/beta.txt"
    assert model_link["type"] == "file"
    assert cached_link == model_link

    assert emitted_roles
    roles = emitted_roles[-1]
    assert Qt.ItemDataRole.DisplayRole in roles
    assert Qt.ItemDataRole.ToolTipRole in roles
    assert Qt.ItemDataRole.DecorationRole in roles
    assert Qt.ItemDataRole.CheckStateRole in roles


def test_incremental_populate_updates_existing_row_without_full_refresh(qapp):
    table = LinksTableView()
    initial_links = _links()
    table.populate(initial_links, mode="normal")
    qapp.processEvents()

    updated_links = [dict(link) for link in initial_links]
    updated_links[1]["notes"] = "changed"

    with (
        patch.object(table, "_full_populate", wraps=table._full_populate) as full_spy,
        patch.object(table.model(), "update_link", wraps=table.model().update_link) as update_spy,
    ):
        table.populate(updated_links, mode="normal")

    qapp.processEvents()

    full_spy.assert_not_called()
    update_spy.assert_called_once()
    assert table.model().get_link(1)["notes"] == "changed"
    assert table._link_cache[1]["notes"] == "changed"


def test_search_populate_skips_default_sort_initialization(qapp):
    table = LinksTableView()
    search_links = [
        {
            "id": 2,
            "name": "Beta",
            "position": 1,
            "type": "web",
            "url": "",
            "notes": "",
            "sphere_name": "Sphere",
            "section_name": "Section",
            "category_name": "Category",
        },
        {
            "id": 1,
            "name": "Alpha",
            "position": 0,
            "type": "file",
            "url": "",
            "notes": "",
            "sphere_name": "Sphere",
            "section_name": "Section",
            "category_name": "Category",
        },
    ]

    with patch.object(
        table,
        "ensure_initial_sort",
        wraps=table.ensure_initial_sort,
    ) as initial_sort_spy:
        table.populate(search_links, mode="search")

    initial_sort_spy.assert_not_called()
    assert table.model().rowCount() == 2


def test_incremental_populate_adds_and_deletes_without_model_reset(qapp):
    table = LinksTableView()
    table.populate(_links(), mode="normal")
    model = table.model()
    resets = []
    model.modelReset.connect(lambda *_args: resets.append(True))

    updated_links = [
        {
            "id": 2,
            "name": "Beta",
            "position": 0,
            "type": "file",
            "url": "C:/tmp/beta.txt",
            "notes": "second",
            "group_launch": True,
        },
        {
            "id": 3,
            "name": "Gamma",
            "position": 1,
            "type": "folder",
            "url": "C:/tmp",
            "notes": "third",
            "group_launch": False,
        },
    ]

    with (
        patch.object(model, "remove_row", wraps=model.remove_row) as remove_spy,
        patch.object(model, "insert_link", wraps=model.insert_link) as insert_spy,
    ):
        table.populate(updated_links, mode="normal")

    assert resets == []
    remove_spy.assert_called_once()
    insert_spy.assert_called_once()
    assert _link_ids(table) == [2, 3]
    assert table.get_cached_link_order() == [2, 3]


def test_incremental_populate_suspends_updates_around_batch(qapp):
    table = LinksTableView()
    initial_links = _links()
    table.populate(initial_links, mode="normal")

    updated_links = [dict(link) for link in initial_links]
    updated_links[0]["notes"] = "batched"
    update_states = []

    original_set_updates_enabled = table.setUpdatesEnabled

    def record_updates_enabled(value: bool) -> None:
        update_states.append(bool(value))
        original_set_updates_enabled(value)

    with (
        patch.object(table, "setUpdatesEnabled", side_effect=record_updates_enabled),
        patch.object(
            table, "_perform_incremental_update", wraps=table._perform_incremental_update
        ) as incremental_spy,
    ):
        table.populate(updated_links, mode="normal")

    incremental_spy.assert_called_once()
    assert update_states[0] is False
    assert update_states[-1] is True


def test_incremental_populate_restores_sort_once_after_batch(qapp):
    table = LinksTableView()
    initial_links = _links()
    table.populate(initial_links, mode="normal")
    table.sortByColumn(int(LinkTableColumn.NAME), Qt.SortOrder.AscendingOrder)

    updated_links = [dict(link) for link in initial_links]
    updated_links[1]["notes"] = "sort restore"

    with patch.object(
        table,
        "restore_sort_after_populate",
        wraps=table.restore_sort_after_populate,
    ) as restore_spy:
        table.populate(updated_links, mode="normal")

    restore_spy.assert_called_once()
    sort_col, sort_order, total_columns = restore_spy.call_args.args
    assert sort_col == int(LinkTableColumn.NAME)
    assert sort_order == Qt.SortOrder.AscendingOrder
    assert total_columns == table.model().columnCount()


def test_group_launch_checkbox_updates_without_model_reset(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(_links())

    roles_seen = []
    resets = []
    model.dataChanged.connect(
        lambda _top_left, _bottom_right, roles: roles_seen.append(list(roles))
    )
    model.modelReset.connect(lambda *_args: resets.append(True))

    assert model.setData(
        model.index(0, int(LinkTableColumn.GROUP_LAUNCH)),
        Qt.CheckState.Checked,
        Qt.ItemDataRole.CheckStateRole,
    )

    assert resets == []
    assert model.get_link(0)["is_group_launch"] == 1
    assert len(roles_seen) == 1
    assert roles_seen[-1] == [Qt.ItemDataRole.CheckStateRole]


def test_group_launch_checkbox_reads_persisted_setting(qapp):
    table = LinksTableView()
    model = table.model()
    links = _links()
    links[0]["is_group_launch"] = 1
    links[0].pop("group_launch", None)

    model.set_links(links)

    assert (
        model.data(
            model.index(0, int(LinkTableColumn.GROUP_LAUNCH)),
            Qt.ItemDataRole.CheckStateRole,
        )
        == Qt.CheckState.Checked
    )
    assert model.get_link(0)["is_group_launch"] == 1


def test_group_launch_checkbox_normalizes_legacy_field(qapp):
    table = LinksTableView()
    model = table.model()
    links = _links()
    links[1].pop("is_group_launch", None)
    links[1]["group_launch"] = True

    model.set_links(links)

    link = model.get_link(1)
    assert link["is_group_launch"] == 1
    assert link["group_launch"] is True
    assert (
        model.data(
            model.index(1, int(LinkTableColumn.GROUP_LAUNCH)),
            Qt.ItemDataRole.CheckStateRole,
        )
        == Qt.CheckState.Checked
    )


def test_group_launch_partial_update_preserves_persisted_setting(qapp):
    table = LinksTableView()
    model = table.model()
    links = _links()
    links[1]["is_group_launch"] = 1
    model.set_links(links)

    assert model.update_link(1, {"name": "Beta renamed"})

    link = model.get_link(1)
    assert link["name"] == "Beta renamed"
    assert link["is_group_launch"] == 1
    assert link["group_launch"] is True


def test_group_launch_toggle_dispatches_persistent_update(qapp):
    table = LinksTableView()
    model = table.model()
    model.set_links(_links())
    controller = LinksTableController(
        SimpleNamespace(),
        table=table,
        links_business=Mock(),
        category_provider=SimpleNamespace(current_category_id=1),
    )

    with patch("app.core.worker_manager.WorkerManager.run") as run_spy:
        assert model.setData(
            model.index(0, int(LinkTableColumn.GROUP_LAUNCH)),
            Qt.CheckState.Checked,
            Qt.ItemDataRole.CheckStateRole,
        )

    run_spy.assert_called_once()
    task, link_id, val_int = run_spy.call_args.args
    assert task == controller._update_group_launch_task
    assert link_id == 1
    assert val_int == 1


def test_group_launch_toggle_persists_setting_to_database(qapp, tmp_path):
    old_db_path = DatabaseManager._db_path
    old_global_pragmas_path = DatabaseManager._global_pragmas_applied_path
    db_path = tmp_path / "group_launch.db"
    try:
        DatabaseManager.close_all()
        DatabaseManager.configure(db_path)
        DatabaseManager.ensure_schema()

        with DatabaseManager.transaction() as conn:
            conn.execute("INSERT INTO sphere (id, name) VALUES (1, 'Sphere')")
            conn.execute("INSERT INTO section (id, sphere_id, name) VALUES (1, 1, 'Section')")
            conn.execute("INSERT INTO category (id, section_id, name) VALUES (1, 1, 'Category')")
            conn.execute(
                """
                INSERT INTO link
                    (id, category_id, name, url, type, is_group_launch, position)
                VALUES
                    (100, 1, 'Persisted', 'https://example.test', 'web', 0, 0)
                """
            )

        table = LinksTableView()
        model = table.model()
        model.set_links(
            [
                {
                    "id": 100,
                    "name": "Persisted",
                    "position": 0,
                    "type": "web",
                    "url": "https://example.test",
                    "notes": "",
                    "is_group_launch": 0,
                }
            ]
        )
        controller = LinksTableController(
            SimpleNamespace(),
            table=table,
            links_business=Mock(),
            category_provider=SimpleNamespace(current_category_id=1),
        )
        assert controller.table is table

        with patch(
            "app.core.worker_manager.WorkerManager.run",
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
        ):
            assert model.setData(
                model.index(0, int(LinkTableColumn.GROUP_LAUNCH)),
                Qt.CheckState.Checked,
                Qt.ItemDataRole.CheckStateRole,
            )

        row = DatabaseManager.get_connection().execute(
            "SELECT is_group_launch FROM link WHERE id = 100"
        ).fetchone()
        assert int(row["is_group_launch"]) == 1

        with patch(
            "app.core.worker_manager.WorkerManager.run",
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
        ):
            assert model.setData(
                model.index(0, int(LinkTableColumn.GROUP_LAUNCH)),
                Qt.CheckState.Unchecked,
                Qt.ItemDataRole.CheckStateRole,
            )

        row = DatabaseManager.get_connection().execute(
            "SELECT is_group_launch FROM link WHERE id = 100"
        ).fetchone()
        assert int(row["is_group_launch"]) == 0
    finally:
        DatabaseManager.close_all()
        DatabaseManager._db_path = old_db_path
        DatabaseManager._global_pragmas_applied_path = old_global_pragmas_path


def test_language_refresh_retranslates_model_once(qapp):
    table = LinksTableView()
    model = table.model()

    with patch.object(model, "retranslateUi", wraps=model.retranslateUi) as retranslate_spy:
        table._on_language_changed("de")

    retranslate_spy.assert_called_once()


def test_theme_style_refresh_updates_table_viewports(qapp):
    table = LinksTableView()
    body_viewport = table.viewport()
    header_viewport = table.horizontalHeader().viewport()

    with (
        patch.object(body_viewport, "update", wraps=body_viewport.update) as body_update,
        patch.object(
            header_viewport,
            "update",
            wraps=header_viewport.update,
        ) as header_update,
    ):
        table._set_primary_cell_text_color(QColor("#112233"))
        table._set_secondary_cell_text_color(QColor("#445566"))
        table._set_hover_row_color(QColor("#778899"))
        table._set_table_header_text_color(QColor("#abcdef"))

    assert body_update.call_count == 3
    header_update.assert_called_once()


def test_double_click_launches_only_resource_columns(qapp):
    handler = object.__new__(LinksUIHandlers)
    link = {"id": 1, "name": "Alpha", "type": "web", "url": "https://alpha.example"}
    handler.controller = Mock()
    handler.controller.get_link_at.return_value = link

    handler._on_double_click(0, int(LinkTableColumn.NAME))
    handler.controller.open_link.assert_called_once_with(link)

    handler.controller.open_link.reset_mock()
    handler._on_double_click(0, int(LinkTableColumn.ORDER))
    handler._on_double_click(0, int(LinkTableColumn.GROUP_LAUNCH))

    handler.controller.open_link.assert_not_called()


def test_direct_order_edit_reorders_without_model_reset_and_keeps_cache(qapp):
    table = LinksTableView()
    model = table.model()
    links = _links() + [
        {
            "id": 3,
            "name": "Gamma",
            "position": 2,
            "type": "folder",
            "url": "C:/tmp",
            "notes": "third",
            "group_launch": False,
        }
    ]
    model.set_links(links)
    table.rebuild_cache_from_items()

    layout_changes = []
    resets = []
    reordered = []
    model.layoutChanged.connect(lambda *_args: layout_changes.append(True))
    model.modelReset.connect(lambda *_args: resets.append(True))
    model.orderEdited.connect(reordered.append)

    assert model.setData(
        model.index(2, int(LinkTableColumn.ORDER)),
        "1",
        Qt.ItemDataRole.EditRole,
    )

    assert resets == []
    assert len(layout_changes) == 1
    assert reordered == [[3, 1, 2]]
    assert _link_ids(table) == [3, 1, 2]
    assert table.get_cached_link_order() == [3, 1, 2]
    assert [model.get_link(row)["position"] for row in range(model.rowCount())] == [0, 1, 2]


def test_large_category_populate_uses_single_full_refresh(qapp):
    table = LinksTableView()
    initial_links = _many_links(10)
    table.populate(initial_links, mode="normal")

    large_links = _many_links(900)

    with (
        patch.object(table, "_full_populate", wraps=table._full_populate) as full_spy,
        patch.object(
            table, "_perform_incremental_update", wraps=table._perform_incremental_update
        ) as incremental_spy,
    ):
        table.populate(large_links, mode="normal")

    full_spy.assert_called_once()
    incremental_spy.assert_not_called()
    assert table.model().rowCount() == 900


def test_mass_id_change_populate_uses_single_full_refresh(qapp):
    table = LinksTableView()
    table.populate(_many_links(500), mode="normal")

    changed_links = _many_links(500, start_id=10_000)

    with (
        patch.object(table, "_full_populate", wraps=table._full_populate) as full_spy,
        patch.object(
            table, "_perform_incremental_update", wraps=table._perform_incremental_update
        ) as incremental_spy,
    ):
        table.populate(changed_links, mode="normal")

    full_spy.assert_called_once()
    incremental_spy.assert_not_called()
    assert table.model().rowCount() == 500


def test_large_category_and_targeted_update_stay_within_smoke_budgets(qapp):
    table = LinksTableView()
    large_links = _many_links(900)

    started = perf_counter()
    table.populate(large_links, mode="normal")
    large_populate_seconds = perf_counter() - started

    started = perf_counter()
    assert table.update_link_by_id({"id": 450, "notes": "fast targeted update"})
    targeted_update_seconds = perf_counter() - started

    assert table.model().rowCount() == 900
    assert large_populate_seconds < LARGE_CATEGORY_POPULATE_BUDGET_SECONDS
    assert targeted_update_seconds < TARGETED_ROW_UPDATE_BUDGET_SECONDS
