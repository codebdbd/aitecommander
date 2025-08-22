"""
Базовый класс для всех Chromium-based браузеров (Chrome, Edge, Brave, Vivaldi и т.д.).
"""

import json
import logging
import os
from typing import Dict, List, Optional

from .base_profile_finder import BaseBrowserProfileFinder

logger = logging.getLogger(__name__)


def detect_chrome_profiles_dir():
    """Возвращает путь к профилям Chrome для текущей ОС или None, если не найдено."""
    candidates = []
    if os.name == "nt":
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
    elif os.name == "posix" and os.uname().sysname == "Darwin":
        candidates.append(os.path.expanduser("~/Library/Application Support/Google/Chrome"))
    elif os.name == "posix" and os.uname().sysname == "Linux":
        candidates.append(os.path.expanduser("~/.config/google-chrome"))
        candidates.append(os.path.expanduser("~/.config/chromium"))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class ChromiumBaseBrowserFinder(BaseBrowserProfileFinder):
    """Базовый класс для всех Chromium-based браузеров."""
    
    def __init__(self, profiles_dir: str, browser_name: str):
        """
        Инициализация finder'а для Chromium-based браузера.
        
        Args:
            profiles_dir: Путь к папке с профилями браузера
            browser_name: Читаемое имя браузера
        """
        self.profiles_dir = profiles_dir
        self.browser_name = browser_name
    
    def find_profiles(self) -> List[Dict[str, str]]:
        """Универсальная логика поиска профилей для Chromium-based браузеров."""
        profiles = []
        
        if not os.path.exists(self.profiles_dir):
            logger.debug(f"Папка профилей {self.browser_name} не найдена: {self.profiles_dir}")
            return profiles
        
        logger.debug(f"find_profiles: profiles_dir={self.profiles_dir}")
        
        try:
            for entry in os.listdir(self.profiles_dir):
                profile_path = os.path.join(self.profiles_dir, entry)
                if os.path.isdir(profile_path) and (entry.startswith("Profile") or entry == "Default"):
                    email = self._extract_email_from_preferences(profile_path)
                    if email:
                        profiles.append({
                            "email": email,
                            "name": entry,
                            "directory": entry,
                            "path": profile_path,
                            "args": f'--profile-directory="{entry}"'
                        })
                        logger.debug(f"Найден профиль {self.browser_name}: {email} ({entry})")
        except Exception as e:
            logger.error(f"Ошибка при поиске профилей {self.browser_name}: {e}")
        
        logger.info(f"Найдено {len(profiles)} профилей {self.browser_name}")
        return profiles
    
    def _extract_email_from_preferences(self, profile_path: str) -> Optional[str]:
        """Извлекает email из Preferences файла."""
        pref_path = os.path.join(profile_path, "Preferences")
        if not os.path.exists(pref_path):
            return None
        
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            
            # Пробуем разные места где может быть email
            email = None
            
            # Основные места поиска email
            account_info = prefs.get("account_info", [])
            if account_info and isinstance(account_info, list) and len(account_info) > 0:
                email = account_info[0].get("email")
            
            if not email:
                gaia_info = prefs.get("gaia_info", {})
                email = gaia_info.get("email")
            
            if not email:
                profile_info = prefs.get("profile", {}).get("info_cache", {})
                if profile_info:
                    # info_cache может содержать несколько профилей
                    for profile_id, profile_data in profile_info.items():
                        if isinstance(profile_data, dict) and profile_data.get("user_name"):
                            email = profile_data["user_name"]
                            break
            
            return email
        except Exception as e:
            logger.debug(f"Не удалось извлечь email из {pref_path}: {e}")
            return None
    
    def get_browser_name(self) -> str:
        """Возвращает читаемое имя браузера.
        NOTE: Намеренное дублирование с другими профайл-файдерами для единообразия API
        и локальной читаемости. Вынос в общий helper нецелесообразен.
        """
        return self.browser_name
    
    def get_profile_argument(self, profile_data: Dict) -> str:
        """Генерирует аргумент командной строки для профиля."""
        directory = profile_data.get("directory", profile_data.get("name", "Default"))
        return f'--profile-directory="{directory}"'
    
    def parse_profile_from_args(self, args: str) -> Optional[Dict]:
        """Парсит профиль из аргументов командной строки."""
        logger.debug(f"parse_profile_from_args: args={args}")
        
        if not args or '--profile-directory' not in args:
            logger.debug("parse_profile_from_args: no --profile-directory in args")
            return None
        
        try:
            import re
            match = re.search(r'--profile-directory="([^"]+)"', args)
            if match:
                directory = match.group(1)
                logger.debug(f"parse_profile_from_args: found directory={directory}")
                result = {
                    "directory": directory,
                    "name": directory,
                    "email": f"{directory} ({self.browser_name})",
                    "args": args,
                    "path": os.path.join(self.profiles_dir, directory) if self.profiles_dir else None
                }
                logger.debug(f"parse_profile_from_args: returning result={result}")
                return result
        except Exception as e:
            logger.debug(f"Ошибка парсинга аргументов {self.browser_name}: {e}")
        
        logger.debug("parse_profile_from_args: could not parse profile")
        return None


# Конкретные реализации для каждого браузера
class EdgeProfileFinder(ChromiumBaseBrowserFinder):
    """Finder для Microsoft Edge профилей."""
    
    def __init__(self):
        from app.config_data import app_config
        super().__init__(app_config.get_edge_profiles_dir(), "Microsoft Edge")


class BraveProfileFinder(ChromiumBaseBrowserFinder):
    """Finder для Brave Browser профилей."""
    
    def __init__(self):
        from app.config_data import app_config
        super().__init__(app_config.get_brave_profiles_dir(), "Brave")


class VivaldiProfileFinder(ChromiumBaseBrowserFinder):
    """Finder для Vivaldi Browser профилей."""
    
    def __init__(self):
        from app.config_data import app_config
        super().__init__(app_config.get_vivaldi_profiles_dir(), "Vivaldi")


class OperaProfileFinder(ChromiumBaseBrowserFinder):
    """Finder для Opera Browser профилей."""
    
    def __init__(self):
        from app.config_data import app_config
        super().__init__(app_config.get_opera_profiles_dir(), "Opera")


class YandexProfileFinder(ChromiumBaseBrowserFinder):
    """Finder для Yandex Browser профилей."""
    
    def __init__(self):
        from app.config_data import app_config
        super().__init__(app_config.get_yandex_profiles_dir(), "Yandex Browser")


class ChromeProfileFinder(ChromiumBaseBrowserFinder):
    """Finder для Google Chrome профилей."""
    
    def __init__(self):
        from app.config_data import app_config
        super().__init__(app_config.get_chrome_profiles_dir(), "Google Chrome")
