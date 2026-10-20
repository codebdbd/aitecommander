import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.entities.link_model import ALLOWED_LINK_COLUMNS, LinkModel
from app.utils.naming import UniqueNameAllocator, generate_unique_name


@pytest.fixture
def repository():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    columns = [
        "id INTEGER PRIMARY KEY", "is_group_launch INTEGER DEFAULT 0",
        "position INTEGER", "category_id INTEGER",
    ]
    columns.extend(
        f"{name} TEXT" for name in sorted(
            ALLOWED_LINK_COLUMNS - {"id", "is_group_launch", "position", "category_id"}
        )
    )
    connection.execute(f"CREATE TABLE link ({', '.join(columns)})")
    connection.executemany(
        "INSERT INTO link(id, name, category_id, position) VALUES (?, ?, 1, ?)",
        [(i, f"Link {i}", i - 1) for i in range(1, 2002)],
    )
    connection.commit()
    yield LinkModel(SimpleNamespace(connection=connection)), connection
    connection.close()


def test_batch_lookup_preserves_order_with_bounded_queries(repository):
    repo, connection = repository
    queries = []
    connection.set_trace_callback(queries.append)
    ids = list(range(2001, 0, -1))
    result = repo.get_links_by_ids(ids + [2001, 99999])
    assert [row["id"] for row in result] == ids
    assert len([q for q in queries if q.startswith("SELECT")]) == 3


def test_group_marking_uses_one_transaction_and_keeps_unrelated_rows(repository):
    repo, connection = repository
    queries = []
    connection.set_trace_callback(queries.append)
    repo.update_group_launch_bulk(list(range(1, 2001)), 1)
    assert len([q for q in queries if q.startswith("UPDATE")]) == 3
    assert queries.count("COMMIT") == 1
    assert connection.execute("SELECT SUM(is_group_launch) FROM link").fetchone()[0] == 2000
    assert connection.execute("SELECT is_group_launch FROM link WHERE id=2001").fetchone()[0] == 0


def test_group_marking_rolls_back_all_chunks(repository, monkeypatch):
    repo, connection = repository
    execute = repo._execute_with_error_handling
    calls = []

    def failing_execute(*args, **kwargs):
        result = execute(*args, **kwargs)
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Failure after second chunk")
        return result

    monkeypatch.setattr(repo, "_execute_with_error_handling", failing_execute)
    with pytest.raises(RuntimeError):
        repo.update_group_launch_bulk(list(range(1, 2001)), 1)
    assert connection.execute("SELECT SUM(is_group_launch) FROM link").fetchone()[0] == 0


def test_move_names_and_positions_share_transaction(repository, monkeypatch):
    repo, connection = repository
    execute = repo._execute_many_with_error_handling

    def fail_names(query, params):
        result = execute(query, params)
        if "SET name" in query:
            raise RuntimeError("Rename failure")
        return result

    monkeypatch.setattr(repo, "_execute_many_with_error_handling", fail_names)
    with pytest.raises(RuntimeError):
        repo.batch_update_links([{"id": 1, "name": "Renamed", "position": 5, "category_id": 2}])
    row = repo.get_link_by_id(1)
    assert (row["name"], row["position"], row["category_id"]) == ("Link 1", 0, 1)
    monkeypatch.setattr(repo, "_execute_many_with_error_handling", execute)
    repo.batch_update_links([{"id": 1, "name": "Renamed", "position": 5, "category_id": 2}])
    row = repo.get_link_by_id(1)
    assert (row["name"], row["position"], row["category_id"]) == ("Renamed", 5, 2)


def test_bulk_group_marking_dispatches_one_worker(qapp, monkeypatch):
    from app.controllers.ui.links.table_controller import LinksTableController
    from app.core.worker_manager import WorkerManager
    from app.views.widgets.link.links_model import LinksTableModel

    model = LinksTableModel()
    model._links = [{"id": i} for i in range(1, 30001)]
    table = SimpleNamespace(model=lambda: model, populate=Mock(), update_link_by_id=Mock())
    controller = LinksTableController(
        SimpleNamespace(), table=table, links_business=Mock(),
        category_provider=SimpleNamespace(current_category_id=1),
    )
    run = Mock()
    monkeypatch.setattr(WorkerManager, "run", run)
    model.set_all_group_launch(1)
    run.assert_called_once_with(
        controller._update_group_launch_batch_task, list(range(1, 30001)), 1
    )


def test_name_allocator_matches_existing_naming_rules():
    names = {" Report ", "Report (1)", "Report (3)", "STRASSE", "Отчёт"}
    allocator = UniqueNameAllocator(names)
    for base in ["Report", "report (3)", "Straße", "Отчёт", "New"] * 100:
        expected = generate_unique_name(names, base)
        assert allocator.suggest(base) == expected
        names.add(expected)
        allocator.add(expected)


