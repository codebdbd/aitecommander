from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.services.structure_share_service import (
    StructureShareService,
    SCHEMA_VERSION,
    MAX_ARCHIVE_ENTRIES,
    MAX_DATA_JSON_SIZE,
    MAX_ICON_FILE_SIZE,
    MAX_TOTAL_UNCOMPRESSED_SIZE,
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
