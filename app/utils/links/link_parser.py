import logging
import re
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, TypedDict

import pythoncom
import win32api
import win32con
import win32gui
import win32ui
from PIL import Image
from PyQt6.QtCore import QFileInfo
from PyQt6.QtWidgets import QFileIconProvider
from win32com.shell import shell

from app.utils.ui.icon.icon_resolver import (
    resolve_icon_for_link,
)
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.icon.validation import (
    is_cached_icon_valid,
    is_valid_icon_file,
    validate_config_for_icons,
)
from app.utils.validators import (
    validate_link_type,
    validate_path,
)

_provider_lock = threading.Lock()
_provider = None

# Module logger
logger = logging.getLogger(__name__)


def _get_icon_provider():
    """Gets thread-safe QFileIconProvider instance"""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = QFileIconProvider()
    return _provider


def _validate_exe_path(exe_path: str) -> bool:
    """Local EXE path validation: existence, file, extension."""
    if not exe_path or not isinstance(exe_path, str):
        return False
    exe_path_obj = Path(exe_path)
    if not exe_path_obj.is_file():
        return False
    if not exe_path.lower().endswith(".exe"):
        return False
    return True


@contextmanager
def com_context():
    """Context manager for COM initialization"""
    try:
        pythoncom.CoInitialize()
        yield
    except pythoncom.com_error as e:
        logger.error("COM initialization failed: %s", e)
        raise
    finally:
        try:
            pythoncom.CoUninitialize()
        except pythoncom.com_error:
            pass


class _GDIResources(TypedDict, total=False):
    hdc_compat: Any
    hdc: Any
    icons: list[int]


@contextmanager
def gdi_context():
    """Context manager for GDI resources"""
    resources: _GDIResources = {}
    try:
        yield resources
    finally:
        if "hdc_compat" in resources:
            try:
                resources["hdc_compat"].DeleteDC()
            except (win32ui.error, AttributeError):
                pass
        if "hdc" in resources:
            try:
                resources["hdc"].DeleteDC()
            except (win32ui.error, AttributeError):
                pass
        if "icons" in resources:
            for icon in resources["icons"]:
                try:
                    win32gui.DestroyIcon(icon)
                except win32gui.error:
                    pass


def _get_default_icon(icon_type: str, config) -> str:
    """Returns FULL path to default icon for specified type via icon_resolver."""
    try:
        resolved = resolve_icon_for_link({"type": icon_type, "icon_path": ""})
        return resolved or ""
    except (RuntimeError, ValueError, OSError) as e:
        logger.warning("_get_default_icon failed for type=%s: %s", icon_type, e)
        return ""


def _extract_icon_from_exe(exe_path: str, save_dir: str) -> Optional[str]:
    """Extracts icon from EXE file with improved error handling"""
    if not _validate_exe_path(exe_path):
        return None
    save_dir_obj = Path(save_dir)
    if not save_dir_obj.exists():
        try:
            save_dir_obj.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Cannot create icons directory %s: %s", save_dir, e)
            return None
    base_name = Path(exe_path).stem
    save_path = save_dir_obj / f"program_{base_name}.ico"
    if is_cached_icon_valid(str(save_path), exe_path):
        logger.debug("Using cached EXE icon: %s", save_path)
        return str(save_path)
    try:
        with gdi_context() as resources:
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            if not large:
                logger.debug("No icon found in %s", exe_path)
                return None
            resources["icons"] = large + small
            hicon = large[0]
            ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
            resources["hdc"] = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(resources["hdc"], ico_x, ico_x)
            resources["hdc_compat"] = resources["hdc"].CreateCompatibleDC()
            resources["hdc_compat"].SelectObject(hbmp)
            resources["hdc_compat"].DrawIcon((0, 0), hicon)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGBA",
                (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                bmpstr,
                "raw",
                "BGRA",
                0,
                1,
            )
            img.save(save_path, format="ICO")
            logger.debug("Extracted EXE icon saved: %s", save_path)
            return str(save_path)
    except win32ui.error as e:
        logger.error("Win32 error extracting icon from %s: %s", exe_path, e)
    except OSError as e:
        logger.error("File error extracting icon from %s: %s", exe_path, e)
    except (RuntimeError, ValueError) as e:
        logger.error("Error extracting icon from %s: %s", exe_path, e)
    return None


