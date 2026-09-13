"""Integration test verifying clean application shutdown without Windows fastfail (0xc0000409)."""

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

    def test_runtime_deterministic_exit(self) -> None:
        """Verify that runtime.run executes cleanly with exit_on_finish=False."""
        code = (
            "import os, sys; "
            "from app.startup.runtime import StartupOptions, ExitCode, run; "
            "opts = StartupOptions(auto_quit=True, quit_after_ms=50, exit_on_finish=False); "
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
