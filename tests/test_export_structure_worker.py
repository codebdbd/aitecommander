from __future__ import annotations

import sqlite3
import unittest

from app.models.workers.export_worker import ExportStructureWorker


class TestExportStructureWorker(unittest.TestCase):
    def test_init_accepts_db_path(self) -> None:
        worker = ExportStructureWorker("custom/path/links.db")
        self.assertEqual(worker.db_path, "custom/path/links.db")

        worker_no_arg = ExportStructureWorker()
        self.assertIsNone(worker_no_arg.db_path)

    def test_do_work_builds_hierarchical_and_flat_data(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT, position INTEGER);
            CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER, name TEXT, position INTEGER);
            CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER, name TEXT, position INTEGER);
            CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, url TEXT, position INTEGER);

            INSERT INTO sphere (id, name, position) VALUES (1, 'Sphere 1', 0);
            INSERT INTO section (id, sphere_id, name, position) VALUES (10, 1, 'Section 1', 0);
            INSERT INTO category (id, section_id, name, position) VALUES (100, 10, 'Category 1', 0);
            INSERT INTO link (id, category_id, name, url, position) VALUES (1000, 100, 'Link 1', 'https://example.com', 0);
            """
        )

        worker = ExportStructureWorker()
        result = worker.do_work(conn)

        # Check flat tables
        self.assertEqual(len(result["spheres"]), 1)
        self.assertEqual(len(result["sections"]), 1)
        self.assertEqual(len(result["categories"]), 1)
        self.assertEqual(len(result["links"]), 1)

        # Check hierarchy
        sphere = result["spheres"][0]
        self.assertEqual(sphere["name"], "Sphere 1")
        self.assertEqual(len(sphere["sections"]), 1)
        section = sphere["sections"][0]
        self.assertEqual(section["name"], "Section 1")
        self.assertEqual(len(section["categories"]), 1)
        category = section["categories"][0]
        self.assertEqual(category["name"], "Category 1")
        self.assertEqual(len(category["links"]), 1)
        link = category["links"][0]
        self.assertEqual(link["name"], "Link 1")
