from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from app.views.windows.dialogs.installed_apps_dialog import (
    InstalledAppsDialog,
    _AppsLoaderThread,
)


class TestInstalledAppsDialogThread(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            cls._app = QApplication([])
        else:
            cls._app = QApplication.instance()

    def test_thread_cancel_aborts_loop_and_signals(self) -> None:
        with patch(
            "app.views.windows.dialogs.installed_apps_dialog.get_installed_apps"
        ) as mock_get_apps:
            # Return list of dummy apps
            mock_apps = [
                MagicMock(name=f"App {i}", path=f"C:\\app{i}.exe", icon_path=None)
                for i in range(10)
            ]
            mock_get_apps.return_value = mock_apps

            thread = _AppsLoaderThread()
            signals_received = []
            thread.apps_ready.connect(lambda apps: signals_received.append("apps"))
            thread.icon_ready.connect(lambda idx, img: signals_received.append("icon"))
            thread.all_done.connect(lambda: signals_received.append("done"))

            thread.cancel()
            thread.run()

            # Should not emit anything after being cancelled before run
            self.assertEqual(signals_received, [])

    def test_dialog_reject_and_accept_stops_thread(self) -> None:
        with patch(
            "app.views.windows.dialogs.installed_apps_dialog.get_installed_apps",
            return_value=[],
        ):
            dialog = InstalledAppsDialog()
            self.assertTrue(hasattr(dialog, "loader_thread"))

            # Test reject stops thread
            dialog.reject()
            self.assertFalse(dialog.loader_thread.isRunning())

    def test_loader_thread_not_parented_to_dialog_to_prevent_crash(self) -> None:
        with patch(
            "app.views.windows.dialogs.installed_apps_dialog.get_installed_apps",
            return_value=[],
        ):
            dialog = InstalledAppsDialog()
            # AUD-021: parent must be None so dialog destruction does not destroy running QThread
            self.assertIsNone(dialog.loader_thread.parent())
            dialog.reject()
