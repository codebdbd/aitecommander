import logging
import os
import re
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

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

# Модульный логгер
logger = logging.getLogger(__name__)


def _get_icon_provider():
    """Получает thread-safe instance QFileIconProvider"""
    global _provider
    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = QFileIconProvider()
    return _provider


def _validate_exe_path(exe_path: str) -> bool:
    """Локальная проверка пути к EXE: существование, файл, расширение, доступ и разумный размер."""
    if not exe_path or not isinstance(exe_path, str):
        return False
    if not os.path.isfile(exe_path):
        return False
    if not exe_path.lower().endswith(".exe"):
        return False
    # Проверяем доступ на чтение
    if not os.access(exe_path, os.R_OK):
        return False
    # Мягкий лимит размера (100 МБ) как защита от случайно огромных файлов
    try:
        if os.path.getsize(exe_path) > 100 * 1024 * 1024:
            logger.warning("EXE file too large: %s", exe_path)
            return False
    except OSError:
        return False
    return True


@contextmanager
def com_context():
    """Контекстный менеджер для COM инициализации"""
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


@contextmanager
def gdi_context():
    """Контекстный менеджер для GDI ресурсов"""
    resources = {}
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
    """Возвращает ПОЛНЫЙ путь к иконке по умолчанию для указанного типа через icon_resolver."""
    try:
        resolved = resolve_icon_for_link({"type": icon_type, "icon_path": ""})
        return resolved or ""
    except Exception:
        return ""


def _extract_icon_from_exe(exe_path: str, save_dir: str) -> Optional[str]:
    """Извлекает иконку из EXE файла с улучшенной обработкой ошибок"""
    if not _validate_exe_path(exe_path):
        return None
    if not os.path.exists(save_dir):
        try:
            os.makedirs(save_dir, exist_ok=True)
        except OSError as e:
            logger.error("Cannot create icons directory %s: %s", save_dir, e)
            return None
    base_name = Path(exe_path).stem
    save_path = os.path.join(save_dir, f"program_{base_name}.ico")
    if is_cached_icon_valid(save_path, exe_path):
        logger.debug("Using cached EXE icon: %s", save_path)
        return save_path
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
            return save_path
    except win32ui.error as e:
        logger.error("Win32 error extracting icon from %s: %s", exe_path, e)
    except OSError as e:
        logger.error("File error extracting icon from %s: %s", exe_path, e)
    except Exception as e:
        logger.error("Unexpected error extracting icon from %s: %s", exe_path, e)
    return None


def _parse_lnk(lnk_path: str) -> Dict[str, str]:
    """Парсит .lnk файл с улучшенной обработкой ошибок"""
    if not lnk_path or not isinstance(lnk_path, str):
        return {}
    if not os.path.exists(lnk_path) or not lnk_path.lower().endswith(".lnk"):
        return {}
    try:
        with com_context():
            shortcut = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink,
            )
            persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
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
        logger.error("File error parsing .lnк file %s: %s", lnk_path, e)
    except Exception as e:
        logger.error("Unexpected error parsing .lnк file %s: %s", lnk_path, e)
    return {}


def parse_lnk(lnk_path: str) -> Dict[str, str]:
    """Публичная оболочка для парсинга .lnk файлов.

    Стабильный API для внешних модулей. Делегирует приватной реализации
    `_parse_lnk`, позволяя в будущем менять внутренности без влияния на клиентов.
    """
    return _parse_lnk(lnk_path)


def _get_name_for_link_type(link_type: str, path: str, lnk_info: Dict[str, str]) -> str:
    """Определяет имя для ссылки в зависимости от типа"""
    if not path:
        return "Unknown"
    try:
        if link_type == "chromeapp":
            return Path(path).stem
        elif link_type == "program":
            target_path = lnk_info.get("path") if lnk_info else path
            return Path(target_path).stem if target_path else Path(path).stem
        elif link_type == "folder":
            return os.path.basename(os.path.normpath(path))
        elif link_type == "file":
            return Path(path).stem
        else:
            return Path(path).stem
    except Exception as e:
        logger.error("Error getting name for %s, path %s: %s", link_type, path, e)
        return "Unknown"


def _handle_folder_icon(config) -> str:
    """Обрабатывает иконку для папки через централизованный резолвер."""
    try:
        resolved = resolve_icon_for_link({"type": "folder", "icon_path": ""})
        if resolved and os.path.exists(resolved):
            return resolved
    except Exception as e:
        logger.debug("folder icon resolve failed, fallback: %s", e)
    return _get_default_icon("folder", config)


