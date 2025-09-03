"""
Firefox Profile Finder - поиск профилей Mozilla Firefox.
"""

import configparser
import logging
import os
import re
from typing import Dict, List, Optional

from .base_profile_finder import BaseBrowserProfileFinder

logger = logging.getLogger(__name__)


class FirefoxProfileFinder(BaseBrowserProfileFinder):
    """Finder для Mozilla Firefox профилей."""

    def __init__(self):
        from app.config_data import app_config

        dir_path = app_config.paths.get_browser_profiles_dir("firefox")
        self.profiles_dir = str(dir_path) if dir_path else ""
        self.browser_name = "Mozilla Firefox"

    def find_profiles(self) -> List[Dict[str, str]]:
        """Находит профили Firefox из profiles.ini."""
        profiles = []
        profiles_ini = os.path.join(self.profiles_dir, "profiles.ini")

        if not os.path.exists(profiles_ini):
            logger.debug(f"Файл profiles.ini не найден: {profiles_ini}")
            return profiles

        try:
            config = configparser.ConfigParser()
            config.read(profiles_ini, encoding="utf-8")

            for section_name in config.sections():
                if section_name.startswith("Profile"):
                    section = config[section_name]
                    name = section.get("Name", "Default")
                    path = section.get("Path", "")
                    is_relative = section.getboolean("IsRelative", True)

                    if is_relative:
                        full_path = os.path.join(self.profiles_dir, path)
                    else:
                        full_path = path

                    if os.path.exists(full_path):
                        # Попытка получить дополнительную информацию из prefs.js
                        email = self._extract_email_from_prefs(full_path)

                        profiles.append(
                            {
                                "name": name,
                                "email": email or name,
                                "path": full_path,
                                "directory": path,
                                "args": f'-P "{name}"',
                            }
                        )
                        logger.debug(
                            f"Найден профиль Firefox: {name} ({email or 'без email'})"
                        )
        except Exception as e:
            logger.error(f"Ошибка при чтении профилей Firefox: {e}")

        logger.info(f"Найдено {len(profiles)} профилей Firefox")
        return profiles

    def _extract_email_from_prefs(self, profile_path: str) -> Optional[str]:
        """Извлекает email из prefs.js Firefox профиля."""
        prefs_file = os.path.join(profile_path, "prefs.js")
        if not os.path.exists(prefs_file):
            return None

        try:
            with open(prefs_file, "r", encoding="utf-8") as f:
                content = f.read()

                # Ищем настройки почты или синхронизации
                email_patterns = [
                    r'user_pref\("services\.sync\.username",\s*"([^"]+)"\)',
                    r'user_pref\("mail\.identity\.default\.useremail",\s*"([^"]+)"\)',
                    r'user_pref\("identity\.fxaccounts\.account\.device\.name",\s*"([^"]+)"\)',
                ]

                for pattern in email_patterns:
                    match = re.search(pattern, content)
                    if match:
                        email = match.group(1)
                        # Проверяем что это похоже на email
                        if "@" in email and "." in email:
                            return email
        except Exception as e:
            logger.debug(f"Не удалось извлечь email из {prefs_file}: {e}")

        return None

    def get_browser_name(self) -> str:
        """Возвращает читаемое имя браузера.
        NOTE: Намеренное дублирование с другими профайл-файдерами для единообразия API
        и локальной читаемости. Вынос в общий helper нецелесообразен.
        """
        return self.browser_name

    def get_profile_argument(self, profile_data: Dict) -> str:
        """Генерирует аргумент командной строки для профиля."""
        profile_name = profile_data.get("name", "default")
        return f'-P "{profile_name}"'

    def parse_profile_from_args(self, args: str) -> Optional[Dict]:
        """Парсит профиль Firefox из аргументов командной строки."""
        logger.debug(f"parse_profile_from_args: args={args}")

        if not args or "-P " not in args:
            logger.debug("parse_profile_from_args: no -P in args")
            return None

        try:
            # Извлекаем имя профиля из -P "ProfileName"
            match = re.search(r'-P\s+"([^"]+)"', args)
            if match:
                profile_name = match.group(1)
                logger.debug(
                    f"parse_profile_from_args: found profile_name={profile_name}"
                )
                result = {
                    "name": profile_name,
                    "email": f"{profile_name} (Firefox)",
                    "args": args,
                    "directory": profile_name,
                    "path": None,  # Путь определяется динамически из profiles.ini
                }
                logger.debug(f"parse_profile_from_args: returning result={result}")
                return result
        except Exception as e:
            logger.debug(f"Ошибка парсинга аргументов Firefox: {e}")

        logger.debug("parse_profile_from_args: could not parse profile")
        return None
