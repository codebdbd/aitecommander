from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtGui import QUndoStack

from app.controllers.ui.undo.commands_structure import ImportStructurePackageCmd
from app.core.results import Result
from app.views.windows.main_window import MainWindow


class _FakeDatabase:
    def __init__(self) -> None:
        self.category_tree: dict | None = None
        self.section_tree: dict | None = None
        self.links = self

    def transaction(self):
        return nullcontext()

    def batch_delete_links(self, link_ids: list[int]) -> int:
        target_ids = set(link_ids)
        deleted = 0
        if self.category_tree is not None:
            links = self.category_tree.get("links", [])
            remaining = [link for link in links if link["id"] not in target_ids]
            deleted += len(links) - len(remaining)
            self.category_tree["links"] = remaining
        if self.section_tree is not None:
            for item in self.section_tree.get("categories", []):
                links = item.get("links", [])
                remaining = [link for link in links if link["id"] not in target_ids]
                deleted += len(links) - len(remaining)
                item["links"] = remaining
        return deleted

    def import_category_tree(self, tree: dict) -> None:
        self.category_tree = _merge_category_tree(self.category_tree, tree)

    def import_section_tree(self, tree: dict) -> None:
        self.section_tree = _merge_section_tree(self.section_tree, tree)


class _FakeStructureService:
    def __init__(self, db: _FakeDatabase) -> None:
        self.db = db

    def export_category_tree(self, _item_id: int) -> dict:
        return deepcopy(
            self.db.category_tree
            or {"category": {}, "links": []}
        )

    def export_section_tree(self, _item_id: int) -> dict:
        return deepcopy(
            self.db.section_tree
            or {"section": {}, "categories": []}
        )

    def delete_category(self, item_id: int) -> Result:
        self.db.category_tree = None
        return Result.success({"id": item_id})

    def delete_section(self, item_id: int) -> Result:
        self.db.section_tree = None
        return Result.success({"id": item_id})

    def delete_categories_bulk(self, category_ids: list[int]) -> Result:
        if self.db.section_tree is not None:
            excluded = set(category_ids)
            self.db.section_tree["categories"] = [
                item
                for item in self.db.section_tree.get("categories", [])
                if item["category"]["id"] not in excluded
            ]
        return Result.success(len(category_ids))

    def get_sections(self, sphere_id: int) -> list[dict]:
        tree = self.db.section_tree
        if tree and tree["section"].get("sphere_id") == sphere_id:
            return [deepcopy(tree["section"])]
        return []


