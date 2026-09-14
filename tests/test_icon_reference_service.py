from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from app.services.icon_reference_service import IconReferenceService


def _init_test_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sphere (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            icon_path TEXT
        );
        CREATE TABLE section (
            id INTEGER PRIMARY KEY,
            sphere_id INTEGER,
            name TEXT NOT NULL,
            icon_path TEXT
        );
        CREATE TABLE category (
            id INTEGER PRIMARY KEY,
            section_id INTEGER,
            name TEXT NOT NULL,
            icon_path TEXT
        );
        CREATE TABLE link (
            id INTEGER PRIMARY KEY,
            category_id INTEGER,
            name TEXT NOT NULL,
            icon_path TEXT
        );
        """
    )
    conn.commit()


def test_cleanup_icon_if_orphaned_never_deletes_external_file(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()

    external_dir = tmp_path / "documents"
    external_dir.mkdir()
    sensitive_file = external_dir / "important_contract.pdf"
    sensitive_file.write_text("critical user document", encoding="utf-8")

    db_mock = MagicMock()
    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock.connection = conn

    service = IconReferenceService(db_mock)
    service._get_user_icons_dir = MagicMock(return_value=icons_dir)

    # Attempt cleanup with absolute path to external sensitive file
    res = service.cleanup_icon_if_orphaned(str(sensitive_file))

    assert res is False
    assert sensitive_file.exists(), "External file was deleted by icon cleanup!"
    assert sensitive_file.read_text(encoding="utf-8") == "critical user document"


def test_cleanup_icon_if_orphaned_rejects_path_traversal(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()

    parent_file = tmp_path / "parent_secret.txt"
    parent_file.write_text("secret", encoding="utf-8")

    db_mock = MagicMock()
    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock.connection = conn

    service = IconReferenceService(db_mock)
    service._get_user_icons_dir = MagicMock(return_value=icons_dir)

    assert service.cleanup_icon_if_orphaned("../parent_secret.txt") is False
    assert parent_file.exists()


def test_is_icon_used_checks_all_four_tables() -> None:
    db_mock = MagicMock()
    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock.connection = conn

    # Insert icons across sphere, section, category, link
    conn.execute("INSERT INTO sphere (id, name, icon_path) VALUES (1, 'S1', 'sphere_icon.png')")
    conn.execute("INSERT INTO section (id, sphere_id, name, icon_path) VALUES (1, 1, 'Sec1', 'section_icon.png')")
    conn.execute("INSERT INTO category (id, section_id, name, icon_path) VALUES (1, 1, 'Cat1', 'cat_icon.png')")
    conn.execute("INSERT INTO link (id, category_id, name, icon_path) VALUES (1, 1, 'L1', 'link_icon.png')")
    conn.commit()

    service = IconReferenceService(db_mock)

    assert service.is_icon_used("sphere_icon.png") is True
    assert service.is_icon_used("section_icon.png") is True
    assert service.is_icon_used("cat_icon.png") is True
    assert service.is_icon_used("link_icon.png") is True
    assert service.is_icon_used("nonexistent_icon.png") is False


def test_is_icon_used_matches_names_with_underscores() -> None:
    db_mock = MagicMock()
    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock.connection = conn

    # Path with multiple underscores
    conn.execute("INSERT INTO link (id, category_id, name, icon_path) VALUES (1, 1, 'L1', 'my_custom_icon_1.png')")
    conn.commit()

    service = IconReferenceService(db_mock)

    # Should match exact and filename
    assert service.is_icon_used("my_custom_icon_1.png") is True
    assert service.is_icon_used("files/icons/my_custom_icon_1.png") is True

    # Should NOT falsely match if a character differs where _ would act as wildcard
    assert service.is_icon_used("myXcustomXiconX1.png") is False


def test_get_orphaned_icons_failsafe_on_db_error(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()
    icon1 = icons_dir / "icon1.png"
    icon1.write_bytes(b"data1")

    db_mock = MagicMock()
    # Mock connection execute to raise DatabaseError
    db_mock.connection.execute.side_effect = sqlite3.OperationalError("disk I/O error")

    service = IconReferenceService(db_mock)
    service._get_user_icons_dir = MagicMock(return_value=icons_dir)

    # If DB query fails, orphaned list MUST be empty to prevent mass deletion
    orphans = service.get_orphaned_icons()
    assert orphans == []
    assert icon1.exists()


def test_cleanup_icon_if_orphaned_success_inside_icons_dir(tmp_path: Path) -> None:
    icons_dir = tmp_path / "user_icons"
    icons_dir.mkdir()
    orphan_file = icons_dir / "orphan_test.png"
    orphan_file.write_bytes(b"orphan data")

    db_mock = MagicMock()
    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock.connection = conn

    service = IconReferenceService(db_mock)
    service._get_user_icons_dir = MagicMock(return_value=icons_dir)

    res = service.cleanup_icon_if_orphaned("orphan_test.png")

    assert res is True
    assert not orphan_file.exists(), "Orphaned icon inside icons_dir was not cleaned up!"
