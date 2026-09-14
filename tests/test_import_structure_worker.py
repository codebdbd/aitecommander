from __future__ import annotations

import sqlite3
from pathlib import Path

from app.models.workers.export_worker import ExportStructureWorker
from app.models.workers.import_worker import ImportStructureWorker


def _init_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path("app/models/schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def test_import_structure_worker_preserves_link_metadata() -> None:
    # 1. Source database setup
    src_conn = sqlite3.connect(":memory:")
    src_conn.row_factory = sqlite3.Row
    _init_schema(src_conn)

    src_conn.execute("INSERT INTO sphere (id, name, position) VALUES (1, 'Main Sphere', 0);")
    src_conn.execute("INSERT INTO section (id, sphere_id, name, position) VALUES (1, 1, 'Main Section', 0);")
    src_conn.execute("INSERT INTO category (id, section_id, name, position) VALUES (1, 1, 'Main Category', 0);")

    src_conn.execute(
        """INSERT INTO link 
           (id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position)
           VALUES (1, 1, 'Test Link 1', 'https://example.com', 'web', 
                   'Secret notes line 1\nSecret notes line 2', 1, '2026-09-13 10:30:00', 'icons/test.ico', '--incognito', 'chrome_work', 0);"""
    )
    src_conn.execute(
        """INSERT INTO link 
           (id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position)
           VALUES (2, 1, 'Test Link 2', 'https://example.org', 'web', 
                   '', 0, NULL, '', '', NULL, 1);"""
    )
    src_conn.commit()

    # 2. Export full structure
    export_worker = ExportStructureWorker()
    exported_data = export_worker.do_work(src_conn)
    assert "spheres" in exported_data
    assert len(exported_data["links"]) == 2

    # 3. Import into destination database
    dst_conn = sqlite3.connect(":memory:")
    dst_conn.row_factory = sqlite3.Row
    _init_schema(dst_conn)

    import_worker = ImportStructureWorker(exported_data)
    stats = import_worker.do_work(dst_conn)

    assert stats["spheres"] == 1
    assert stats["sections"] == 1
    assert stats["categories"] == 1
    assert stats["links"] == 2

    # 4. Verify link 1 metadata
    row1 = dst_conn.execute("SELECT * FROM link WHERE name = 'Test Link 1'").fetchone()
    assert row1 is not None
    assert row1["notes"] == "Secret notes line 1\nSecret notes line 2"
    assert row1["is_favorite"] == 1
    assert row1["last_used"] == "2026-09-13 10:30:00"
    assert row1["args"] == "--incognito"
    assert row1["browser_key"] == "chrome_work"

    # 5. Verify link 2 defaults
    row2 = dst_conn.execute("SELECT * FROM link WHERE name = 'Test Link 2'").fetchone()
    assert row2 is not None
    assert row2["notes"] == ""
    assert row2["is_favorite"] == 0
    assert row2["last_used"] is None
    assert row2["args"] == ""
    assert row2["browser_key"] is None


def test_import_structure_worker_normalizes_boolean_and_empty_metadata() -> None:
    dst_conn = sqlite3.connect(":memory:")
    dst_conn.row_factory = sqlite3.Row
    _init_schema(dst_conn)

    payload = [
        {
            "name": "Sphere",
            "position": 0,
            "sections": [
                {
                    "name": "Section",
                    "position": 0,
                    "categories": [
                        {
                            "name": "Category",
                            "position": 0,
                            "links": [
                                {
                                    "name": "Link with bool fav",
                                    "url": "https://a.com",
                                    "type": "web",
                                    "is_favorite": True,
                                    "notes": None,
                                    "last_used": None,
                                },
                                {
                                    "name": "Link without extra keys",
                                    "url": "https://b.com",
                                    "type": "web",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    ]

    worker = ImportStructureWorker(payload)
    stats = worker.do_work(dst_conn)
    assert stats["links"] == 2

    l1 = dst_conn.execute("SELECT * FROM link WHERE name = 'Link with bool fav'").fetchone()
    assert l1["is_favorite"] == 1
    assert l1["notes"] == ""
    assert l1["last_used"] is None

    l2 = dst_conn.execute("SELECT * FROM link WHERE name = 'Link without extra keys'").fetchone()
    assert l2["is_favorite"] == 0
    assert l2["notes"] == ""
    assert l2["last_used"] is None
