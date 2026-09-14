from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.structure_share_service import (
    MAX_ARCHIVE_ENTRIES,
    MAX_DATA_JSON_SIZE,
    SCHEMA_VERSION,
    StructureShareService,
    _sha256_bytes,
)


def _create_minimal_archive(
    zip_path: Path,
    *,
    data_dict: dict | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> None:
    data_bytes = json.dumps(data_dict or {"category": {"name": "Cat"}}).encode("utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_type": "category",
        "package_id": "pkg1",
        "checksums": {
            "data.json": _sha256_bytes(data_bytes),
            "files": {},
        },
    }
    if extra_files:
        for name, content in extra_files.items():
            manifest["checksums"]["files"][name] = _sha256_bytes(content)

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("data.json", data_bytes)
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)


def test_read_archive_success(tmp_path: Path) -> None:
    zip_path = tmp_path / "valid.zip"
    icon_content = b"fake_icon_png_data"
    _create_minimal_archive(
        zip_path,
        data_dict={"category": {"name": "Valid Cat"}},
        extra_files={"files/icons/test.png": icon_content},
    )

    service = StructureShareService(MagicMock())
    manifest, data, icons = service._read_archive(zip_path)

    assert manifest["package_type"] == "category"
    assert data["category"]["name"] == "Valid Cat"
    assert "test.png" in icons
    assert icons["test.png"] == icon_content


def test_read_archive_rejects_excessive_entries(tmp_path: Path) -> None:
    zip_path = tmp_path / "too_many_entries.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", b"{}")
        zf.writestr("data.json", b"{}")
        for i in range(MAX_ARCHIVE_ENTRIES + 1):
            zf.writestr(f"files/icons/icon_{i}.png", b"x")

    service = StructureShareService(MagicMock())
    with pytest.raises(ValueError, match="too many entries"):
        service._read_archive(zip_path)


def test_read_archive_rejects_oversized_declared_data(tmp_path: Path) -> None:
    zip_path = tmp_path / "declared_oversized.zip"
    _create_minimal_archive(zip_path)

    service = StructureShareService(MagicMock())
    fake_info = zipfile.ZipInfo("data.json")
    fake_info.file_size = MAX_DATA_JSON_SIZE + 1000

    with patch.object(zipfile.ZipFile, "infolist", return_value=[fake_info]):
        with pytest.raises(ValueError, match="declared size"):
            service._read_archive(zip_path)


def test_read_archive_rejects_oversized_streamed_entry(tmp_path: Path) -> None:
    zip_path = tmp_path / "stream_oversized.zip"
    _create_minimal_archive(zip_path)

    service = StructureShareService(MagicMock())
    # Test safe_read_entry limit enforcement during streaming
    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(ValueError, match="exceeds maximum allowed size"):
            service._safe_read_entry(zf, "data.json", max_size=2)


def test_read_archive_rejects_cumulative_uncompressed_limit(tmp_path: Path) -> None:
    zip_path = tmp_path / "cumulative_oversized.zip"
    _create_minimal_archive(zip_path)

    service = StructureShareService(MagicMock())
    # 6 icons of 9 MB each: each is under 10 MB, but total is 54 MB (> 50 MB limit)
    fake_infos = [
        zipfile.ZipInfo("manifest.json"),
        zipfile.ZipInfo("data.json"),
    ]
    fake_infos[0].file_size = 100
    fake_infos[1].file_size = 100

    for i in range(6):
        info = zipfile.ZipInfo(f"files/icons/icon_{i}.png")
        info.file_size = 9 * 1024 * 1024
        fake_infos.append(info)

    with patch.object(zipfile.ZipFile, "infolist", return_value=fake_infos):
        with pytest.raises(ValueError, match="total declared uncompressed size"):
            service._read_archive(zip_path)


def test_read_archive_skips_unsafe_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "traversal.zip"
    _create_minimal_archive(
        zip_path,
        extra_files={
            "files/icons/../../evil.exe": b"dangerous",
            "files/icons/safe.png": b"safe",
        },
    )

    service = StructureShareService(MagicMock())
    manifest, data, icons = service._read_archive(zip_path)

    # Path traversal entry must NOT be loaded into icons dict
    assert "evil.exe" not in icons
    assert "safe.png" in icons


