from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from app.services.structure_share_service import (
    ALLOWED_WORKSPACE_EXTENSIONS,
    MAX_WORKSPACE_FILE_SIZE,
    StructureShareService,
    get_user_workspace_files_dir,
)


def test_collect_workspace_files(tmp_path: Path) -> None:
    service = StructureShareService(MagicMock())
    test_script = tmp_path / "deploy.py"
    test_script.write_text("print('hello')", encoding="utf-8")

    data = {
        "category": {"id": 1, "name": "Work"},
        "links": [
            {"id": 10, "name": "Deploy Script", "url": str(test_script), "type": "file"},
            {"id": 11, "name": "Web", "url": "https://google.com", "type": "web"},
        ],
    }

    files = service._collect_workspace_files(data)
    assert len(files) == 1
    rel_path = next(iter(files.keys()))
    assert rel_path.startswith("files/workspace/")
    assert rel_path.endswith("deploy.py")
    assert data["links"][0].get("workspace_file") is not None


def test_export_import_category_with_workspace_files(tmp_path: Path) -> None:
    mock_ss = MagicMock()
    service = StructureShareService(mock_ss)

    script_file = tmp_path / "test_task.bat"
    script_file.write_text("@echo off\necho 123", encoding="utf-8")

    cat_tree = {
        "category": {"id": 5, "name": "Scripts", "icon_path": ""},
        "links": [
            {"id": 50, "name": "Test Task", "url": str(script_file), "type": "file"},
        ],
    }
    mock_ss.export_category_tree.return_value = cat_tree

    archive_path = tmp_path / "scripts_cat.zip"
    service.export_category_archive(5, archive_path)
    assert archive_path.is_file()

    # Inspect the zip contents
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "data.json" in names
        assert any(n.startswith("files/workspace/") for n in names)

    # Now import into another section
    service.import_category_archive(archive_path, target_section_id=100)
    assert mock_ss.import_category_tree.called
    imported_tree = mock_ss.import_category_tree.call_args[0][0]

    assert imported_tree["category"]["section_id"] == 100
    assert len(imported_tree["links"]) == 1
    imported_link = imported_tree["links"][0]
    # The imported link should have an updated local path pointing to the extracted workspace file
    new_url = Path(imported_link["url"])
    assert new_url.name == "test_task.bat"
    assert new_url.is_file()
    assert new_url.read_text(encoding="utf-8") == "@echo off\necho 123"


def test_export_import_single_link(tmp_path: Path) -> None:
    mock_ss = MagicMock()
    service = StructureShareService(mock_ss)

    archive_path = tmp_path / "cat.zip"
    service.export_category_archive(42, archive_path)
    assert archive_path.is_file()

    service.import_category_archive(archive_path, target_section_id=77)
    assert mock_ss.import_category_tree.called


def test_inspect_package(tmp_path: Path) -> None:
    mock_ss = MagicMock()
    mock_ss.export_category_tree.return_value = {"id": 42, "name": "Docs", "links": []}
    service = StructureShareService(mock_ss)
    archive_path = tmp_path / "cat.zip"
    service.export_category_archive(42, archive_path)
    manifest = service.inspect_package(archive_path)
    assert manifest.get("package_type") == "category"
