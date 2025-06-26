import os
import logging
import re
import shutil
import time
import pythoncom
import win32com.client
import win32api
import win32con
import win32ui
import win32gui
from pathlib import Path
from urllib.parse import urlparse, urljoin
from typing import Optional, Dict
from collections import OrderedDict
from app.utils.web_favicon import get_web_favicon, make_http_request
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def parse_webpage_title(html_content: str, url: str) -> str:
    """Извлекает заголовок или мета-теги из HTML-страницы."""
    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    if title and title.lower() not in ["just a moment...", "checking your browser..."]:
        logging.info(f"[parse_webpage_title] title='{title}' url={url}")
        return title

    meta_og_title = soup.find("meta", property="og:title")
    if meta_og_title and meta_og_title.get("content"):
        logging.info(f"[parse_webpage_title] og:title='{meta_og_title['content']}' url={url}")
        return meta_og_title["content"].strip()

    meta_tw_title = soup.find("meta", attrs={"name": "twitter:title"})
    if meta_tw_title and meta_tw_title.get("content"):
        logging.info(f"[parse_webpage_title] twitter:title='{meta_tw_title['content']}' url={url}")
        return meta_tw_title["content"].strip()

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        logging.info(f"[parse_webpage_title] description='{meta_desc['content']}' url={url}")
        return meta_desc["content"].strip()

    meta_og_desc = soup.find("meta", property="og:description")
    if meta_og_desc and meta_og_desc.get("content"):
        logging.info(f"[parse_webpage_title] og:description='{meta_og_desc['content']}' url={url}")
        return meta_og_desc["content"].strip()

    meta_tw_desc = soup.find("meta", attrs={"name": "twitter:description"})
    if meta_tw_desc and meta_tw_desc.get("content"):
        logging.info(f"[parse_webpage_title] twitter:description='{meta_tw_desc['content']}' url={url}")
        return meta_tw_desc["content"].strip()

    h1 = soup.find("h1")
    if h1 and h1.text.strip():
        logging.info(f"[parse_webpage_title] h1='{h1.text.strip()}' url={url}")
        return h1.text.strip()

    logging.warning(f"[parse_webpage_title] fallback to domain url={url}")
    return urlparse(url).netloc or url

from PIL import Image, UnidentifiedImageError
from PyQt6.QtWidgets import QFileIconProvider
from PyQt6.QtCore import QFileInfo
from win32com.shell import shell

# Константы
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
CACHE_MAX_SIZE = 1000
CACHE_TTL = 7 * 24 * 3600  # 7 дней
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_TIMEOUT = 10

# Кэш favicon
_favicon_cache = OrderedDict()

def get_default_icon(icon_type: str, config=None) -> str:
    """Возвращает путь к дефолтной иконке по типу."""
    if config and hasattr(config, 'DEFAULT_ICONS'):
        return config.DEFAULT_ICONS.get(icon_type, config.DEFAULT_ICONS.get('default', 'default.ico'))
    return 'default.ico'

def is_valid_icon_file(path: str) -> bool:
    """Проверяет корректность файла иконки."""
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) > MAX_IMAGE_SIZE:
        logging.warning(f"[is_valid_icon_file] File too large: {path}")
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except UnidentifiedImageError:
        logging.warning(f"[is_valid_icon_file] Invalid image format: {path}")
        return False
    except Exception as e:
        logging.error(f"[is_valid_icon_file] Error validating icon: {e}, path={path}")
        return False

def clean_cache():
    """Очищает старые записи из кэша favicon."""
    while len(_favicon_cache) > CACHE_MAX_SIZE:
        _favicon_cache.popitem(last=False)



def extract_link_info(link_type: str, path: str, config=None) -> dict:
    """Универсальная функция: возвращает name, icon для любой ссылки."""
    return {
        "name": get_name_for_link(link_type, path),
        "icon": get_icon_for_link(link_type, path, config),
    }

def get_name_for_link(link_type: str, path: str) -> str:
    """Возвращает имя для ссылки в зависимости от её типа."""
    if not path:
        return ""

    if link_type == "web":
        url = path
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        response = make_http_request(url)
        if response:
            response.encoding = "utf-8"
            return parse_webpage_title(response.text, url)
        return urlparse(url).netloc or url

    if link_type == "chromeapp" and path.lower().endswith('.lnk'):
        try:
            info = parse_chrome_shortcut(path)
            return info.get("name", "")
        except (OSError, pythoncom.com_error) as e:
            logging.error(f"[get_name_for_link] Chrome shortcut parse failed: {e}, path={path}")
            return ""

    if link_type == "program":
        if path.lower().endswith('.lnk'):
            try:
                info = parse_chrome_shortcut(path)
                return info.get("name", "")
            except (OSError, pythoncom.com_error) as e:
                logging.error(f"[get_name_for_link] Program shortcut parse failed: {e}, path={path}")
                return ""
        base = os.path.basename(path)
        name, _ = os.path.splitext(base)
        return name

    if link_type in ("script", "batch"):
        base = os.path.basename(os.path.dirname(path) if link_type == "script" else path)
        name, _ = os.path.splitext(base)
        return name

    if link_type == "folder":
        result = os.path.basename(os.path.normpath(path))
        print("[DEBUG] get_name_for_link input:", path, "output:", result)
        return result

    if link_type == "file":
        return os.path.basename(path)

    return ""

