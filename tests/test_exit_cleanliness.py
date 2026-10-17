"""Integration test verifying clean application shutdown without Windows fastfail (0xc0000409)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestExitCleanliness(unittest.TestCase):
    """Verify that Python/Qt process shutdown terminates cleanly with exit code 0."""

    def setUp(self) -> None:
        self.data_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_dir.cleanup)
        self.env = os.environ.copy()
        self.env["APPDATA"] = self.data_dir.name
        self.env["LOCALAPPDATA"] = self.data_dir.name
        self.env.pop("PYTEST_CURRENT_TEST", None)

    def test_cli_help_exit_code_zero(self) -> None:
        """Run application with --help in subprocess and assert clean exit code 0."""
        cmd = [sys.executable, str(ROOT / "main.py"), "--help"]
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, f"Expected 0, got {result.returncode}. Stderr: {result.stderr}")

    def test_runtime_headless_returns_with_exit_on_finish_disabled(self) -> None:
        """Verify that runtime.run can return normally for embedding/headless callers."""
        code = (
            "import sys; "
            "from app.startup.initializer import StartupMode; "
            "from app.startup.runtime import StartupOptions, run; "
            "opts = StartupOptions(mode=StartupMode.HEADLESS, auto_quit=True, quit_after_ms=0, exit_on_finish=False); "
            "rc = run(opts); "
            "sys.exit(int(rc))"
        )
        cmd = [sys.executable, "-c", code]
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, f"Expected 0, got {result.returncode}. Stderr: {result.stderr}")

    def test_runtime_gui_auto_quit_exits_cleanly(self) -> None:
        """Verify that the production GUI exit path avoids Windows Qt teardown fastfail."""
        code = (
            "from app.startup.runtime import StartupOptions, run; "
            "run(StartupOptions(auto_quit=True, quit_after_ms=50, exit_on_finish=True))"
        )
        cmd = [sys.executable, "-c", code]
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, f"Expected 0, got {result.returncode}. Stderr: {result.stderr}")

    def test_main_window_close_runs_shutdown_before_process_exit(self) -> None:
        """Exercise closeEvent, including COM setup, instead of only app.quit()."""
        code = """
import app.main
from PyQt6.QtCore import QTimer
from app.startup import runtime
from app.views.windows.main_window import MainWindow

def schedule_close(app, options):
    def close_window():
        windows = [w for w in app.topLevelWidgets() if isinstance(w, MainWindow)]
        assert len(windows) == 1
        windows[0].close()
    QTimer.singleShot(500, close_window)

runtime._schedule_auto_quit = schedule_close
runtime.run(runtime.StartupOptions(exit_on_finish=True))
"""
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=str(ROOT), env=self.env,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        log = (Path(self.data_dir.name) / "Codebdbd" / "Aite Commander" / "logs" / "app.log").read_text(encoding="utf-8")
        self.assertIn("MainWindow.closeEvent: initiating shutdown", log)
        self.assertIn("Application shutdown completed successfully", log)
        self.assertIn("APPLICATION SHUTDOWN", log)
