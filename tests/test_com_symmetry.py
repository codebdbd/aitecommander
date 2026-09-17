"""Architectural guard: verify COM symmetry and ensure root main.py remains a thin wrapper."""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
APP_MAIN_SRC = (APP_ROOT / "app" / "main.py").read_text(encoding="utf-8")
ROOT_MAIN_SRC = (APP_ROOT / "main.py").read_text(encoding="utf-8")


def test_no_com_logic_in_root_main() -> None:
    """Root main.py MUST NOT contain COM logic, CoUninitialize, or ExitProcess."""
    assert "CoUninitialize" not in ROOT_MAIN_SRC
    assert "CoInitialize" not in ROOT_MAIN_SRC
    assert "ExitProcess" not in ROOT_MAIN_SRC


def test_com_lifecycle_in_app_main() -> None:
    """CoInitialize and CoUninitialize must both exist symmetrically in app/main.py."""
    assert "CoInitialize" in APP_MAIN_SRC
    assert "CoUninitialize" in APP_MAIN_SRC
