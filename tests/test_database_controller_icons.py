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


def test_import_icons_archive_rejects_oversized_file(tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    archive = tmp_path / "huge.zip"
    controller = DatabaseController(Mock())

    with zipfile.ZipFile(archive, "w") as zipf:
        zipf.writestr("huge.png", b"fake")

    mock_info = zipfile.ZipInfo("huge.png")
    mock_info.file_size = 11 * 1024 * 1024

    with patch(
        "app.controllers.ui.dialogs.database_controller.icon_path_service.get_supported_icon_formats",
        return_value=[".png", ".ico"],
    ), patch("zipfile.ZipFile.infolist", return_value=[mock_info]):
        try:
            controller._import_icons_archive(str(archive), str(icons_dir))
        except ValueError as e:
            assert "huge.png" in str(e)



def test_import_icons_archive_does_not_destroy_existing_icon_on_corrupt_read(tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    original_icon = icons_dir / "good.png"
    original_icon.write_bytes(b"ORIGINAL_VALID_CONTENT")

    archive = tmp_path / "corrupt.zip"
    controller = DatabaseController(Mock())

    # Write a good member, then we'll simulate an error during extraction
    with zipfile.ZipFile(archive, "w") as zipf:
        zipf.writestr("good.png", b"NEW_DATA")

    with patch(
        "app.controllers.ui.dialogs.database_controller.icon_path_service.get_supported_icon_formats",
        return_value=[".png", ".ico"],
    ), patch("shutil.copyfileobj", side_effect=OSError("Disk write failed")):
        try:
            controller._import_icons_archive(str(archive), str(icons_dir))
            assert False, "Expected OSError"
        except OSError:
            pass

    # The original icon MUST be completely intact!
    assert original_icon.read_bytes() == b"ORIGINAL_VALID_CONTENT"
