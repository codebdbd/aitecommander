from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from app.controllers.ui.dialogs.database_controller import DatabaseController


def test_export_icons_archive_skips_temp_and_metadata_files(tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    (icons_dir / "site.png").write_bytes(b"png")
    (icons_dir / ".site.png.tmp").write_bytes(b"tmp")
    (icons_dir / "site.meta.json").write_text("{}", encoding="utf-8")
    archive = tmp_path / "icons.zip"
    controller = DatabaseController(Mock())

    with patch(
        "app.controllers.ui.dialogs.database_controller.icon_path_service.get_supported_icon_formats",
        return_value=[".png", ".ico"],
    ):
        controller._export_icons_archive(str(icons_dir), str(archive))

    with zipfile.ZipFile(archive, "r") as zipf:
        assert zipf.namelist() == ["site.png"]


def test_import_icons_archive_skips_unsupported_and_unsafe_names(tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    archive = tmp_path / "icons.zip"
    controller = DatabaseController(Mock())
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("site.png", b"png")
        zipf.writestr("../escape.png", b"bad")
        zipf.writestr("note.txt", b"txt")

    with patch(
        "app.controllers.ui.dialogs.database_controller.icon_path_service.get_supported_icon_formats",
        return_value=[".png", ".ico"],
    ):
        imported = controller._import_icons_archive(str(archive), str(icons_dir))

    assert imported == 1
    assert (icons_dir / "site.png").exists()
    assert not (tmp_path / "escape.png").exists()
