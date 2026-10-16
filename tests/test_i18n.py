from __future__ import annotations

import argparse
import os
import unittest

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from i18n.cli import cmd_check
from i18n.language_service import LanguageService

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestI18nSubsystem(unittest.TestCase):
    """Comprehensive tests for the internationalization subsystem."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.service = LanguageService.instance()
        self._initial_lang = self.service.current_language()

    def tearDown(self) -> None:
        self.service.set_language(self._initial_lang)

    def test_catalogs_integrity_and_parity(self) -> None:
        """Verify all translation catalogs pass 100% completeness and parity check."""
        ret = cmd_check(argparse.Namespace())
        self.assertEqual(0, ret, "Translation catalog integrity check failed")

    def test_available_languages_contain_all_six(self) -> None:
        """Verify LanguageService exposes all 6 official languages."""
        langs = self.service.available_languages()
        codes = {d.code for d in langs}
        expected = {"en", "ru", "uk", "de", "es", "fr"}
        self.assertEqual(expected, codes)

    def test_switch_language_and_signals(self) -> None:
        """Verify set_language updates current_language and emits signal."""
        received: list[str] = []
        self.service.languageChanged.connect(received.append)
        try:
            self.assertTrue(self.service.set_language("de"))
            self.assertEqual("de", self.service.current_language())
            self.assertIn("de", received)

            self.assertTrue(self.service.set_language("ru"))
            self.assertEqual("ru", self.service.current_language())
            self.assertIn("ru", received)
        finally:
            self.service.languageChanged.disconnect(received.append)

    def test_runtime_pluralization(self) -> None:
        """Verify %n evaluation works for plural numerus forms across languages."""
        # Russian (3 grammatical forms: 1, 2-4, 5+)
        self.service.set_language("ru")
        self.assertEqual(
            "Выбран 1 элемент",
            QCoreApplication.translate("BaseDragDropTable", "%n item selected", "", 1),
        )
        self.assertEqual(
            "Выбрано 2 элемента",
            QCoreApplication.translate("BaseDragDropTable", "%n item selected", "", 2),
        )
        self.assertEqual(
            "Выбрано 5 элементов",
            QCoreApplication.translate("BaseDragDropTable", "%n item selected", "", 5),
        )

        # English (2 grammatical forms: 1, 2+)
        self.service.set_language("en")
        self.assertEqual(
            "1 item selected",
            QCoreApplication.translate("BaseDragDropTable", "%n item selected", "", 1),
        )
        self.assertEqual(
            "2 items selected",
            QCoreApplication.translate("BaseDragDropTable", "%n item selected", "", 2),
        )
        self.assertEqual(
            "5 items selected",
            QCoreApplication.translate("BaseDragDropTable", "%n item selected", "", 5),
        )


if __name__ == "__main__":
    unittest.main()
