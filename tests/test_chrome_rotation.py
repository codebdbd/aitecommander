"""Tests for Chrome profile rotation feature."""

import importlib
import json
import logging
import sqlite3
from unittest.mock import Mock

from app.controllers.ui.dialogs.link_dialog_controller import LinkDialogController
from app.controllers.ui.links.link_operations import LinksUILinkOperations
from app.models.entities.link_model import LinkModel
from app.utils.links.link_utils import LinkInfo


def test_migration_0008():
    """Verify that migration 0008 adds chrome_rotation, rotation_index, rotation_profiles."""
    mod = importlib.import_module("app.models.migrations.0008_add_chrome_rotation")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'web'
        )
        """
    )

    logger = logging.getLogger("test_migration_0008")
    mod.migrate(conn, logger)

    cols = {r["name"] for r in conn.execute("PRAGMA table_info('link')").fetchall()}
    assert "chrome_rotation" in cols
    assert "rotation_index" in cols
    assert "rotation_profiles" in cols

    # Idempotence: running again should not fail
    mod.migrate(conn, logger)


def test_link_model_rotation_support():
    """Verify that LinkModel handles rotation fields in upsert, get, and update_rotation_index."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create schema including all columns
    conn.executescript(
        """
        CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER, name TEXT);
        CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER, name TEXT);
        INSERT INTO category (id, section_id, name) VALUES (1, 1, 'Cat 1');

        CREATE TABLE link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'web',
            notes TEXT DEFAULT '',
            is_favorite INTEGER DEFAULT 0,
            last_used TEXT DEFAULT NULL,
            icon_path TEXT DEFAULT '',
            args TEXT DEFAULT '',
            browser_key TEXT DEFAULT NULL,
            position INTEGER DEFAULT 0,
            chrome_rotation INTEGER NOT NULL DEFAULT 0,
            rotation_index INTEGER NOT NULL DEFAULT 0,
            rotation_profiles TEXT DEFAULT NULL,
            is_group_launch INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    # Mock connection manager
    cm = Mock()
    cm.connection = conn
    cm.get_connection.return_value = conn
    cm.transaction.return_value = conn

    model = LinkModel(cm)

    profiles_data = [
        {"directory": "Profile 1", "name": "Work", "browser_key": "chrome"},
        {"directory": "Profile 2", "name": "Personal", "browser_key": "chrome"},
    ]
    profiles_json = json.dumps(profiles_data)

    # Insert link with rotation
    link_id = model.upsert_link(
        {
            "category_id": 1,
            "name": "Rotating Link",
            "url": "https://example.com",
            "type": "web",
            "chrome_rotation": 1,
            "rotation_index": 0,
            "rotation_profiles": profiles_json,
        }
    )
    assert link_id > 0

    # Retrieve by ID
    link = model.get_link_by_id(link_id)
    assert link is not None
    assert link["chrome_rotation"] == 1
    assert link["rotation_index"] == 0
    assert link["rotation_profiles"] == profiles_json

    # Retrieve via get_links
    links = model.get_links(1)
    assert len(links) == 1
    assert links[0]["chrome_rotation"] == 1
    assert links[0]["rotation_profiles"] == profiles_json

    # Update rotation index
    model.update_rotation_index(link_id, 1)
    updated = model.get_link_by_id(link_id)
    assert updated["rotation_index"] == 1


def test_link_dialog_controller_rotation_saves_single_record():
    """Verify that enabling chrome_rotation saves 1 link record with rotation_profiles JSON."""
    controller = LinkDialogController(database=Mock())

    profiles = [
        {"directory": "Profile 1", "name": "User 1", "browser_key": "chrome"},
        {"directory": "Profile 2", "name": "User 2", "browser_key": "chrome"},
    ]

    form_data = {
        "name": "Multi Profile Test",
        "url": "https://test.com",
        "link_type": "web",
        "category_id": 5,
        "chrome_rotation": True,
        "rotation_profiles": profiles,
        "selected_profiles": profiles,  # Even if selected_profiles has profiles
    }

    links_data = controller._prepare_links_data(form_data)
    # Should only create 1 link record, NOT 2 separate links
    assert len(links_data) == 1
    rec = links_data[0]
    assert rec["chrome_rotation"] == 1
    assert rec["rotation_index"] == 0
    parsed = json.loads(rec["rotation_profiles"])
    assert len(parsed) == 2
    assert parsed[0]["directory"] == "Profile 1"
    assert parsed[1]["directory"] == "Profile 2"


def test_prepare_rotated_link_cycling():
    """Verify that _prepare_rotated_link advances index and sets Chrome profile args."""
    business_mock = Mock()
    ctrl = Mock()
    ctrl.table = Mock()
    ctrl.business = business_mock
    ctrl.main = Mock()
    link_ops = LinksUILinkOperations(controller=ctrl, link_operations=Mock())

    profiles = [
        {"directory": "Default", "browser_key": "chrome"},
        {"directory": "Profile 1", "browser_key": "chrome"},
        {"directory": "Profile 2", "browser_key": "chrome"},
    ]

    link = {
        "id": 42,
        "name": "Rotating",
        "url": "https://example.com",
        "type": "web",
        "chrome_rotation": 1,
        "rotation_index": 0,
        "rotation_profiles": json.dumps(profiles),
    }

    # Click 1: should use Default (index 0), advance to 1
    rot1 = link_ops._prepare_rotated_link(link)
    assert rot1["args"] == '--profile-directory="Default"'
    assert rot1["browser_key"] == "chrome"
    assert link["rotation_index"] == 1
    business_mock.update_rotation_index.assert_called_with(42, 1)

    # Click 2: should use Profile 1 (index 1), advance to 2
    rot2 = link_ops._prepare_rotated_link(link)
    assert rot2["args"] == '--profile-directory="Profile 1"'
    assert link["rotation_index"] == 2
    business_mock.update_rotation_index.assert_called_with(42, 2)

    # Click 3: should use Profile 2 (index 2), advance to 0 (wrap around)
    rot3 = link_ops._prepare_rotated_link(link)
    assert rot3["args"] == '--profile-directory="Profile 2"'
    assert link["rotation_index"] == 0
    business_mock.update_rotation_index.assert_called_with(42, 0)

    # Click 4: should use Default again (index 0), advance to 1
    rot4 = link_ops._prepare_rotated_link(link)
    assert rot4["args"] == '--profile-directory="Default"'
    assert link["rotation_index"] == 1
    business_mock.update_rotation_index.assert_called_with(42, 1)



def test_link_info_rotation_fields():
    """Verify that LinkInfo.from_dict parses chrome rotation attributes."""
    data = {
        "id": 10,
        "url": "https://example.org",
        "type": "web",
        "chrome_rotation": 1,
        "rotation_index": 3,
        "rotation_profiles": '[{"directory": "Profile 1"}]',
    }
    info = LinkInfo.from_dict(data)
    assert info.chrome_rotation is True
    assert info.rotation_index == 3
    assert info.rotation_profiles == '[{"directory": "Profile 1"}]'


def test_prepare_rotated_link_empty_or_corrupted_profiles():
    """Verify that _prepare_rotated_link handles missing/corrupted profiles gracefully."""
    business_mock = Mock()
    ctrl = Mock()
    ctrl.table = Mock()
    ctrl.business = business_mock
    ctrl.main = Mock()
    link_ops = LinksUILinkOperations(controller=ctrl, link_operations=Mock())

    # Case 1: invalid JSON
    link1 = {
        "id": 1,
        "url": "https://example.com",
        "chrome_rotation": 1,
        "rotation_profiles": "invalid-json",
    }
    result1 = link_ops._prepare_rotated_link(link1)
    assert result1 == link1
    business_mock.update_rotation_index.assert_not_called()

    # Case 2: empty list
    link2 = {
        "id": 2,
        "url": "https://example.com",
        "chrome_rotation": 1,
        "rotation_profiles": "[]",
    }
    result2 = link_ops._prepare_rotated_link(link2)
    assert result2 == link2
    business_mock.update_rotation_index.assert_not_called()