def _parse_lnk(lnk_path: str) -> dict[str, str]:
    """Parses .lnk file with improved error handling"""
    if not lnk_path or not isinstance(lnk_path, str):
        return {}
    lnk_path_obj = Path(lnk_path)
    if not lnk_path_obj.exists() or not lnk_path.lower().endswith(".lnk"):
        return {}
    try:
        with com_context():
            shortcut: Any = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink,
            )
            persist_file: Any = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
            persist_file.Load(lnk_path)
            path, _ = shortcut.GetPath(shell.SLGP_UNCPRIORITY)
            args = shortcut.GetArguments()
            icon_path, icon_index = shortcut.GetIconLocation()
            result = {
                "path": path or "",
                "args": args or "",
                "icon_path": icon_path or "",
                "icon_index": str(icon_index) if icon_index else "0",
            }
            logger.debug("Parsed .lnk: %s", result)
            return result
    except pythoncom.com_error as e:
        logger.error("COM error parsing .lnk file %s: %s", lnk_path, e)
    except OSError as e:
        logger.error("File error parsing .lnk file %s: %s", lnk_path, e)
    except (RuntimeError, ValueError) as e:
        logger.error("Error parsing .lnk file %s: %s", lnk_path, e)
    return {}


def parse_lnk(lnk_path: str) -> dict[str, str]:
    """Public wrapper for parsing .lnk files.

    Stable API for external modules. Delegates to private implementation
    `_parse_lnk`, allowing future changes to internals without affecting clients.
    """
    return _parse_lnk(lnk_path)


def _get_name_for_link_type(link_type: str, path: str, lnk_info: dict[str, str]) -> str:
    """Determines name for link based on type"""
    if not path:
        return "Unknown"
    try:
        if link_type == "chromeapp":
            return Path(path).stem
        elif link_type == "program":
            target_path = lnk_info.get("path") if lnk_info else path
            return Path(target_path).stem if target_path else Path(path).stem
        elif link_type == "folder":
            return Path(path).name
        elif link_type == "file":
            return Path(path).stem
        else:
            return Path(path).stem
    except (OSError, ValueError, RuntimeError, AttributeError, TypeError) as e:
        logger.error(
            "Error getting name for link_type=%s path=%s: %s", link_type, path, e
        )
        return "Unknown"


def _handle_folder_icon(config) -> str:
    """Handles folder icon via centralized resolver."""
    try:
        resolved = resolve_icon_for_link({"type": "folder", "icon_path": ""})
        if resolved and Path(resolved).exists():
            return resolved
    except (RuntimeError, ValueError, OSError) as e:
        logger.debug("folder icon resolve failed (type=folder): %s", e)
    return _get_default_icon("folder", config)


def _handle_chromeapp_icon(lnk_info: dict[str, str], icons_dir: str) -> Optional[str]:
    """Handles Chrome app icon"""
    logger.info("[ICON_PARSE] _handle_chromeapp_icon called, lnk_info=%s", lnk_info)
    args = lnk_info.get("args", "")
    if not args:
        logger.info("[ICON_PARSE] Chrome app: no args found")
        return None
    app_id_match = re.search(r"--app-id=([a-z0-9]{32})", args)
    if not app_id_match:
        logger.info("[ICON_PARSE] Chrome app: app_id not found in args: %s", args)
        return None
    app_id = app_id_match.group(1)
    logger.info("[ICON_PARSE] Chrome app: app_id=%s", app_id)
    icons_dir_obj = Path(icons_dir)
    icon_dst = icons_dir_obj / f"chromeapp_{app_id}.png"
    if is_valid_icon_file(str(icon_dst)):
        logger.info("[ICON_PARSE] Using cached chromeapp icon: %s", icon_dst)
        return str(icon_dst)
    icon_src = lnk_info.get("icon_path")
    logger.info("[ICON_PARSE] Chrome app: icon_src=%s", icon_src)
    if icon_src and Path(icon_src).exists():
        try:
            icon_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(icon_src, str(icon_dst))
            if is_valid_icon_file(str(icon_dst)):
                logger.info("[ICON_PARSE] Copied chromeapp icon: %s", icon_dst)
                return str(icon_dst)
        except OSError as e:
            logger.error("[ICON_PARSE] Failed to copy chromeapp icon: %s", e)
    logger.info("[ICON_PARSE] Chrome app: returning None")
    return None


