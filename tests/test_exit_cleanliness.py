"""Integration test verifying clean application shutdown without Windows fastfail (0xc0000409)."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestExitCleanliness(unittest.TestCase):
    """Verify that Python/Qt process shutdown terminates cleanly with exit code 0."""

    def test_cli_help_exit_code_zero(self) -> None:
        """Run application with --help in subprocess and assert clean exit code 0."""
        cmd = [sys.executable, str(ROOT / "main.py"), "--help"]
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
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
        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, f"Expected 0, got {result.returncode}. Stderr: {result.stderr}")