def _handle_chromeapp_icon(lnk_info: Dict[str, str], icons_dir: str) -> Optional[str]:
    """Обрабатывает иконку для Chrome-приложения"""
    args = lnk_info.get("args", "")
    if not args:
        return None
    app_id_match = re.search(r"--app-id=([a-z0-9]{32})", args)
    if not app_id_match:
        return None
    app_id = app_id_match.group(1)
    icon_dst = os.path.join(icons_dir, f"chromeapp_{app_id}.png")
    if is_valid_icon_file(icon_dst):
        logger.debug("Using cached chromeapp icon: %s", icon_dst)
        return icon_dst
    icon_src = lnk_info.get("icon_path")
    if icon_src and os.path.exists(icon_src):
        try:
            os.makedirs(os.path.dirname(icon_dst), exist_ok=True)
            shutil.copyfile(icon_src, icon_dst)
            if is_valid_icon_file(icon_dst):
                logger.debug("Copied chromeapp icon: %s", icon_dst)
                return icon_dst
        except OSError as e:
            logger.error("Failed to copy chromeapp icon: %s", e)
    return None


def _handle_program_icon(
    path: str, lnk_info: Dict[str, str], icons_dir: str
) -> Optional[str]:
    """Обрабатывает иконку для программы"""
    target_path = lnk_info.get("path") if lnk_info else path
    if target_path and target_path.lower().endswith(".exe"):
        return _extract_icon_from_exe(target_path, icons_dir)
    return None


def _handle_file_icon(path: str, icons_dir: str) -> Optional[str]:
    """Обрабатывает иконку для файла"""
    if not path:
        return None
    try:
        ext = Path(path).suffix.lower().replace(".", "")
        if not ext:
            return None
        icon_path = os.path.join(icons_dir, f"file_{ext}.png")
        if is_valid_icon_file(icon_path):
            return icon_path
        os.makedirs(os.path.dirname(icon_path), exist_ok=True)
        provider = _get_icon_provider()
        q_icon = provider.icon(QFileInfo(path))
        if not q_icon.isNull():
            pixmap = q_icon.pixmap(256, 256)
            if pixmap.save(icon_path, "PNG"):
                logger.debug("Extracted file icon: %s", icon_path)
                return icon_path
    except Exception as e:
        logger.error("Failed to extract file icon for %s: %s", path, e)
    return None


def _get_icon_for_link_type(
    link_type: str, path: str, lnk_info: Dict[str, str], config, icons_dir: str
) -> str:
    """Определяет иконку для ссылки в зависимости от типа"""
    icon = None
    try:
        if link_type == "folder":
            icon = _handle_folder_icon(config)
        elif link_type == "chromeapp":
            icon = _handle_chromeapp_icon(lnk_info, icons_dir)
        elif link_type == "program":
            icon = _handle_program_icon(path, lnk_info, icons_dir)
        elif link_type == "file":
            icon = _handle_file_icon(path, icons_dir)
    except Exception as e:
        logger.error("Error getting icon for %s, path %s: %s", link_type, path, e)
    if not is_valid_icon_file(icon):
        icon = _get_default_icon(link_type, config)
        logger.debug("Fallback to default icon: %s", icon)
    return icon or ""


def parse_local_link(
    link_type: str, path: str, config, args: str = None
) -> Dict[str, str]:
    """Парсит локальную ссылку и возвращает информацию о ней, включая имя и иконку."""
    if not validate_link_type(link_type):
        logger.error("Invalid link_type: %r", link_type)
        return {"name": "Error", "icon": ""}
    if not validate_path(path):
        logger.error("Invalid path: %r", path)
        return {"name": "Error", "icon": ""}
    if not validate_config_for_icons(config):
        logger.error("Config.LINK_ICONS_DIR не найден")
        return None
    icons_dir = str(icon_path_service.get_user_icons_dir())
    lnk_info = {}
    if path.lower().endswith(".lnk"):
        lnk_info = _parse_lnk(path)
    name = _get_name_for_link_type(link_type, path, lnk_info)
    icon = _get_icon_for_link_type(link_type, path, lnk_info, config, icons_dir)
    result = {"name": name, "icon": icon}
    logger.debug("parse_local_link result: %s", result)
    return result