def _handle_program_icon(
    path: str, lnk_info: dict[str, str], icons_dir: str
) -> Optional[str]:
    """Handles program icon"""
    logger.info("[ICON_PARSE] _handle_program_icon called, path=%s, lnk_info=%s", path, lnk_info)
    target_path = lnk_info.get("path") if lnk_info else path
    logger.info("[ICON_PARSE] Program: target_path=%s", target_path)
    if target_path and target_path.lower().endswith(".exe"):
        logger.info("[ICON_PARSE] Extracting icon from exe: %s", target_path)
        result = _extract_icon_from_exe(target_path, icons_dir)
        logger.info("[ICON_PARSE] Extract result: %s", result)
        return result
    logger.info("[ICON_PARSE] Program: returning None (not an exe)")
    return None


def _handle_file_icon(path: str, icons_dir: str) -> Optional[str]:
    """Handles file icon"""
    if not path:
        return None
    try:
        ext = Path(path).suffix.lower().replace(".", "")
        if not ext:
            return None
        icons_dir_obj = Path(icons_dir)
        icon_path = icons_dir_obj / f"file_{ext}.png"
        if is_valid_icon_file(str(icon_path)):
            return str(icon_path)
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        provider = _get_icon_provider()
        q_icon = provider.icon(QFileInfo(path))
        if not q_icon.isNull():
            pixmap = q_icon.pixmap(256, 256)
            if pixmap.save(str(icon_path), "PNG"):
                logger.debug("Extracted file icon: %s", icon_path)
                return str(icon_path)
    except (OSError, RuntimeError, AttributeError, ValueError) as e:
        logger.error("Failed to extract file icon for path=%s: %s", path, e)
    return None


def _get_icon_for_link_type(
    link_type: str, path: str, lnk_info: dict[str, str], config, icons_dir: str
) -> str:
    """Determines icon for link based on type"""
    logger.info("[ICON_PARSE] _get_icon_for_link_type: link_type=%s, path=%s", link_type, path)
    icon: Optional[str] = None
    try:
        if link_type == "folder":
            icon = _handle_folder_icon(config)
        elif link_type == "chromeapp":
            logger.info("[ICON_PARSE] Handling chromeapp icon")
            icon = _handle_chromeapp_icon(lnk_info, icons_dir)
        elif link_type == "program":
            logger.info("[ICON_PARSE] Handling program icon")
            icon = _handle_program_icon(path, lnk_info, icons_dir)
        elif link_type == "file":
            icon = _handle_file_icon(path, icons_dir)
    except (OSError, RuntimeError, ValueError, KeyError, AttributeError) as e:
        logger.error(
            "[ICON_PARSE] Error getting icon for link_type=%s path=%s lnk_info=%s: %s",
            link_type,
            path,
            lnk_info,
            e,
        )
    logger.info("[ICON_PARSE] Extracted icon: %s", icon)
    if icon and is_valid_icon_file(icon):
        logger.info("[ICON_PARSE] Using extracted icon: %s", icon)
        return icon
    fallback = _get_default_icon(link_type, config)
    logger.info("[ICON_PARSE] Fallback to default icon: %s", fallback)
    return fallback or ""


def parse_local_link(
    link_type: str, path: str, config, args: Optional[str] = None
) -> dict[str, str]:
    """Parses local link and returns information about it, including name and icon."""
    if not validate_link_type(link_type):
        logger.error("Invalid link_type: %r", link_type)
        return {"name": "Error", "icon": ""}
    if not validate_path(path):
        logger.error("Invalid path: %r", path)
        return {"name": "Error", "icon": ""}
    if not validate_config_for_icons(config):
        logger.error("Config.LINK_ICONS_DIR not found")
        return {"name": "Error", "icon": ""}
    icons_dir = str(icon_path_service.get_user_icons_dir())
    lnk_info = {}
    if path.lower().endswith(".lnk"):
        lnk_info = _parse_lnk(path)
    else:
        lnk_info = {}
    name = _get_name_for_link_type(link_type, path, lnk_info)
    icon = _get_icon_for_link_type(link_type, path, lnk_info, config, icons_dir)
    result = {"name": name, "icon": icon}
    logger.debug("parse_local_link result: %s", result)
    return result