_VALID_1X1_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_export_never_includes_external_files_or_traversal(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()
    valid_icon = icons_dir / "valid.png"
    valid_icon.write_bytes(_VALID_1X1_PNG)

    # External private file
    external_doc = tmp_path / "private_document.txt"
    external_doc.write_text("SUPER SECRET DATA")

    service = StructureShareService(MagicMock())
    candidates = [
        str(external_doc),
        "../../private_document.txt",
        "C:\\Windows\\system32\\calc.exe",
        "valid.png",
        "nonexistent.png",
        "bad_extension.exe",
    ]

    files = service._resolve_icon_candidates(candidates, icons_dir)

    # Only the legitimate icon within icons_dir must be included
    assert len(files) == 1
    assert "files/icons/valid.png" in files
    assert files["files/icons/valid.png"] == valid_icon.resolve()


def test_write_archive_excludes_external_icons(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()
    valid_icon = icons_dir / "valid.png"
    valid_icon.write_bytes(_VALID_1X1_PNG)

    private_doc = tmp_path / "passwords.txt"
    private_doc.write_text("my password")

    service = StructureShareService(MagicMock())
    archive_path = tmp_path / "exported.zip"

    data = {
        "category": {"name": "Test Cat", "icon_path": str(private_doc)},
        "links": [
            {"name": "L1", "url": "https://example.com", "icon_path": "valid.png"},
            {"name": "L2", "url": "https://example2.com", "icon_path": "../../passwords.txt"},
        ],
    }

    with patch("app.utils.ui.icon.path_service.icon_path_service.get_user_icons_dir", return_value=icons_dir):
        service._write_archive("category", data, archive_path)

    with zipfile.ZipFile(archive_path, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "data.json" in namelist
        assert "files/icons/valid.png" in namelist
        assert "files/icons/passwords.txt" not in namelist
        assert not any("passwords" in name for name in namelist)


def test_install_icons_rejects_malformed_and_non_image_payloads(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()

    service = StructureShareService(MagicMock())
    icons = {
        "valid.png": _VALID_1X1_PNG,
        "script.exe": b"MZ\x90\x00\x03\x00\x00\x00",
        "fake.png": b"NOT AN IMAGE DATA",
        "../../traversal.png": _VALID_1X1_PNG,
    }

    with patch("app.utils.ui.icon.path_service.icon_path_service.ensure_user_icons_dir", return_value=icons_dir):
        installed = service._install_icons(icons)

    assert installed == {"valid.png"}
    assert (icons_dir / "valid.png").is_file()
    assert not (icons_dir / "script.exe").exists()
    assert not (icons_dir / "fake.png").exists()
    assert not (tmp_path / "traversal.png").exists()


def test_import_sanitizes_external_icon_path(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()
    installed_icon = icons_dir / "installed.png"
    installed_icon.write_bytes(_VALID_1X1_PNG)

    service = StructureShareService(MagicMock())

    data = {
        "category": {
            "name": "Malicious Cat",
            "icon_path": "C:\\Windows\\system32\\calc.exe",
        },
        "links": [
            {
                "name": "Link 1",
                "url": "https://example.com",
                "icon_path": "/etc/shadow",
            },
            {
                "name": "Link 2",
                "url": "https://example.com",
                "icon_path": "installed.png",
            },
        ],
    }

    with patch("app.utils.ui.icon.path_service.icon_path_service.get_user_icons_dir", return_value=icons_dir):
        prepared = service._prepare_category_tree_for_import(data, section_id=10, valid_icons={"installed.png"})

    # External path on category should be stripped to empty default
    assert prepared["category"]["icon_path"] == ""

    # External path on link should be sanitized to default.ico
    assert prepared["links"][0]["icon_path"] == "default.ico"

    # Valid installed icon should be preserved
    assert prepared["links"][1]["icon_path"] == "installed.png"

