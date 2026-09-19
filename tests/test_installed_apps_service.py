"""Tests for installed applications discovery service."""

import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.links.link_parser import normalize_windows_icon_location
from app.utils.system.installed_apps_service import (
    InstalledAppInfo,
    cache_app_icon,
    get_installed_apps,
    get_start_menu_shortcuts,
)

_VALID_PROGRAM_EXTS = {".exe", ".bat", ".cmd", ".ps1", ".msc", ".cpl"}


def test_normalize_windows_icon_location_keeps_negative_resource_index(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TEST_ICON_ROOT", r"C:\Windows")

    path, index = normalize_windows_icon_location(
        r"%TEST_ICON_ROOT%\System32\imageres.dll,-102"
    )

    assert path == r"C:\Windows\System32\imageres.dll"
    assert index == -102


def test_cache_app_icon_uses_shortcut_resource_index(tmp_path: Path) -> None:
    icon_source = tmp_path / "app-icons.dll"
    icon_source.write_bytes(b"icon resources")
    icons_dir = tmp_path / "icons"
    extracted = icons_dir / "program_app-icons_-4.png"
    app = InstalledAppInfo(
        name="Example",
        path=str(tmp_path / "app.exe"),
        app_type="desktop",
        icon_path=str(icon_source),
        icon_index=-4,
    )

    def fake_extract(_path: str, _save_dir: str, _index: int) -> str:
        icons_dir.mkdir()
        extracted.write_bytes(b"png")
        return str(extracted)

    with (
        patch(
            "app.utils.ui.icon.path_service.icon_path_service.get_user_icons_dir",
            return_value=icons_dir,
        ),
        patch(
            "app.utils.links.link_parser._extract_icon_from_exe",
            side_effect=fake_extract,
        ) as extract,
    ):
        result = cache_app_icon(app)

    assert result == str(extracted)
    extract.assert_called_once_with(str(icon_source), str(icons_dir), -4)


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
