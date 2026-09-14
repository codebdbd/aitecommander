"""Tests for installed applications discovery service."""

import platform
from pathlib import Path

import pytest

from app.utils.system.installed_apps_service import (
    InstalledAppInfo,
    get_installed_apps,
    get_start_menu_shortcuts,
)

_VALID_PROGRAM_EXTS = {".exe", ".bat", ".cmd", ".ps1", ".msc", ".cpl"}


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows specific test")
def test_get_start_menu_shortcuts():
    shortcuts = get_start_menu_shortcuts()
    assert isinstance(shortcuts, dict)
    assert len(shortcuts) > 0
    for name, path in shortcuts.items():
        assert isinstance(name, str)
        # All resolved shortcuts must point to real program files, NOT .lnk files
        assert not path.lower().endswith(".lnk")
        assert Path(path).suffix.lower() in _VALID_PROGRAM_EXTS
        assert Path(path).exists()


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows specific test")
def test_get_installed_apps():
    apps = get_installed_apps()
    assert isinstance(apps, list)
    assert len(apps) > 0

    for app in apps:
        assert isinstance(app, InstalledAppInfo)
        assert app.name.strip() != ""
        assert app.path.strip() != ""
        assert app.app_type in ("uwp", "desktop")

    # Verify at least one UWP app exists (e.g. calculator or settings)
    uwp_apps = [a for a in apps if a.app_type == "uwp"]
    assert len(uwp_apps) > 0
    assert any("shell:appsfolder\\" in a.path.lower() for a in uwp_apps)

    # Verify that desktop apps point directly to executable files and NEVER to .lnk
    desktop_apps = [a for a in apps if a.app_type == "desktop"]
    assert len(desktop_apps) > 0
    for app in desktop_apps:
        low_p = app.path.lower()
        assert not low_p.endswith(".lnk"), f"Desktop app '{app.name}' still points to .lnk: {app.path}"
        assert Path(app.path).suffix.lower() in _VALID_PROGRAM_EXTS

    # Verify that no web URLs, documentation extensions, or uninstallers exist in the list
    for app in apps:
        low_p = app.path.lower()
        assert not low_p.startswith(("http://", "https://", "shell:appsfolder\\http"))
        for doc_ext in (".url", ".htm", ".html", ".chm", ".pdf", ".txt", ".cer", ".ico"):
            assert not low_p.endswith(doc_ext)
        assert "unins000" not in low_p
        assert "uninstall.exe" not in low_p