def get_icon_for_link(link_type: str, path: str, config=None, args: str = None) -> str:
    """Возвращает путь к иконке в зависимости от типа ссылки."""
    logging.debug(f"[get_icon_for_link] link_type={link_type}, path={path}")

    if not config:
        return get_default_icon('default')

    if link_type == "folder":
        # Всегда возвращаем абсолютный путь к folder_icon.png
        if config and hasattr(config, 'UI_ICONS_DIR'):
            return str(config.UI_ICONS_DIR / "folder_icon.png")
        return "folder_icon.png"

    if link_type == "script":
        return get_default_icon('script', config)

    if link_type == "batch":
        return get_default_icon('batch', config)

    if link_type == "chromeapp":
        app_id = None
        if args is None and isinstance(path, dict):
            args = path.get("args", "")
            path = path.get("path", "")
        if args:
            m = re.search(r'--app-id=([a-z0-9]{32})', args)
            if m:
                app_id = m.group(1)
        if not app_id:
            logging.warning(f"[get_icon_for_link] No app-id for chromeapp, path={path}")
            return get_default_icon('chrome', config)
        icon_dst = os.path.join(config.LINK_ICONS_DIR, f"chromeapp_{app_id}.ico")
        if os.path.exists(icon_dst) and is_valid_icon_file(icon_dst):
            return icon_dst
        try:
            info = parse_chrome_shortcut(path)
            icon_path = info.get("icon_path")
            if icon_path and os.path.exists(icon_path):
                shutil.copyfile(icon_path, icon_dst)
                logging.info(f"[get_icon_for_link] Copied chromeapp icon to {icon_dst}")
                return icon_dst
        except (OSError, pythoncom.com_error) as e:
            logging.error(f"[get_icon_for_link] Chrome shortcut parse failed: {e}, path={path}")
        return get_default_icon('chrome', config)

    if link_type == "web" and path.startswith(("http://", "https://")):
        return get_web_favicon(path, config)

    if link_type == "program":
        exe_path = path
        if exe_path and os.path.exists(exe_path):
            icon_path = extract_icon_from_exe(exe_path)
            if icon_path and is_valid_icon_file(icon_path):
                return icon_path
        return get_default_icon('program', config)

    if link_type == "file":
        ext = os.path.splitext(path)[1].lower()
        ext_name = ext[1:] if ext.startswith('.') else ext
        if not ext_name:
            return get_default_icon('file', config)
        icon_path = os.path.join(config.LINK_ICONS_DIR, f"{ext_name}.ico")
        if not os.path.exists(icon_path) and os.path.exists(path):
            try:
                provider = QFileIconProvider()
                file_info = QFileInfo(path)
                icon = provider.icon(file_info)
                if not icon.isNull():
                    icon.pixmap(256, 256).save(icon_path, "ICO")
            except RuntimeError as e:
                logging.error(f"[get_icon_for_link] Icon extraction failed: {e}, path={path}")
        if os.path.exists(icon_path) and is_valid_icon_file(icon_path):
            return icon_path
        return get_default_icon('file', config)

    if path.lower().endswith(".lnk"):
        try:
            info = parse_program_shortcut(path)
            exe_path = info.get("path")
            if exe_path and os.path.exists(exe_path) and not exe_path.startswith(("http://", "https://")):
                icon_path = extract_icon_from_exe(exe_path)
                if icon_path and is_valid_icon_file(icon_path):
                    return icon_path
        except (OSError, pythoncom.com_error) as e:
            logging.error(f"[get_icon_for_link] Shortcut parse failed: {e}, path={path}")
        return get_default_icon('default', config)

    logging.warning(f"[get_icon_for_link] Unknown link_type={link_type}, path={path}")
    return get_default_icon('default', config)

def extract_icon_from_exe(exe_path: str, icon_index: int = 0, save_path: str = None) -> Optional[str]:
    """Извлекает иконку из exe/dll и сохраняет в ICO-файл."""
    if not save_path:
        save_path = os.path.join(
            os.path.dirname(exe_path),
            f"{os.path.splitext(os.path.basename(exe_path))[0]}.ico"
        )
    try:
        large, small = win32gui.ExtractIconEx(exe_path, icon_index)
        if not large:
            return None
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_x)
        hdc_compat = hdc.CreateCompatibleDC()
        hdc_compat.SelectObject(hbmp)
        win32gui.DrawIconEx(hdc_compat.GetSafeHdc(), 0, 0, large[0], ico_x, ico_x, 0, None, win32con.DI_NORMAL)
        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)
        img.save(save_path, format='ICO')
        return save_path
    except (win32ui.error, OSError) as e:
        logging.error(f"[extract_icon_from_exe] Failed: {e}, path={exe_path}")
        return None
    finally:
        for hicon in large + small:
            win32gui.DestroyIcon(hicon)
        if 'hdc_compat' in locals():
            hdc_compat.DeleteDC()
        if 'hdc' in locals():
            hdc.DeleteDC()

