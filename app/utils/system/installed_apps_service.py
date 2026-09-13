"""Service for discovering installed Windows applications.

Discovers applications from:
1. Windows Shell namespace folder (shell:AppsFolder) for UWP/Store and packaged apps.
2. Windows Start Menu directories (All Users & Current User), resolving shortcuts to their
   real program executable files (.exe, .bat, .cmd, etc.).
"""

import ctypes
from ctypes import byref, c_int, c_ubyte, c_ulong, c_ushort, c_void_p, c_wchar, c_wchar_p, Structure, wintypes
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import platform
import re
from typing import Any, Optional
import uuid

logger = logging.getLogger(__name__)


@dataclass
class InstalledAppInfo:
    """Represents an installed application."""

    name: str
    path: str  # Direct path to executable (.exe/.bat/etc.) or shell:AppsFolder\<AUMID>
    app_type: str  # "desktop" or "uwp"
    description: str = ""
    icon_path: Optional[str] = None
    args: str = ""


# Valid executable extensions for runnable desktop programs
_VALID_PROGRAM_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".msc", ".cpl"}

# Non-executable file extensions that installers place in the Start Menu
_DOCUMENT_EXTENSIONS = {
    ".url",
    ".htm",
    ".html",
    ".pdf",
    ".chm",
    ".hlp",
    ".txt",
    ".rtf",
    ".doc",
    ".docx",
    ".cer",
    ".crt",
    ".pfx",
    ".xml",
    ".json",
    ".ico",
    ".png",
    ".jpg",
}

# Known Windows GUID folders
_KNOWN_FOLDERS = {
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}": r"C:\Windows\System32",
    "{6D809377-6AF0-444B-8957-A3773F02200E}": r"C:\Program Files",
    "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}": r"C:\Program Files (x86)",
    "{D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27}": r"C:\Windows\SysWOW64",
    "{F38BF404-1D43-42F2-9305-67DE0B28FC23}": r"C:\Windows",
}


class _GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]

    def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
        super().__init__(l, w1, w2, (c_ubyte * 8)(b1, b2, b3, b4, b5, b6, b7, b8))


class _SHFILEINFOW(Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", c_wchar * 260),
        ("szTypeName", c_wchar * 80),
    ]


_IID_ISHELLITEM = _GUID(
    0x43826D1E, 0xE718, 0x42EE, 0xBC, 0x55, 0xA1, 0xE2, 0x61, 0xC3, 0x7B, 0xFE
)


def _resolve_known_folder_guid_path(raw_path: str) -> str:
    """Resolve Windows KnownFolder GUID prefixes (e.g. {1AC14E77...}\\cmd.exe) to real disk paths."""
    m = re.match(r"^\{([0-9a-fA-F\-]+)\}(.*)", raw_path)
    if not m:
        return raw_path
    guid_str = "{" + m.group(1).upper() + "}"
    sub_path = m.group(2).lstrip(r"\/")

    # 1. Try Windows API SHGetKnownFolderPath
    try:
        u = uuid.UUID(guid_str)
        guid_struct = _GUID(u.fields[0], u.fields[1], u.fields[2], *u.bytes[8:])
        p_path = c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            byref(guid_struct), 0, None, byref(p_path)
        )
        if hr == 0 and p_path.value:
            folder = p_path.value
            ctypes.windll.ole32.CoTaskMemFree(p_path)
            return f"{folder}\\{sub_path}"
    except Exception:
        pass

    # 2. Fallback to dictionary
    if guid_str in _KNOWN_FOLDERS:
        return f"{_KNOWN_FOLDERS[guid_str]}\\{sub_path}"

    return raw_path


def _is_document_or_web_target(path: str) -> bool:
    """Check if the path is a web link, document, manual, or certificate rather than a program."""
    low = (path or "").lower().strip()
    if low.startswith(("http://", "https://", "ftp://", "www.", "mailto:", "ms-help:", "javascript:")):
        return True
    for ext in _DOCUMENT_EXTENSIONS:
        if low.endswith(ext):
            return True
    return False


def _is_uninstaller(target_path: str, args: str = "") -> bool:
    """Language-independent detection of uninstaller executables based on binary name or arguments."""
    low = (target_path + " " + args).lower()
    if "unins000" in low or "uninstall" in low or "unin000" in low:
        return True
    return False


