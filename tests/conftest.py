"""Pytest bootstrap for local imports."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import _pytest.pathlib as pytest_pathlib
import _pytest.tmpdir as pytest_tmpdir
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
root_str = str(PROJECT_ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

_SYSTEM_TEMP_ROOT = Path(tempfile.gettempdir())
if "sandbox" in str(_SYSTEM_TEMP_ROOT).lower():
    _SYSTEM_TEMP_ROOT = PROJECT_ROOT / ".pytest_temp"
elif _SYSTEM_TEMP_ROOT.name == "aitecommander_pytest":
    _SYSTEM_TEMP_ROOT = _SYSTEM_TEMP_ROOT.parent

TEST_TEMP_ROOT = _SYSTEM_TEMP_ROOT / "aitecommander_pytest_files"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
PYTEST_BASETEMP = _SYSTEM_TEMP_ROOT / f"aitecommander_pytest_run_{uuid.uuid4().hex}"
PYTEST_PROFILE_ROOT = TEST_TEMP_ROOT / f"pytest_profile_{uuid.uuid4().hex}"
PYTEST_APPDATA = PYTEST_PROFILE_ROOT / "AppData" / "Roaming"
PYTEST_LOCALAPPDATA = PYTEST_PROFILE_ROOT / "AppData" / "Local"
PYTEST_QSETTINGS = PYTEST_PROFILE_ROOT / "QSettings"
for _dir in (PYTEST_APPDATA, PYTEST_LOCALAPPDATA, PYTEST_QSETTINGS):
    _dir.mkdir(parents=True, exist_ok=True)

os.environ["APPDATA"] = str(PYTEST_APPDATA)
os.environ["LOCALAPPDATA"] = str(PYTEST_LOCALAPPDATA)
os.environ["TMP"] = str(_SYSTEM_TEMP_ROOT)
os.environ["TEMP"] = str(_SYSTEM_TEMP_ROOT)
tempfile.tempdir = str(_SYSTEM_TEMP_ROOT)

try:
    from PyQt6.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(PYTEST_QSETTINGS),
    )
except Exception:
    pass


def pytest_configure(config) -> None:
    config.option.basetemp = str(PYTEST_BASETEMP)


def pytest_unconfigure(config) -> None:
    shutil.rmtree(PYTEST_PROFILE_ROOT, ignore_errors=True)


pytest_pathlib.cleanup_dead_symlinks = lambda root: None
pytest_tmpdir.cleanup_dead_symlinks = lambda root: None


def build_test_temp_path(*parts: str) -> Path:
    path = TEST_TEMP_ROOT.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def tmp_path(request) -> Path:
    path = build_test_temp_path("pytest_tmp_path", f"{request.node.name}_{uuid.uuid4().hex}")
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])

