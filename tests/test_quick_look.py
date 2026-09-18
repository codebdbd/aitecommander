from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from app.views.windows.dialogs.quick_look_dialog import QuickLookDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestQuickLookDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.opened_urls: list[str] = []
        self.nav_directions: list[int] = []
        self.parent_widget = QWidget()
        self.dialog = QuickLookDialog(
            parent=self.parent_widget,
            on_open_callback=self.opened_urls.append,
            on_navigate_callback=self.nav_directions.append,
        )

    def tearDown(self) -> None:
        self.dialog.close()
        self.parent_widget.close()

    def test_text_preview(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Line 1\nLine 2\nLine 3\n")
            temp_path = f.name
        try:
            self.dialog.set_link({"name": "Test Text", "url": temp_path, "type": "file"})
            self.assertIn("Line 1", self.dialog._text_edit.toPlainText())
            self.assertIn("UTF-8", self.dialog._text_info_lbl.text())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_csv_preview(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("Header1,Header2,Header3\nVal1,Val2,Val3\nVal4,Val5,Val6\n")
            temp_path = f.name
        try:
            self.dialog.set_link({"name": "Test CSV", "url": temp_path, "type": "file"})
            self.assertEqual(2, self.dialog._table_view.rowCount())
            self.assertEqual(3, self.dialog._table_view.columnCount())
            self.assertEqual("Val1", self.dialog._table_view.item(0, 0).text())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_xlsx_preview_with_shared_strings_and_formulas(self) -> None:
        with tempfile.NamedTemporaryFile("wb", suffix=".xlsx", delete=False) as f:
            temp_path = f.name
        try:
            with zipfile.ZipFile(temp_path, "w") as z:
                shared_strings = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<si><t>Header Col</t></si>'
                    '</sst>'
                )
                sheet_xml = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    '<sheetData>'
                    '<row r="1">'
                    '<c r="A1" t="s"><v>0</v></c>'
                    '<c r="B1"><v>100</v></c>'
                    '<c r="C1"><f>A1+B1</f><v>200</v></c>'
                    '<c r="D1"><f>NOW()</f></c>'
                    '</row>'
                    '</sheetData>'
                    '</worksheet>'
                )
                z.writestr("xl/sharedStrings.xml", shared_strings)
                z.writestr("xl/worksheets/sheet1.xml", sheet_xml)

            self.dialog.set_link({"name": "Test XLSX", "url": temp_path, "type": "file"})
            self.assertEqual(1, self.dialog._table_view.rowCount())
            self.assertEqual(4, self.dialog._table_view.columnCount())
            self.assertEqual("Header Col", self.dialog._table_view.item(0, 0).text())
            self.assertEqual("100", self.dialog._table_view.item(0, 1).text())
            self.assertEqual("200", self.dialog._table_view.item(0, 2).text())
            self.assertEqual("=NOW()", self.dialog._table_view.item(0, 3).text())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_zip_preview(self) -> None:
        with tempfile.NamedTemporaryFile("wb", suffix=".zip", delete=False) as f:
            temp_path = f.name
        try:
            with zipfile.ZipFile(temp_path, "w") as z:
                z.writestr("file1.txt", "content1")
                z.writestr("subdir/file2.txt", "content2")

            self.dialog.set_link({"name": "Test ZIP", "url": temp_path, "type": "file"})
            self.assertEqual(2, self.dialog._folder_list.count())
            self.assertEqual(self.dialog._stack.currentWidget(), self.dialog._folder_page)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_missing_file_renders_delicate_warning(self) -> None:
        fake_path = "C:/non_existent_folder/missing_file.pdf"
        self.dialog.set_link({"name": "Missing", "url": fake_path, "type": "file"})
        self.assertEqual(self.dialog._stack.currentWidget(), self.dialog._card_page)
        self.assertFalse(self.dialog._open_btn.isEnabled())
        self.assertIn("missing_file.pdf", self.dialog._card_desc_lbl.text())

    def test_context_menus_cleaned_up_on_set_link(self) -> None:
        dummy_menu = QMenu(self.dialog)
        self.dialog._context_menus.append(dummy_menu)
        self.assertEqual(1, len(self.dialog._context_menus))

        self.dialog.set_link({"name": "New Link", "url": "https://example.com", "type": "web"})
        self.assertEqual(0, len(self.dialog._context_menus))

    def test_keyboard_events_dispatch(self) -> None:
        # Test Return/Enter calls on_open_callback
        enter_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        handled = self.dialog._handle_key_event(enter_event)
        self.assertTrue(handled)

        # Test Up and Down navigation callbacks
        down_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.dialog._handle_key_event(down_event))
        self.assertEqual([1], self.nav_directions)

        up_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.dialog._handle_key_event(up_event))
        self.assertEqual([1, -1], self.nav_directions)

        # Test Esc closes dialog
        esc_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        self.assertTrue(self.dialog._handle_key_event(esc_event))

    def test_copy_content_action(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Test content to copy")
            temp_path = f.name
        try:
            self.dialog.set_link({"name": "Test Copy", "url": temp_path, "type": "file"})
            self.assertFalse(self.dialog._copy_content_btn.isHidden())
            self.dialog._handle_copy_content()
            self.assertEqual("Test content to copy", QApplication.clipboard().text())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_syntax_highlighter_configured_on_code(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("def foo():\n    return True\n")
            temp_path = f.name
        try:
            self.dialog.set_link({"name": "Code", "url": temp_path, "type": "file"})
            self.assertIsNotNone(self.dialog._syntax_highlighter.document())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_media_preview_wav(self) -> None:
        import wave
        with tempfile.NamedTemporaryFile("wb", suffix=".wav", delete=False) as f:
            temp_path = f.name
        try:
            with wave.open(temp_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(44100)
                w.writeframes(b"\x00\x00" * 44100)
            self.dialog.set_link({"name": "Test Audio", "url": temp_path, "type": "file"})
            self.assertEqual(self.dialog._stack.currentWidget(), self.dialog._card_page)
            self.assertIn("WAV", self.dialog._card_desc_lbl.text())
            self.assertIn("0:01", self.dialog._card_desc_lbl.text())
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
