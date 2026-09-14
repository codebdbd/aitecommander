"""Tests for section MIME data creation and parsing."""

import unittest

from PyQt6.QtCore import QByteArray, QMimeData
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser


class TestSectionMimeData(unittest.TestCase):
    """Tests for MimeDataParser section helpers."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_create_and_extract_section_payload(self):
        mime = MimeDataParser.create_section_mime_data([42], source_sphere_id=2)
        sec_mime = app_config.get_section_mime_type()
        self.assertTrue(mime.hasFormat(sec_mime))

        ids, source_sphere = MimeDataParser.extract_section_payload(mime)
        self.assertEqual(ids, [42])
        self.assertEqual(source_sphere, 2)

    def test_create_section_mime_without_source_sphere(self):
        mime = MimeDataParser.create_section_mime_data([10, 20])
        ids, source_sphere = MimeDataParser.extract_section_payload(mime)
        self.assertEqual(ids, [10, 20])
        self.assertIsNone(source_sphere)

    def test_extract_from_empty_or_invalid_mime(self):
        empty_mime = QMimeData()
        ids, source_sphere = MimeDataParser.extract_section_payload(empty_mime)
        self.assertEqual(ids, [])
        self.assertIsNone(source_sphere)

        corrupt_mime = QMimeData()
        corrupt_mime.setData(app_config.get_section_mime_type(), QByteArray(b"not json"))
        ids, source_sphere = MimeDataParser.extract_section_payload(corrupt_mime)
        self.assertEqual(ids, [])
        self.assertIsNone(source_sphere)


if __name__ == "__main__":
    unittest.main()