def _get_detailed_start_menu_shortcuts() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Scan Start Menu folders and resolve shortcuts to their actual executable target files.

    Returns:
        tuple of (lookup_map, unique_shortcuts_map):
            - lookup_map: keyed by lowercase stem, target filename, and target stem.
            - unique_shortcuts_map: keyed by lowercase stem.
    """
    if platform.system() != "Windows":
        return {}, {}

    start_dirs = [
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]

    from app.utils.links.link_parser import parse_lnk

    lookup_shortcuts: dict[str, dict[str, Any]] = {}
    unique_shortcuts: dict[str, dict[str, Any]] = {}

    for s_dir in start_dirs:
        p = Path(s_dir)
        if not p.exists():
            continue
        try:
            for f in p.rglob("*.lnk"):
                try:
                    info = parse_lnk(str(f))
                    target = (info.get("path") or "").strip()
                    args = (info.get("args") or "").strip()

                    # Handle Windows shell virtual shortcuts
                    if not target:
                        stem_low = f.stem.lower()
                        if "explorer" in stem_low:
                            target = os.path.expandvars(r"%WINDIR%\explorer.exe")
                        elif "control panel" in stem_low:
                            target = os.path.expandvars(r"%WINDIR%\system32\control.exe")
                        elif stem_low == "run":
                            target = os.path.expandvars(r"%WINDIR%\explorer.exe")

                    if not target:
                        continue

                    p_target = Path(target)
                    if p_target.is_dir():
                        continue

                    ext = p_target.suffix.lower()
                    if ext in _DOCUMENT_EXTENSIONS or ext not in _VALID_PROGRAM_EXTENSIONS:
                        continue

                    if _is_uninstaller(target, args):
                        continue

                    if not p_target.exists():
                        continue

                    data = {
                        "name": f.stem,
                        "target": target,
                        "args": args,
                        "icon_path": info.get("icon_path"),
                        "lnk": str(f),
                    }

                    f_stem_low = f.stem.lower()
                    lookup_shortcuts[f_stem_low] = data
                    lookup_shortcuts[p_target.name.lower()] = data
                    lookup_shortcuts[p_target.stem.lower()] = data

                    if f_stem_low not in unique_shortcuts:
                        unique_shortcuts[f_stem_low] = data
                except Exception as parse_err:
                    logger.debug("Failed parsing shortcut %s: %s", f, parse_err)
        except OSError as e:
            logger.debug("Error scanning Start Menu in %s: %s", s_dir, e)

    return lookup_shortcuts, unique_shortcuts


def get_start_menu_shortcuts() -> dict[str, str]:
    """Scan Start Menu folders for shortcuts resolved to executable program files.

    Returns:
        Mapping of lowercase shortcut name to resolved program executable (.exe) path.
    """
    _, unique_shortcuts = _get_detailed_start_menu_shortcuts()
    return {stem: data["target"] for stem, data in unique_shortcuts.items()}


def get_installed_apps() -> list[InstalledAppInfo]:
    """Discover all installed applications on Windows, resolving desktop apps to their real .exe.

    Returns:
        Sorted list of `InstalledAppInfo` objects.
    """
    if platform.system() != "Windows":
        return []

    lookup_shortcuts, unique_shortcuts = _get_detailed_start_menu_shortcuts()
    apps: list[InstalledAppInfo] = []
    seen_targets: set[str] = set()

    # Step 1: Query shell:AppsFolder via COM
    try:
        import pythoncom
        import win32com.client

        com_inited = False
        try:
            pythoncom.CoInitialize()
            com_inited = True
        except Exception:
            pass

        try:
            shell_dispatch = win32com.client.Dispatch("Shell.Application")
            apps_folder = shell_dispatch.NameSpace("shell:AppsFolder")
            if apps_folder is not None:
                for item in apps_folder.Items():
                    try:
                        name = (item.Name or "").strip()
                        raw_path = (item.Path or "").strip()
                        if not name or not raw_path:
                            continue

                        if _is_uninstaller(name, raw_path):
                            continue

                        if _is_document_or_web_target(raw_path):
                            continue

                        # Resolve KnownFolder GUID prefixes (e.g. {1AC14E77...}\cmd.exe)
                        resolved_raw = _resolve_known_folder_guid_path(raw_path)
                        low_name = name.lower()
                        low_raw = raw_path.lower()

                        # Skip directories
                        try:
                            if os.path.exists(resolved_raw) and Path(resolved_raw).is_dir():
                                continue
                        except Exception:
                            pass

                        # Case 1: Direct file on disk
                        if os.path.isabs(resolved_raw) and Path(resolved_raw).exists():
                            p_raw = Path(resolved_raw)
                            if p_raw.is_dir() or p_raw.suffix.lower() not in _VALID_PROGRAM_EXTENSIONS:
                                continue
                            if _is_uninstaller(resolved_raw):
                                continue
                            final_path = resolved_raw
                            app_type = "desktop"
                            args = ""
                            icon_path = None
                            desc = resolved_raw
                        # Case 2: Matched with resolved Start Menu shortcut (by name, raw path, or stem)
                        elif low_name in lookup_shortcuts:
                            m = lookup_shortcuts[low_name]
                            final_path = m["target"]
                            app_type = "desktop"
                            args = m["args"]
                            icon_path = m["icon_path"]
                            desc = m["target"]
                        elif low_raw in lookup_shortcuts:
                            m = lookup_shortcuts[low_raw]
                            final_path = m["target"]
                            app_type = "desktop"
                            args = m["args"]
                            icon_path = m["icon_path"]
                            desc = m["target"]
                        else:
                            # Case 3: UWP or packaged Windows Store application
                            if _is_document_or_web_target(raw_path):
                                continue
                            if any(raw_path.lower().endswith(ext) for ext in _DOCUMENT_EXTENSIONS):
                                continue
                            final_path = f"shell:AppsFolder\\{raw_path}"
                            app_type = "uwp"
                            args = ""
                            icon_path = None
                            desc = "Windows App"

                        t_key = final_path.lower()
                        if t_key not in seen_targets:
                            seen_targets.add(t_key)
                            apps.append(
                                InstalledAppInfo(
                                    name=name,
                                    path=final_path,
                                    app_type=app_type,
                                    description=desc,
                                    icon_path=icon_path,
                                    args=args,
                                )
                            )
                    except Exception as item_err:
                        logger.debug("Error reading apps folder item: %s", item_err)
        finally:
            if com_inited:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("Failed to enumerate shell:AppsFolder via COM: %s", exc)

    # Step 2: Add any remaining Start Menu shortcuts that weren't in shell:AppsFolder
    for stem_low, data in unique_shortcuts.items():
        t_key = data["target"].lower()
        if t_key not in seen_targets:
            seen_targets.add(t_key)
            apps.append(
                InstalledAppInfo(
                    name=data["name"],
                    path=data["target"],
                    app_type="desktop",
                    description=data["target"],
                    icon_path=data["icon_path"],
                    args=data["args"],
                )
            )

    # Sort alphabetically by name
    apps.sort(key=lambda a: a.name.lower())
    return apps


def extract_shell_icon_image(path: str) -> Optional[Any]:
    """Extract a native Windows icon as QImage from an executable file or shell:AppsFolder AUMID.

    Executables (.exe) are extracted cleanly without any shortcut overlay arrow badge.
    """
    if platform.system() != "Windows" or not path:
        return None

    try:
        from PyQt6.QtGui import QImage

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        ole32 = ctypes.windll.ole32

        ole32.CoInitialize(None)

        item = c_void_p()
        hr = shell32.SHCreateItemFromParsingName(
            path, None, byref(_IID_ISHELLITEM), byref(item)
        )
        if hr != 0 or not item.value:
            return None

        pidl = c_void_p()
        if shell32.SHGetIDListFromObject(item, byref(pidl)) != 0 or not pidl.value:
            return None

        sfi = _SHFILEINFOW()
        SHGFI_PIDL = 0x00000008
        SHGFI_ICON = 0x00000100
        shell32.SHGetFileInfoW(
            pidl, 0, byref(sfi), ctypes.sizeof(sfi), SHGFI_PIDL | SHGFI_ICON
        )
        if not sfi.hIcon:
            return None

        img = QImage.fromHICON(sfi.hIcon)
        user32.DestroyIcon(sfi.hIcon)
        if not img.isNull():
            return img.copy()
    except Exception as e:
        logger.debug("Failed to extract shell icon for %s: %s", path, e)
    return None


def cache_app_icon(app_info: InstalledAppInfo) -> Optional[str]:
    """Extract and persist the application's clean icon to user icons cache.

    Returns:
        Path to the saved PNG icon file, or None if extraction failed.
    """
    try:
        from app.utils.ui.icon.path_service import icon_path_service

        icons_dir = icon_path_service.get_user_icons_dir()
        safe_name = re.sub(r"[^\w\-]", "_", app_info.name).strip("_") or "app"
        icon_path = Path(icons_dir) / f"app_{safe_name[:40]}.png"

        # 1. If a custom icon path was specified on the shortcut and exists, try it
        target_icon_src = app_info.icon_path if (app_info.icon_path and Path(app_info.icon_path).exists()) else app_info.path

        # 2. Extract native Windows Shell icon (clean, no shortcut arrow)
        img = extract_shell_icon_image(target_icon_src)
        if img and not img.isNull():
            icon_path.parent.mkdir(parents=True, exist_ok=True)
            if img.save(str(icon_path), "PNG"):
                return str(icon_path)

        # 3. Fallback to _get_file_icon_with_com
        from app.utils.links.link_parser import _get_file_icon_with_com

        saved = _get_file_icon_with_com(target_icon_src, icon_path)
        if saved and Path(saved).exists():
            return saved
    except Exception as e:
        logger.warning("Failed to cache icon for app %s: %s", app_info.name, e)
    return None
