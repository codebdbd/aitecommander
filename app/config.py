import os
from pathlib import Path
from PyQt6.QtCore import QSize

# Метаданные приложения
APP_NAME = "Link Manager"
ORG_NAME = "MyCompany"

# Директория для хранения данных (обычно %APPDATA%/MyCompany/Link Manager)
APP_DIR = Path(os.getenv("APPDATA", Path.cwd())) / ORG_NAME / APP_NAME

# Путь к файлу базы SQLite
DB_PATH = APP_DIR / "links.db"

# Директория для кеша иконок ссылок
LINK_ICONS_DIR = Path(__file__).resolve().parent.parent / "link_icons"

import sys

# Автоопределение директории профилей Chrome

def detect_chrome_profiles_dir():
    """
    Возвращает путь к профилям Chrome для текущей ОС или None, если не найдено.
    """
    candidates = []
    if sys.platform.startswith("win"):
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
    elif sys.platform.startswith("darwin"):
        candidates.append(os.path.expanduser("~/Library/Application Support/Google/Chrome"))
    elif sys.platform.startswith("linux"):
        candidates.append(os.path.expanduser("~/.config/google-chrome"))
        candidates.append(os.path.expanduser("~/.config/chromium"))

    for path in candidates:
        if os.path.exists(path):
            return path
    return None

CHROME_PROFILES_DIR = detect_chrome_profiles_dir()

# Манифест тем оформления
THEMES_MANIFEST = APP_DIR / "themes.json"

# Ресурсы UI: QSS и UI-иконки
QSS_DIR      = Path(__file__).parent / "views" / "resources" / "qss"
UI_ICONS_DIR = Path(__file__).parent / "views" / "resources" / "ui_icons"

# Путь к SQL-схеме
SCHEMA_FILE = Path(__file__).parent / "models" / "schema.sql"

# Размер иконок избранного (по стандарту PyQt)
FAVORITE_ICON_SIZE = QSize(24, 24)

# Иконки по умолчанию
DEFAULT_ICONS = {
    "default": "default.ico",
    "folder": "folder_icon.png",
    "web": "web_icon.png",
    "program": "program_icon.png",
    "script": "script_icon.png",
    "chrome": "chrome_icon.png",
    "chromeapp": "chrome_icon.png",
    "file": "documents_icon.png",
    "category": "category.ico",
    "section": "section.ico",
    "ai": "ai_icon.png",
    "work": "work_icon.png",
    "study": "study_icon.png",
    "personal": "personal_icon.png",
    "cut": "cut.svg",
    "copy": "copy.svg",
    "delete": "delete.svg",
    "edit": "edit.svg",
    "link": "link.svg",
    "favorite": "favorite.svg",
    "notes": "notes.svg",
    "run": "run.svg",
    "sort": "sort.svg",
    "add_category": "add_category.svg",
    "add_link": "add_link.svg",
    "add_section": "add_section.svg",
    "paste": "paste.svg"
}