def test_move_preparation_reads_once_and_does_not_scan_duplicates():
    from app.utils.ui.dnd.links_command import MoveLinksCommand

    rows = [{"id": i, "name": str(i), "url": str(i), "args": "", "category_id": 1}
            for i in range(1, 2001)]
    service = SimpleNamespace(get_links_by_ids=Mock(return_value=rows))
    business = SimpleNamespace(
        links=service, get_next_position=lambda _: 0, get_links=lambda _: rows,
    )
    command = MoveLinksCommand((i for i in range(1, 2001)), 2, SimpleNamespace(links_business=business))
    command._is_duplicate = Mock(side_effect=AssertionError("Full duplicate scan"))
    command._prepare_data()
    service.get_links_by_ids.assert_called_once()
    assert len(command._new_states) == 2000
    assert command._new_states[0]["name"] == "1 (1)"
    assert command._new_states[-1]["name"] == "2000 (1)"


def test_section_export_fetches_links_in_batch():
    from app.models.managers.import_export_manager import ImportExportManager

    categories = [{"id": i} for i in range(1000)]
    links = SimpleNamespace(get_links_for_categories=Mock(return_value={2: [{"id": 9}]}))
    db = SimpleNamespace(
        sections=SimpleNamespace(get_section_by_id=lambda _: {"id": 1}),
        categories=SimpleNamespace(get_categories=lambda _: categories),
        links=links,
    )
    result = ImportExportManager(db).export_section_tree(1)
    links.get_links_for_categories.assert_called_once_with(list(range(1000)))
    assert result["categories"][2]["links"] == [{"id": 9}]
    assert result["categories"][3]["links"] == []


def test_paste_sections_loads_target_once_and_sees_new_sections():
    from app.services.structure_context_service import StructureContextService

    service = object.__new__(StructureContextService)
    service.db = SimpleNamespace(
        sections=SimpleNamespace(get_sections=Mock(return_value=[])),
        import_section_tree=Mock(return_value=7),
    )
    service._merge_section_tree_into_section = Mock()
    tree = {"section": {"name": "Same"}, "categories": []}
    result = service.paste_section_trees_to_sphere([tree, tree], 1)
    service.db.sections.get_sections.assert_called_once_with(1)
    service.db.import_section_tree.assert_called_once()
    service._merge_section_tree_into_section.assert_called_once()
    assert result["created_section_ids"] == [7]
    assert result["merged_section_ids"] == [7]


def test_quick_add_multiple_links_pushes_one_batch_command(monkeypatch):
    from PyQt6.QtWidgets import QDialog

    import app.controllers.ui.dialogs as dialogs
    import app.controllers.ui.links.link_operations as operations
    import app.views.windows.dialogs.link_dialog.link_dialog as dialog_module

    rows = [{"name": "A"}, {"name": "B"}]
    controller = SimpleNamespace(
        get_initialization_data=lambda *_: {}, get_result_data=lambda: rows
    )
    monkeypatch.setattr(dialogs, "LinkDialogController", lambda *args, **kwargs: controller)
    monkeypatch.setattr(dialog_module, "LinkDialog", lambda **kwargs: SimpleNamespace(
        set_link_type=lambda _: None, exec=lambda: QDialog.DialogCode.Accepted
    ))
    batch = Mock()
    monkeypatch.setattr(operations, "BatchSaveLinksCmd", batch)
    main = SimpleNamespace(undo_stack=SimpleNamespace(push=Mock()))
    component = SimpleNamespace(
        main=main, business=SimpleNamespace(db=None), _validate_category_exists=lambda cid: cid,
    )
    operations.LinksUILinkOperations.quick_add_link(component, "web", 1)
    batch.assert_called_once_with(links_data=rows, _old_link_data=None, main_window=main)
    main.undo_stack.push.assert_called_once_with(batch.return_value)


def test_group_launch_keeps_order_limit_and_delays(monkeypatch):
    from PyQt6.QtCore import QTimer

    from app.controllers.ui.links.controller import LinksUIController

    pending = []
    monkeypatch.setattr(QTimer, "singleShot", lambda delay, callback: pending.append((delay, callback)))
    opened = []
    controller = SimpleNamespace(
        link_ops=SimpleNamespace(_open_link=opened.append), _get_delay_ms_for_link=lambda _: 25
    )
    rows = [{"id": i} for i in range(5)]
    LinksUIController._open_links_sequentially(controller, rows, max_total=3)
    while pending:
        delay, callback = pending.pop(0)
        assert delay == 25
        callback()
    assert opened == rows[:3]
