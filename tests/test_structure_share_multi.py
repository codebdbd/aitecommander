from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel, QUndoStack
from PyQt6.QtWidgets import QMenu, QWidget

from app.utils.ui.menu_builders.menu_actions import MenuTexts, StructureItemType
from app.utils.ui.menu_builders.structure_menu_builder import StructureMenuBuilder
from app.views.windows.main_window import MainWindow


class _FakeDb:
    def __init__(self) -> None:
        self.sections: dict[int, dict] = {
            10: {"id": 10, "name": "Section A", "sphere_id": 1},
            20: {"id": 20, "name": "Section B", "sphere_id": 1},
        }
        self.section_trees: dict[int, dict] = {
            10: {
                "section": {"id": 10, "name": "Section A", "sphere_id": 1},
                "categories": [],
            },
            20: {
                "section": {"id": 20, "name": "Section B", "sphere_id": 1},
                "categories": [],
            },
        }

    def transaction(self):
        return nullcontext()


class _FakeStructureService:
    def __init__(self, db: _FakeDb) -> None:
        self.db = db

    def export_section_tree(self, section_id: int) -> dict:
        return deepcopy(
            self.db.section_trees.get(section_id, {"section": {"id": section_id}})
        )

    def get_sections(self, sphere_id: int) -> list[dict]:
        return [
            deepcopy(s)
            for s in self.db.sections.values()
            if s.get("sphere_id") == sphere_id
        ]

    def get_section_by_id(self, section_id: int) -> dict | None:
        return deepcopy(self.db.sections.get(section_id))


class _FakeTree(QWidget):
    def __init__(self, items: list[QStandardItem], model: QStandardItemModel) -> None:
        super().__init__()
        self._items = items
        self._model = model

    def selectionModel(self):
        items = self._items
        model = self._model

        class _SelModel:
            def selectedRows(self, _col=0):
                return [model.indexFromItem(it) for it in items]

        return _SelModel()


def test_structure_menu_builder_single_section_actions(qapp, monkeypatch) -> None:
    main_window = SimpleNamespace(
        settings=SimpleNamespace(get_theme=lambda: "dark"),
        action_controller=None,
        add_new_category=lambda: None,
        edit_structure_item=lambda _item: None,
        share_section=lambda _sid: None,
        share_sections=lambda _sids: None,
        import_category_to_section=lambda _sid: None,
        import_section_to_current_sphere=lambda: None,
    )
    model = QStandardItemModel()
    item = QStandardItem("Section A")
    item.setData((StructureItemType.SECTION, 10), Qt.ItemDataRole.UserRole)
    model.appendRow(item)

    tree = _FakeTree([item], model)
    builder = StructureMenuBuilder(tree, main_window)
    monkeypatch.setattr(builder, "_create_context_action", lambda *a, **k: None)

    menu = QMenu(tree)
    builder._add_section_actions(
        menu, model.indexFromItem(item), 10, lambda _item: None
    )

    action_texts = [a.text() for a in menu.actions()]
    expected_export = QCoreApplication.translate(
        "MenuActions", MenuTexts.EXPORT_SECTION
    )
    expected_exports = QCoreApplication.translate(
        "MenuActions", MenuTexts.EXPORT_SECTIONS
    )
    expected_add_cat = QCoreApplication.translate("MenuActions", MenuTexts.ADD_CATEGORY)
    expected_edit_sec = QCoreApplication.translate(
        "MenuActions", MenuTexts.EDIT_SECTION
    )

    assert any(expected_export in t for t in action_texts)
    assert not any(expected_exports in t for t in action_texts)
    assert any(expected_add_cat in t for t in action_texts)
    assert any(expected_edit_sec in t for t in action_texts)


def test_structure_menu_builder_multiple_sections_actions(qapp, monkeypatch) -> None:
    called_with = []
    main_window = SimpleNamespace(
        settings=SimpleNamespace(get_theme=lambda: "dark"),
        action_controller=None,
        add_new_category=lambda: None,
        edit_structure_item=lambda _item: None,
        share_section=lambda _sid: None,
        share_sections=lambda sids: called_with.append(sids),
        import_category_to_section=lambda _sid: None,
        import_section_to_current_sphere=lambda: None,
    )
    model = QStandardItemModel()
    item1 = QStandardItem("Section A")
    item1.setData((StructureItemType.SECTION, 10), Qt.ItemDataRole.UserRole)
    item2 = QStandardItem("Section B")
    item2.setData((StructureItemType.SECTION, 20), Qt.ItemDataRole.UserRole)
    model.appendRow(item1)
    model.appendRow(item2)

    tree = _FakeTree([item1, item2], model)
    builder = StructureMenuBuilder(tree, main_window)
    monkeypatch.setattr(builder, "_create_context_action", lambda *a, **k: None)

    menu = QMenu(tree)
    builder._add_section_actions(
        menu, model.indexFromItem(item1), 10, lambda _item: None
    )

    action_texts = [a.text() for a in menu.actions()]
    expected_exports = QCoreApplication.translate(
        "MenuActions", MenuTexts.EXPORT_SECTIONS
    )
    expected_add_cat = QCoreApplication.translate("MenuActions", MenuTexts.ADD_CATEGORY)
    expected_edit_sec = QCoreApplication.translate(
        "MenuActions", MenuTexts.EDIT_SECTION
    )

    assert any(expected_exports in t for t in action_texts)
    assert not any(expected_add_cat in t for t in action_texts)
    assert not any(expected_edit_sec in t for t in action_texts)

    # Trigger export sections action
    export_action = next(a for a in menu.actions() if expected_exports in a.text())
    export_action.trigger()
    assert called_with == [[10, 20]]


