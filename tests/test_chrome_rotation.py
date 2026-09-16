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


def test_rotation_mixin_toggled():
    """Verify that RotationMixin toggling disables/enables Profile button and manages visibility."""
    from app.views.windows.dialogs.link_dialog.handlers_mixins.rotation_mixin import (
        RotationMixin,
    )

    class DummyHandler(RotationMixin):
        def __init__(self, dialog):
            self.dialog = dialog

    dialog = Mock()
    profile_btn = Mock()
    rotation_btn = Mock()
    dialog._get_profile_btn.return_value = profile_btn
    dialog._get_rotation_profiles_btn.return_value = rotation_btn
    dialog.selected_profiles = [{"directory": "Profile 1"}]
    dialog.rotation_profiles = []
    dialog.tr = lambda s: s

    handler = DummyHandler(dialog)

    # Toggle ON
    handler._on_rotation_toggled(True)
    profile_btn.setEnabled.assert_called_with(False)
    rotation_btn.setEnabled.assert_called_with(True)
    assert dialog.selected_profiles == []

    # Toggle OFF
    handler._on_rotation_toggled(False)
    profile_btn.setEnabled.assert_called_with(True)
    rotation_btn.setEnabled.assert_called_with(False)
    assert dialog.rotation_profiles == []


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


def test_load_rotation_state_in_dialog():
    """Verify that _load_rotation_state restores saved state on LinkDialog."""
    from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog

    profiles = [{"directory": "Profile 1", "name": "Work"}]
    link = {
        "id": 5,
        "chrome_rotation": 1,
        "rotation_profiles": json.dumps(profiles),
    }

    dialog = Mock(spec=LinkDialog)
    dialog.link = link
    dialog.rotation_profiles = []
    dialog.selected_profiles = []
    dialog.tr = lambda s: s

    rotation_chk = Mock()
    rotation_btn = Mock()
    profile_btn = Mock()
    dialog._get_rotation_chk.return_value = rotation_chk
    dialog._get_rotation_profiles_btn.return_value = rotation_btn
    dialog._get_profile_btn.return_value = profile_btn

    LinkDialog._load_rotation_state(dialog)

    assert dialog.rotation_profiles == profiles
    rotation_chk.setChecked.assert_called_with(True)
    profile_btn.setEnabled.assert_called_with(False)
    rotation_btn.setEnabled.assert_called_with(True)


def test_type_change_mixin_hides_rotation_when_not_web():
    """Verify that TypeChangeMixin hides rotation controls for non-WEB link types."""
    from app.views.windows.dialogs.link_dialog.handlers_mixins.type_change_mixin import (
        TypeChangeMixin,
    )

    class DummyTypeHandler(TypeChangeMixin):
        def __init__(self, dialog):
            self.dialog = dialog

    dialog = Mock()
    dialog.link_type = "file"
    dialog.selected_profiles = []
    dialog.ui = Mock()
    dialog.ui.widgets = {}

    rotation_chk = Mock()
    rotation_btn = Mock()
    dialog._get_rotation_chk.return_value = rotation_chk
    dialog._get_rotation_profiles_btn.return_value = rotation_btn
    dialog._get_args_le.return_value = Mock()
    dialog._get_args_lbl.return_value = Mock()
    dialog._get_browse_btn.return_value = Mock()
    dialog._get_url_le.return_value = Mock()

    handler = DummyTypeHandler(dialog)
    handler._update_ui_state()

    rotation_chk.setVisible.assert_called_with(False)
    rotation_chk.setChecked.assert_called_with(False)


def test_button_counters_and_tooltips(monkeypatch):
    """Verify that both top profile button and rotation button use count badges and detailed tooltips."""
    import app.views.windows.dialogs.link_dialog.handlers_mixins.rotation_mixin as rot_mod
    from app.views.windows.dialogs.link_dialog.handlers_mixins.rotation_mixin import (
        RotationMixin,
    )
    from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog

    monkeypatch.setattr(rot_mod, "_tr", lambda text, *a, **kw: text)

    dialog = Mock(spec=LinkDialog)
    dialog.tr = lambda s: s

    # 1. Top profile button formatting
    assert LinkDialog._format_profile_text(dialog, []) == "Profile"
    assert LinkDialog._format_profile_text(dialog, [{"name": "Work"}]) == "Profile (1)"
    assert LinkDialog._format_profile_text(dialog, [{"name": "P1"}, {"name": "P2"}, {"name": "P3"}]) == "Profiles (3)"

    tip_empty = LinkDialog._format_profile_tooltip(dialog, [])
    assert tip_empty == "Select browser profile"

    tip_single = LinkDialog._format_profile_tooltip(dialog, [{"name": "Work"}])
    assert "Work" in tip_single
    assert "Click to change" in tip_single

    tip_multi = LinkDialog._format_profile_tooltip(dialog, [{"name": "Work"}, {"name": "Personal"}])
    assert "2" in tip_multi
    assert "• Work" in tip_multi
    assert "• Personal" in tip_multi

    # 2. Rotation button formatting
    assert RotationMixin._format_rotation_text([]) == "Select profiles..."
    assert RotationMixin._format_rotation_text([{"name": "P1"}]) == "Profiles (1)"
    assert RotationMixin._format_rotation_text([{"name": "P1"}, {"name": "P2"}, {"name": "P3"}]) == "Profiles (3)"

    rot_tip_empty = RotationMixin._format_rotation_tooltip([])
    assert "Select profiles for rotation" in rot_tip_empty

    rot_tip = RotationMixin._format_rotation_tooltip([
        {"name": "FirstProfile"},
        {"name": "SecondProfile"},
    ])
    assert "Rotation order (2):" in rot_tip
    assert "1. FirstProfile" in rot_tip
    assert "2. SecondProfile" in rot_tip
    assert "Click to change" in rot_tip