def parse_program_shortcut(lnk_path: str, icons_dir: str = None) -> dict:
    """Парсит ярлык (.lnk) и возвращает информацию о нём."""
    if not os.path.exists(lnk_path) or not lnk_path.lower().endswith('.lnk'):
        return {}
    try:
        pythoncom.CoInitialize()
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )
        persist_file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
        persist_file.Load(lnk_path)
        path, _ = shortcut.GetPath(shell.SLGP_UNCPRIORITY)
        arguments = shortcut.GetArguments()
        icon_path, icon_index = shortcut.GetIconLocation()
        result_icon = icon_path
        if icons_dir and icon_path:
            base_name = os.path.splitext(os.path.basename(path))[0] or 'program_icon'
            ext = os.path.splitext(icon_path)[1] or '.ico'
            dst_icon = os.path.join(icons_dir, f"{base_name}{ext}")
            if os.path.exists(icon_path):
                shutil.copyfile(icon_path, dst_icon)
                result_icon = dst_icon
            elif path.lower().endswith('.exe'):
                extract_icon_from_exe(path, 0, dst_icon)
                if os.path.exists(dst_icon):
                    result_icon = dst_icon
        return {
            "path": path,
            "args": arguments,
            "icon_path": result_icon
        }
    except pythoncom.com_error as e:
        logging.error(f"[parse_program_shortcut] COM error: {e}, path={lnk_path}")
        return {}
    finally:
        pythoncom.CoUninitialize()

def parse_chrome_shortcut(lnk_path: str) -> Dict[str, str]:
    """Парсит ярлык Chrome и возвращает информацию о нём."""
    try:
        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch('WScript.Shell')
        shortcut = shell.CreateShortcut(lnk_path)
        target = shortcut.TargetPath
        args = shortcut.Arguments
        icon_path = shortcut.IconLocation.split(",")[0] if shortcut.IconLocation else ""
        name = Path(lnk_path).stem
        app_id = None
        m = re.search(r'--app-id=([a-z0-9]{32})', args)
        if m:
            app_id = m.group(1)
        return {
            "name": name,
            "target": target,
            "args": args,
            "app_id": app_id,
            "icon_path": icon_path,
            "lnk_path": lnk_path
        }
    except (pythoncom.com_error, OSError) as e:
        logging.error(f"[parse_chrome_shortcut] Failed: {e}, path={lnk_path}")
        return {}
    finally:
        pythoncom.CoUninitialize()

def extract_icon_from_shortcut(lnk_info: dict, icons_dir: str) -> Optional[str]:
    """Извлекает иконку из информации о ярлыке."""
    app_id = lnk_info.get("app_id")
    icon_src = lnk_info.get("icon_path")
    if not app_id or not icon_src:
        return None
    icon_dst = os.path.join(icons_dir, f"chromeapp_{app_id}.ico")
    if os.path.exists(icon_dst) and is_valid_icon_file(icon_dst):
        return icon_dst
    try:
        if os.path.exists(icon_src):
            shutil.copyfile(icon_src, icon_dst)
            if is_valid_icon_file(icon_dst):
                return icon_dst
    except OSError as e:
        logging.error(f"[extract_icon_from_shortcut] Failed: {e}, src={icon_src}")
    return None

def to_relative_icon_path(path: str, config=None) -> str:
    """Преобразует абсолютный путь к иконке в относительный."""
    if not path:
        return path
    base_dir = config.BASE_PATH if config else os.path.dirname(os.path.abspath(__file__))
    try:
        return os.path.relpath(path, base_dir)
    except ValueError as e:
        logging.error(f"[to_relative_icon_path] Failed: {e}, path={path}")
        return path

def to_absolute_icon_path(path: str, config=None) -> str:
    """Преобразует относительный путь к иконке в абсолютный."""
    if not path:
        return path
    base_dir = config.BASE_PATH if config else os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base_dir, path))

def get_icon_path(icons_dir, icon_name, default='default.ico', config=None) -> str:
    """Возвращает путь к иконке или дефолтный путь."""
    path = os.path.join(icons_dir, icon_name)
    if os.path.exists(path) and is_valid_icon_file(path):
        return path
    default_path = os.path.join(icons_dir, default)
    if os.path.exists(default_path) and is_valid_icon_file(default_path):
        return default_path
    return get_default_icon('default', config)

def get_ui_icon_path(ui_dir, icon_name, config=None) -> str:
    """Возвращает путь к UI-иконке."""
    return get_default_icon(icon_name, config)