def test_main_window_share_sections_exports_multiple_files(
    qapp, tmp_path: Path
) -> None:
    db = _FakeDb()
    structure_service = _FakeStructureService(db)

    class _FakeShareService:
        def __init__(self, ss) -> None:
            self._ss = ss

        def build_filename(self, pkg_type: str, name: str) -> str:
            return f"{name}.aitesec"

        def export_section_archive(self, section_id: int, dest_path: Path) -> None:
            dest_path.write_text(f"archive_{section_id}", encoding="utf-8")

    class _FakeFacade:
        @staticmethod
        def resolve_export_item_name(sb, pkg_type, sid):
            return f"Section_{sid}"

    class _WinStub:
        def _get_structure_share_service(self, _title):
            return SimpleNamespace(
                structure_service=structure_service
            ), _FakeShareService(structure_service)

        def _require_facade(self):
            return _FakeFacade()

        def share_section(self, sid):
            pass

    win = _WinStub()
    with (
        patch(
            "app.services.dialog_path_service.DialogPathService.get_downloads_dir",
            return_value=str(tmp_path),
        ),
        patch("app.services.dialog_path_service.DialogPathService.remember_dir"),
        patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value=str(tmp_path),
        ),
        patch("app.views.windows.main_window.set_status_message") as mock_status,
        patch("PyQt6.QtGui.QDesktopServices.openUrl"),
    ):
        MainWindow.share_sections(win, [10, 20])

    exported_files = sorted(list(tmp_path.glob("*.aitesec")))
    assert len(exported_files) == 2
    assert (tmp_path / "Section_10.aitesec").is_file()
    assert (tmp_path / "Section_20.aitesec").is_file()
    assert mock_status.called


def test_main_window_import_structure_package_multiple_files(
    qapp, tmp_path: Path
) -> None:
    db = _FakeDb()
    structure_service = _FakeStructureService(db)
    undo_stack = QUndoStack()

    p1 = tmp_path / "sec1.aitesec"
    p2 = tmp_path / "sec2.aitesec"
    p1.write_text("pkg1", encoding="utf-8")
    p2.write_text("pkg2", encoding="utf-8")

    imported_paths = []

    class _WinStub:
        def __init__(self) -> None:
            self.undo_stack = undo_stack
            self.refreshed = False

        def get_undo_stack(self):
            return self.undo_stack

        def _get_structure_share_service(self, _title):
            return SimpleNamespace(
                structure_service=structure_service
            ), SimpleNamespace()

        def _choose_archive_open_paths(self, **_kwargs):
            return [p1, p2]

        def _import_structure_archive_with_undo(self, *, archive_path, **_kwargs):
            imported_paths.append(archive_path)
            return True

        def _refresh_structure_after_import(self, **_kwargs):
            self.refreshed = True

    win = _WinStub()
    with patch("app.views.windows.main_window.set_status_message"):
        MainWindow._import_structure_package(win, "section", 1)

    assert imported_paths == [p1, p2]
    assert win.refreshed is True


def test_main_window_import_archive_files_multiple(qapp, tmp_path: Path) -> None:
    p1 = tmp_path / "sec1.aitesec"
    p2 = tmp_path / "sec2.aitesec"
    p1.write_text("pkg1", encoding="utf-8")
    p2.write_text("pkg2", encoding="utf-8")

    imported = []
    undo_stack = QUndoStack()

    class _WinStub:
        def __init__(self) -> None:
            self.undo_stack = undo_stack
            self.refreshed = False

        def get_undo_stack(self):
            return self.undo_stack

        def import_archive_file(self, archive_path, **kwargs):
            imported.append(archive_path)
            return True

        def _refresh_structure_after_import(self, **_kwargs):
            self.refreshed = True

    win = _WinStub()
    with patch("app.views.windows.main_window.set_status_message"):
        res = MainWindow.import_archive_files(win, [p1, p2])

    assert res is True
    assert imported == [p1, p2]
    assert win.refreshed is True