def _merge_links(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {link["id"]: deepcopy(link) for link in existing}
    merged.update({link["id"]: deepcopy(link) for link in incoming})
    return list(merged.values())


def _merge_category_tree(current: dict | None, incoming: dict) -> dict:
    if current is None:
        return deepcopy(incoming)
    return {
        "category": deepcopy(incoming["category"]),
        "links": _merge_links(current.get("links", []), incoming.get("links", [])),
    }


def _merge_section_tree(current: dict | None, incoming: dict) -> dict:
    if current is None:
        return deepcopy(incoming)
    categories = {
        item["category"]["id"]: deepcopy(item)
        for item in current.get("categories", [])
    }
    for item in incoming.get("categories", []):
        category_id = item["category"]["id"]
        if category_id in categories:
            categories[category_id] = {
                "category": deepcopy(item["category"]),
                "links": _merge_links(
                    categories[category_id].get("links", []),
                    item.get("links", []),
                ),
            }
        else:
            categories[category_id] = deepcopy(item)
    return {
        "section": deepcopy(incoming["section"]),
        "categories": list(categories.values()),
    }


def _command(
    package_type: str,
    item_id: int,
    before_tree: dict | None,
    after_tree: dict,
    db: _FakeDatabase,
) -> ImportStructurePackageCmd:
    parent_key = "section_id" if package_type == "category" else "sphere_id"
    target_id = after_tree[package_type][parent_key]
    return ImportStructurePackageCmd(
        package_type=package_type,
        item_id=item_id,
        target_id=target_id,
        before_tree=before_tree,
        after_tree=after_tree,
        structure_service=_FakeStructureService(db),
        main_window=SimpleNamespace(
            _refresh_structure_after_import=lambda **_kwargs: None
        ),
        text=f"Import {package_type}",
    )


@pytest.mark.parametrize("package_type", ["category", "section"])
def test_undo_redo_restores_merged_package_data(package_type: str) -> None:
    if package_type == "category":
        before = {
            "category": {"id": 10, "name": "Work", "section_id": 2},
            "links": [{"id": 100, "category_id": 10, "name": "Old"}],
        }
        after = {
            "category": {"id": 10, "name": "Work", "section_id": 2},
            "links": [
                {"id": 100, "category_id": 10, "name": "Updated"},
                {"id": 101, "category_id": 10, "name": "New"},
            ],
        }
    else:
        before = {
            "section": {"id": 20, "name": "Projects", "sphere_id": 1},
            "categories": [
                {
                    "category": {"id": 30, "name": "Existing", "section_id": 20},
                    "links": [{"id": 300, "category_id": 30, "name": "Old"}],
                }
            ],
        }
        after = {
            "section": {"id": 20, "name": "Projects", "sphere_id": 1},
            "categories": [
                {
                    "category": {"id": 30, "name": "Existing", "section_id": 20},
                    "links": [
                        {"id": 300, "category_id": 30, "name": "Updated"},
                        {"id": 301, "category_id": 30, "name": "New"},
                    ],
                },
                {
                    "category": {"id": 31, "name": "Imported", "section_id": 20},
                    "links": [{"id": 302, "category_id": 31, "name": "Another"}],
                },
            ],
        }

    db = _FakeDatabase()
    if package_type == "category":
        db.category_tree = deepcopy(after)
        item_id = 10
    else:
        db.section_tree = deepcopy(after)
        item_id = 20
    command = _command(package_type, item_id, before, after, db)
    undo_stack = QUndoStack()
    undo_stack.push(command)

    undo_stack.undo()

    actual_before = db.category_tree if package_type == "category" else db.section_tree
    assert actual_before == before

    undo_stack.redo()

    actual_after = db.category_tree if package_type == "category" else db.section_tree
    assert actual_after == after


@pytest.mark.parametrize("package_type", ["category", "section"])
def test_undo_redo_removes_and_restores_imported_copy(package_type: str) -> None:
    if package_type == "category":
        after = {
            "category": {"id": 10, "name": "Work copy", "section_id": 2},
            "links": [{"id": 100, "category_id": 10, "name": "Imported"}],
        }
        item_id = 10
    else:
        after = {
            "section": {"id": 20, "name": "Projects copy", "sphere_id": 1},
            "categories": [
                {
                    "category": {"id": 30, "name": "Imported", "section_id": 20},
                    "links": [{"id": 300, "category_id": 30, "name": "Imported"}],
                }
            ],
        }
        item_id = 20

    db = _FakeDatabase()
    if package_type == "category":
        db.category_tree = deepcopy(after)
    else:
        db.section_tree = deepcopy(after)
    command = _command(package_type, item_id, None, after, db)
    undo_stack = QUndoStack()
    undo_stack.push(command)

    undo_stack.undo()

    actual_after_undo = db.category_tree if package_type == "category" else db.section_tree
    assert actual_after_undo is None

    undo_stack.redo()

    actual_after_redo = db.category_tree if package_type == "category" else db.section_tree
    assert actual_after_redo == after


def test_context_menu_section_import_pushes_undo_command() -> None:
    db = _FakeDatabase()
    structure_service = _FakeStructureService(db)
    imported_tree = {
        "section": {"id": 20, "name": "Imported", "sphere_id": 1},
        "categories": [],
    }

    class _ArchiveService:
        @staticmethod
        def inspect_package(_path: Path) -> dict:
            return {"item_name": "Imported"}

    class _MainWindowStub:
        def __init__(self) -> None:
            self.undo_stack = QUndoStack()
            self.structure_business = SimpleNamespace(
                structure_service=structure_service
            )
            self.refreshed = False

        def get_undo_stack(self):
            return self.undo_stack

        def _get_structure_share_service(self, _title):
            return self.structure_business, _ArchiveService()

        @staticmethod
        def _choose_archive_open_path(**_kwargs):
            return Path("section.aitesec")

        def _import_archive(self, **_kwargs) -> bool:
            db.section_tree = deepcopy(imported_tree)
            return True

        def _import_structure_archive_with_undo(self, **kwargs) -> bool:
            return MainWindow._import_structure_archive_with_undo(self, **kwargs)

        def _refresh_structure_after_import(self, **_kwargs) -> None:
            self.refreshed = True

    main_window = _MainWindowStub()
    with patch("app.views.windows.main_window.set_status_message"):
        MainWindow._import_structure_package(main_window, "section", 1)

    assert main_window.refreshed
    assert main_window.undo_stack.count() == 1
    main_window.undo_stack.undo()
    assert db.section_tree is None


def test_opened_section_import_pushes_undo_command() -> None:
    db = _FakeDatabase()
    structure_service = _FakeStructureService(db)
    imported_tree = {
        "section": {"id": 20, "name": "Imported", "sphere_id": 1},
        "categories": [],
    }

    class _ArchiveService:
        @staticmethod
        def inspect_package(_path: Path) -> dict:
            return {"package_type": "section", "item_name": "Imported"}

    class _MainWindowStub:
        def __init__(self) -> None:
            self.undo_stack = QUndoStack()
            self.structure_business = SimpleNamespace(
                structure_service=structure_service
            )

        def get_undo_stack(self):
            return self.undo_stack

        def _import_archive(self, **_kwargs) -> bool:
            db.section_tree = deepcopy(imported_tree)
            return True

        def _import_structure_archive_with_undo(self, **kwargs) -> bool:
            return MainWindow._import_structure_archive_with_undo(self, **kwargs)

        def _refresh_structure_after_import(self, **_kwargs) -> None:
            pass

    main_window = _MainWindowStub()
    with (
        patch(
            "app.services.structure_share_service.StructureShareService",
            return_value=_ArchiveService(),
        ),
        patch("app.views.windows.main_window.set_status_message"),
    ):
        imported = MainWindow.import_archive_file(
            main_window, Path("section.aitesec"), target_type="sphere", target_id=1
        )

    assert imported
    assert main_window.undo_stack.count() == 1
    main_window.undo_stack.undo()
    assert db.section_tree is None
