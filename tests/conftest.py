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
if _SYSTEM_TEMP_ROOT.name == "aitecommander_pytest":
    _SYSTEM_TEMP_ROOT = _SYSTEM_TEMP_ROOT.parent

TEST_TEMP_ROOT = _SYSTEM_TEMP_ROOT / "aitecommander_pytest_files"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
PYTEST_BASETEMP = _SYSTEM_TEMP_ROOT / f"aitecommander_pytest_run_{uuid.uuid4().hex}"
os.environ["TMP"] = str(_SYSTEM_TEMP_ROOT)
os.environ["TEMP"] = str(_SYSTEM_TEMP_ROOT)
tempfile.tempdir = str(_SYSTEM_TEMP_ROOT)


def pytest_configure(config) -> None:
    config.option.basetemp = str(PYTEST_BASETEMP)


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
