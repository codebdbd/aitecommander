from __future__ import annotations

import json
import shutil
import sqlite3
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from conftest import build_test_temp_path
from app.controllers.ui.dialogs.database_controller import DatabaseController
from app.services.database_restore_worker import DatabaseRestoreWorker
from app.utils.ui.icon.path_service import icon_path_service


class TestDatabaseBundleExportImport(unittest.TestCase):
    def setUp(self):
        self.temp_path = build_test_temp_path("manual_tmp", "database_bundle_test")
        shutil.rmtree(self.temp_path, ignore_errors=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_path, ignore_errors=True)

    def test_unified_backup_creates_zip_with_manifest_and_referenced_icons(self):
        source_db = self.temp_path / "source.db"
        dest_zip = self.temp_path / "backup.zip"
        icons_dir = self.temp_path / "icons"
        icons_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy user icon
        test_icon = icons_dir / "my_icon.png"
        test_icon.write_bytes(b"\x89PNG\r\n\x1a\nfake_image_content")

        # Create SQLite database with link table referencing the icon
        conn = sqlite3.connect(str(source_db))
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE sphere (id INTEGER, name TEXT, icon_path TEXT)")
        conn.execute("CREATE TABLE section (id INTEGER, sphere_id INTEGER, name TEXT, icon_path TEXT)")
        conn.execute("CREATE TABLE category (id INTEGER, section_id INTEGER, name TEXT, icon_path TEXT)")
        conn.execute("CREATE TABLE link (id INTEGER, category_id INTEGER, name TEXT, icon_path TEXT)")
        conn.execute("INSERT INTO link (id, name, icon_path) VALUES (1, 'Test', 'my_icon.png')")
        conn.commit()

        # Monkeypatch icon path service user dir
        orig_get_user_icons_dir = icon_path_service.get_user_icons_dir
        icon_path_service.get_user_icons_dir = lambda: icons_dir

        try:
            fake_db = SimpleNamespace(connection=conn, db_path=str(source_db))
            controller = DatabaseController(fake_db)

            # Perform backup to .zip
            controller._save_database_copy(str(source_db), str(dest_zip))

            self.assertTrue(dest_zip.exists())
            self.assertTrue(zipfile.is_zipfile(dest_zip))

            with zipfile.ZipFile(dest_zip, "r") as zf:
                names = zf.namelist()
                self.assertIn("database.db", names)
                self.assertIn("manifest.json", names)
                self.assertIn("icons/my_icon.png", names)

                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                self.assertEqual(manifest.get("format_version"), "1.0")
                self.assertEqual(manifest.get("db_filename"), "database.db")

                # Verify database content inside zip
                extracted_db = self.temp_path / "extracted_db.db"
                with zf.open("database.db", "r") as src, open(extracted_db, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                chk_conn = sqlite3.connect(str(extracted_db))
                row = chk_conn.execute("SELECT name, icon_path FROM link WHERE id=1").fetchone()
                chk_conn.close()
                self.assertEqual(row[0], "Test")
                self.assertEqual(row[1], "my_icon.png")

        finally:
            icon_path_service.get_user_icons_dir = orig_get_user_icons_dir
            conn.close()

    def test_restore_worker_extracts_bundle_and_publishes_icons(self):
        bundle_zip = self.temp_path / "test_bundle.zip"
        staging_root = self.temp_path / "staging"
        staging_root.mkdir(parents=True, exist_ok=True)

        target_icons_dir = self.temp_path / "target_icons"
        target_icons_dir.mkdir(parents=True, exist_ok=True)

        # Build a valid bundle
        source_db = self.temp_path / "inner_db.db"
        conn = sqlite3.connect(str(source_db))
        conn.execute("CREATE TABLE link (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO link VALUES (42, 'Answer')")
        conn.commit()
        conn.close()

        with zipfile.ZipFile(bundle_zip, "w") as zf:
            zf.write(str(source_db), "database.db")
            zf.writestr("icons/restored_icon.svg", "<svg>test</svg>")

        worker = DatabaseRestoreWorker(SimpleNamespace(), bundle_zip)

        orig_get_user_icons_dir = icon_path_service.get_user_icons_dir
        icon_path_service.get_user_icons_dir = lambda: target_icons_dir

        try:
            staged_db, staged_icons = worker._extract_bundle_staging(bundle_zip, staging_root)

            self.assertTrue(staged_db.exists())
            self.assertTrue((staged_icons / "restored_icon.svg").exists())

            worker._publish_staged_icons(staged_icons)
            self.assertTrue((target_icons_dir / "restored_icon.svg").exists())
            self.assertEqual((target_icons_dir / "restored_icon.svg").read_text(), "<svg>test</svg>")

        finally:
            icon_path_service.get_user_icons_dir = orig_get_user_icons_dir
