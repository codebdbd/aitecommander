from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.core.log_manager import LogManager


def test_cli_version_flag_exits_zero_without_side_effects() -> None:
    res = subprocess.run(
        [sys.executable, "-m", "app.main", "--version"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "AiteCommander" in res.stdout


def test_cli_help_flag_exits_zero() -> None:
    res = subprocess.run(
        [sys.executable, "-m", "app.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "usage:" in res.stdout


def test_cli_version_does_not_import_pyqt() -> None:
    code = (
        "import sys; "
        "sys.argv = ['app.main', '--version']; "
        "import app.main; "
        "rc = app.main.main(); "
        "print('PYQT_IMPORTED', any(name.startswith('PyQt6') for name in sys.modules)); "
        "sys.exit(rc)"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "PYQT_IMPORTED False" in res.stdout


def test_log_manager_setup_fail_soft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LogManager, "_configured", False)
    blocker_file = tmp_path / "blocker.txt"
    blocker_file.write_text("blocker", encoding="utf-8")
    bad_dir = blocker_file / "subdir"

    from app.core.paths.path_manager import PathManager
    monkeypatch.setattr(PathManager, "logs_dir", lambda: bad_dir)

    # Should not raise exception; fail-soft to stream logging
    LogManager.setup()
    assert LogManager._configured is True
