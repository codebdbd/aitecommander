"""Tests for Local Path Health Radar (worker, folder propagation, BatchRelinkCmd, and dialog)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtGui import QUndoStack
from PyQt6.QtWidgets import QApplication

from app.controllers.services.link_health_service import LinkHealthService
from app.controllers.ui.undo.commands_links import BatchRelinkCmd
from app.core.database_manager import DatabaseManager
from app.models import Database
from app.models.workers.link_health_worker import (
    LinkHealthWorker,
    propagate_folder_relink,
)
from app.services.links_service import LinksService
from app.views.windows.dialogs.health_radar_dialog import HealthRadarDialog

_QAPP: QApplication | None = None


def _open_test_db(db_file: Path) -> Database:
    global _QAPP
    _QAPP = QApplication.instance() or QApplication([])  # type: ignore[assignment]
    DatabaseManager.close_all()
    DatabaseManager.configure(db_file)
    DatabaseManager.ensure_schema()
    return Database()


def _seed_test_hierarchy(db: Database) -> int:
    """Create a test sphere, section, and category and return category_id."""
    conn = db.connection
    cur = conn.execute(
        "INSERT INTO sphere (name, position) VALUES (?, ?)",
        ("WorkSphere", 1),
    )
    sphere_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO section (sphere_id, name, position) VALUES (?, ?, ?)",
        (sphere_id, "DevSection", 1),
    )
    section_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO category (section_id, name, position) VALUES (?, ?, ?)",
        (section_id, "ToolsCategory", 1),
    )
    category_id = int(cur.lastrowid)
    conn.commit()
    return category_id


def test_link_health_worker_detects_and_auto_discovers_moved_paths(tmp_path: Path) -> None:
    """Worker should skip healthy paths, auto-discover moved files/versioned folders, and detect duplicates."""
    db_file = tmp_path / "health_test.db"
    db = _open_test_db(db_file)
    try:
        cat_id = _seed_test_hierarchy(db)
        links_svc = LinksService(db)

        # 1. Healthy local file
        healthy_file = tmp_path / "healthy" / "readme.txt"
        healthy_file.parent.mkdir(parents=True, exist_ok=True)
        healthy_file.write_text("ok", encoding="utf-8")

        # 2. Moved file into a sibling/child folder
        old_project_dir = tmp_path / "workspace" / "old_loc"
        new_project_dir = tmp_path / "workspace" / "new_loc"
        new_project_dir.mkdir(parents=True, exist_ok=True)
        moved_script = new_project_dir / "deploy.ps1"
        moved_script.write_text("Write-Host 'hi'", encoding="utf-8")

        # 3. Versioned directory upgrade (Tool v1.0 -> Tool v1.2)
        apps_root = tmp_path / "apps"
        new_app_bin = apps_root / "Tool v1.2" / "bin"
        new_app_bin.mkdir(parents=True, exist_ok=True)
        moved_exe = new_app_bin / "runner.exe"
        moved_exe.write_bytes(b"MZ")

        # 4. Completely missing file
        missing_file = tmp_path / "nowhere" / "ghost.txt"

        # 5. Duplicate collision: broken link whose moved target already exists as another link in same category
        dup_dir = tmp_path / "dup_area"
        dup_new_dir = dup_dir / "relocated"
        dup_new_dir.mkdir(parents=True, exist_ok=True)
        dup_target = dup_new_dir / "report.pdf"
        dup_target.write_bytes(b"%PDF")

        # Insert links
        links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Healthy Doc",
                "url": str(healthy_file),
                "type": "file",
                "position": 1,
            }
        )
        moved_script_id = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Deploy Script",
                "url": str(old_project_dir / "deploy.ps1"),
                "type": "script",
                "position": 2,
            }
        )
        versioned_exe_id = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Tool Runner",
                "url": str(apps_root / "Tool v1.0" / "bin" / "runner.exe"),
                "type": "program",
                "position": 3,
            }
        )
        missing_id = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Ghost File",
                "url": str(missing_file),
                "type": "file",
                "position": 4,
            }
        )
        # Existing valid link with same (category_id, name, url, args)
        links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Dup Report",
                "url": str(dup_target),
                "type": "file",
                "args": "",
                "position": 5,
            }
        )
        # Broken link with same name/args whose relocated target matches the existing link
        dup_broken_id = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Dup Report",
                "url": str(dup_dir / "old_place" / "report.pdf"),
                "type": "file",
                "args": "",
                "position": 6,
            }
        )

        worker = LinkHealthWorker(db)
        finished_payloads: list[list[dict]] = []
        worker.signals.finished.connect(lambda items: finished_payloads.append(items))
        worker.run()

        assert len(finished_payloads) == 1
        issues = {int(item["id"]): item for item in finished_payloads[0]}

        # Healthy file must not be in issues
        assert len(issues) == 4

        # Moved script should be auto-discovered
        assert issues[moved_script_id]["status"] == LinkHealthWorker.STATUS_FIX_FOUND
        assert Path(issues[moved_script_id]["suggested_url"]) == moved_script

        # Versioned program should be auto-discovered
        assert issues[versioned_exe_id]["status"] == LinkHealthWorker.STATUS_FIX_FOUND
        assert Path(issues[versioned_exe_id]["suggested_url"]) == moved_exe

        # Missing file should be STATUS_NOT_FOUND
        assert issues[missing_id]["status"] == LinkHealthWorker.STATUS_NOT_FOUND
        assert issues[missing_id]["suggested_url"] == ""

        # Duplicate target in same category should be STATUS_DUPLICATE_EXISTS
        assert (
            issues[dup_broken_id]["status"]
            == LinkHealthWorker.STATUS_DUPLICATE_EXISTS
        )
        assert Path(issues[dup_broken_id]["suggested_url"]) == dup_target
    finally:
        DatabaseManager.close_all()


def test_propagate_folder_relink_resolves_siblings(tmp_path: Path) -> None:
    """Locating one moved file should automatically resolve sibling broken links in the same folder tree."""
    old_root = tmp_path / "OldWorkspace" / "ProjectA"
    new_root = tmp_path / "MovedArchive" / "2026" / "ProjectA"
    (new_root / "sub").mkdir(parents=True, exist_ok=True)

    file_a = new_root / "main.py"
    file_b = new_root / "sub" / "helper.py"
    file_a.write_text("# main", encoding="utf-8")
    file_b.write_text("# helper", encoding="utf-8")

    items = [
        {
            "id": 10,
            "category_id": 1,
            "name": "Main",
            "url": str(old_root / "main.py"),
            "suggested_url": str(file_a),
            "status": LinkHealthWorker.STATUS_FIX_FOUND,
            "type": "script",
            "args": "",
        },
        {
            "id": 11,
            "category_id": 1,
            "name": "Helper",
            "url": str(old_root / "sub" / "helper.py"),
            "suggested_url": "",
            "status": LinkHealthWorker.STATUS_NOT_FOUND,
            "type": "script",
            "args": "",
        },
    ]

    updated_ids = propagate_folder_relink(
        items,
        str(old_root / "main.py"),
        str(file_a),
    )

    assert updated_ids == [11]
    assert items[1]["status"] == LinkHealthWorker.STATUS_FIX_FOUND
    assert Path(items[1]["suggested_url"]) == file_b


def test_batch_relink_cmd_redo_and_undo_in_place(tmp_path: Path) -> None:
    """BatchRelinkCmd must update URLs in-place on redo() and restore exact original URLs on undo() without touching disk files."""
    db_file = tmp_path / "relink_undo.db"
    db = _open_test_db(db_file)
    try:
        cat_id = _seed_test_hierarchy(db)
        links_svc = LinksService(db)

        script_file = tmp_path / "new_dir" / "my_script.ps1"
        script_file.parent.mkdir(parents=True, exist_ok=True)
        original_disk_bytes = b"# Sacred user script content - DO NOT OVERWRITE"
        script_file.write_bytes(original_disk_bytes)

        old_url = str(tmp_path / "old_dir" / "my_script.ps1")
        new_url = str(script_file)

        link_id = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Sacred Script",
                "url": old_url,
                "type": "script",
                "notes": "important note",
                "is_favorite": 1,
                "is_group_launch": 1,
                "args": "--fast",
                "position": 7,
            }
        )

        row_before = dict(
            db.connection.execute(
                "SELECT * FROM link WHERE id = ?", (link_id,)
            ).fetchone()
        )
        new_row = dict(row_before)
        new_row["url"] = new_url

        fake_main_window = SimpleNamespace(
            database_controller=SimpleNamespace(db=db),
            links_business=SimpleNamespace(
                links=links_svc,
                batch_updated=MagicMock(),
                invalidate_cache=MagicMock(),
            ),
            link_operations=SimpleNamespace(emit_top_panels_changed=MagicMock()),
            links_actions=SimpleNamespace(
                schedule_restore_selection_multiple=MagicMock()
            ),
        )

        undo_stack = QUndoStack()
        cmd = BatchRelinkCmd([row_before], [new_row], fake_main_window)
        undo_stack.push(cmd)

        # Verify redo updated URL in-place while preserving ID, notes, favorite, position
        row_after_redo = dict(
            db.connection.execute(
                "SELECT * FROM link WHERE id = ?", (link_id,)
            ).fetchone()
        )
        assert row_after_redo["id"] == link_id
        assert row_after_redo["url"] == new_url
        assert row_after_redo["notes"] == "important note"
        assert row_after_redo["is_favorite"] == 1
        assert row_after_redo["is_group_launch"] == 1
        assert row_after_redo["position"] == row_before["position"]
        assert script_file.read_bytes() == original_disk_bytes

        # Undo via QUndoStack
        undo_stack.undo()
        row_after_undo = dict(
            db.connection.execute(
                "SELECT * FROM link WHERE id = ?", (link_id,)
            ).fetchone()
        )
        assert row_after_undo["id"] == link_id
        assert row_after_undo["url"] == old_url
        assert row_after_undo["notes"] == "important note"
        assert row_after_undo["is_favorite"] == 1
        assert row_after_undo["position"] == row_before["position"]
        assert script_file.read_bytes() == original_disk_bytes
    finally:
        DatabaseManager.close_all()


def test_health_radar_dialog_workflow(tmp_path: Path) -> None:
    """HealthRadarDialog should populate issues, propagate manual locations, and push BatchRelinkCmd to undo_stack."""
    db_file = tmp_path / "dialog_test.db"
    db = _open_test_db(db_file)
    try:
        cat_id = _seed_test_hierarchy(db)
        links_svc = LinksService(db)

        old_dir = tmp_path / "old_folder"
        new_dir = tmp_path / "relocated_folder"
        new_dir.mkdir(parents=True, exist_ok=True)
        target_a = new_dir / "alpha.txt"
        target_b = new_dir / "beta.txt"
        target_a.write_text("alpha", encoding="utf-8")
        target_b.write_text("beta", encoding="utf-8")

        id_a = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Alpha File",
                "url": str(old_dir / "alpha.txt"),
                "type": "file",
                "position": 1,
            }
        )
        id_b = links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Beta File",
                "url": str(old_dir / "beta.txt"),
                "type": "file",
                "position": 2,
            }
        )

        row_a = dict(
            db.connection.execute("SELECT * FROM link WHERE id = ?", (id_a,)).fetchone()
        )
        row_b = dict(
            db.connection.execute("SELECT * FROM link WHERE id = ?", (id_b,)).fetchone()
        )

        undo_stack = QUndoStack()
        fake_main = SimpleNamespace(
            database_controller=SimpleNamespace(db=db),
            links_business=SimpleNamespace(
                links=links_svc,
                batch_updated=MagicMock(),
                invalidate_cache=MagicMock(),
            ),
            link_operations=SimpleNamespace(emit_top_panels_changed=MagicMock()),
            links_actions=SimpleNamespace(
                schedule_restore_selection_multiple=MagicMock()
            ),
            undo_stack=undo_stack,
        )

        service = LinkHealthService(db)
        dlg = HealthRadarDialog(service, db, parent=None)
        dlg._main_window = fake_main

        # Simulate finished scan where both items are initially not_found
        issues = [
            {
                "id": id_a,
                "category_id": cat_id,
                "name": "Alpha File",
                "url": str(old_dir / "alpha.txt"),
                "suggested_url": "",
                "status": LinkHealthWorker.STATUS_NOT_FOUND,
                "type": "file",
                "args": "",
                "category_path": "WorkSphere / DevSection / ToolsCategory",
                "hierarchy": {"sphere_name": "WorkSphere"},
                "link_data": row_a,
            },
            {
                "id": id_b,
                "category_id": cat_id,
                "name": "Beta File",
                "url": str(old_dir / "beta.txt"),
                "suggested_url": "",
                "status": LinkHealthWorker.STATUS_NOT_FOUND,
                "type": "file",
                "args": "",
                "category_path": "WorkSphere / DevSection / ToolsCategory",
                "hierarchy": {"sphere_name": "WorkSphere"},
                "link_data": row_b,
            },
        ]
        dlg._on_finished(issues)
        assert dlg.table_widget.rowCount() == 2

        # Manually locate Alpha File -> Beta File should auto-resolve via folder propagation!
        updated_ids = dlg.apply_manual_location(id_a, str(target_a))
        assert set(updated_ids) == {id_a, id_b}
        assert dlg.relink_button.isEnabled()

        # Click Relink Selected -> both links should be updated in DB and undoable via undo_stack
        dlg._on_relink_selected()
        assert dlg.table_widget.rowCount() == 0

        db_url_a = db.connection.execute(
            "SELECT url FROM link WHERE id = ?", (id_a,)
        ).fetchone()["url"]
        db_url_b = db.connection.execute(
            "SELECT url FROM link WHERE id = ?", (id_b,)
        ).fetchone()["url"]
        assert Path(db_url_a) == target_a
        assert Path(db_url_b) == target_b

        # Undo via undo_stack
        undo_stack.undo()
        db_url_a_undo = db.connection.execute(
            "SELECT url FROM link WHERE id = ?", (id_a,)
        ).fetchone()["url"]
        assert db_url_a_undo == str(old_dir / "alpha.txt")

        # Verify retranslateUi runs cleanly
        dlg.retranslateUi()
        dlg.close()
    finally:
        DatabaseManager.close_all()



def test_system_dialog_controller_launches_health_radar_end_to_end(tmp_path: Path) -> None:
    """SystemDialogController.handle_check_local_paths must register with real AppShutdownController and run WorkerManager without errors."""
    import time

    from PyQt6.QtCore import Qt, QThreadPool
    from PyQt6.QtWidgets import QMainWindow

    from app.controllers.system.app_shutdown_controller import AppShutdownController
    from app.controllers.ui.dialogs import DialogManager
    from app.controllers.ui.dialogs.system_dialog_controller import (
        SystemDialogController,
    )
    from app.core.worker_manager import WorkerManager
    from app.utils.ui.menu_builders.base import get_menu_icon

    db_file = tmp_path / "e2e_health.db"
    db = _open_test_db(db_file)
    win = QMainWindow()
    try:
        cat_id = _seed_test_hierarchy(db)
        links_svc = LinksService(db)
        links_svc.create_or_update_link(
            {
                "category_id": cat_id,
                "name": "Missing App",
                "url": str(tmp_path / "missing_dir" / "app.exe"),
                "type": "program",
            }
        )

        # Verify folder_check icon resolves to a valid non-null QIcon
        icon = get_menu_icon("folder_check", "dark")
        assert not icon.isNull()

        shutdown_ctrl = AppShutdownController(win)
        win.app_shutdown = shutdown_ctrl  # type: ignore[attr-defined]
        win.structure_business = SimpleNamespace(db=db)  # type: ignore[attr-defined]

        sys_ctrl = SystemDialogController(
            win,
            database_controller=MagicMock(),
            links_table_controller=MagicMock(),
            links_business=MagicMock(),
        )

        sys_ctrl.handle_check_local_paths()
        service = sys_ctrl._link_health_service
        assert service is not None
        dlg = service._active_dialog
        assert dlg is not None

        # Wait for WorkerManager pool and process Qt events
        deadline = time.monotonic() + 6.0
        while not dlg._is_finished and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.02)
        WorkerManager.shutdown(3000)

        assert dlg._is_finished is True
        assert dlg.table_widget.rowCount() == 1

        # Check the row and test _on_delete_selected with confirmation
        chk_item = dlg.table_widget.item(0, dlg.COL_CHECK)
        assert chk_item is not None
        chk_item.setCheckState(Qt.CheckState.Checked)

        orig_ask = DialogManager.ask_confirmation
        DialogManager.ask_confirmation = staticmethod(lambda *a, **kw: True)  # type: ignore[method-assign]
        try:
            dlg._on_delete_selected()
        finally:
            DialogManager.ask_confirmation = orig_ask  # type: ignore[method-assign]

        # Wait for async DB deletion task on QThreadPool before closing DB
        QThreadPool.globalInstance().waitForDone(3000)
        QApplication.processEvents()

        assert dlg.table_widget.rowCount() == 0
        dlg.close()
    finally:
        QThreadPool.globalInstance().waitForDone(3000)
        win.close()
        DatabaseManager.close_all()
