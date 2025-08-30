"""
Хранилище кэша профилей браузеров в файловой системе пользователя.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from app.config_data import app_config

logger = logging.getLogger(__name__)


def get_cache_path() -> Path:
    """Возвращает путь к файлу кэша профилей браузеров.

    Файл хранится в config-директории пользователя: browser_profiles.json
    """
    return app_config.paths.get_config_dir() / "browser_profiles.json"


def load_profiles() -> Dict[str, List[dict]]:
    """Загружает профили из JSON-кэша.

    Returns:
        dict: {browser_key: [profiles,...]} либо пустой словарь.
    """
    logger.warning(
        "profile_cache.load_profiles() устарел: используйте PersistentProfileCache вместо прямого чтения файла"
    )
    path = get_cache_path()
    try:
        if not path.exists():
            logger.debug("Кэш профилей отсутствует: %s", path)
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("Некорректный формат файла кэша профилей: %s", type(data))
                return {}
            # Нормализуем значения на случай, если там не списки
            normalized: Dict[str, List[dict]] = {}
            for key, profiles in data.items():
                if isinstance(profiles, list):
                    normalized[key] = profiles
                elif isinstance(profiles, dict):
                    normalized[key] = list(profiles.values())
                else:
                    normalized[key] = []
            logger.info("Загружен кэш профилей: %d браузеров", len(normalized))
            return normalized
    except Exception as e:
        logger.warning("Ошибка чтения кэша профилей %s: %s", path, e)
        return {}


def save_profiles(profiles: Dict[str, List[dict]]) -> bool:
    """Сохраняет профили в JSON-кэш.

    Args:
        profiles: {browser_key: [profiles,...]}
    """
    logger.warning(
        "profile_cache.save_profiles() устарел: используйте PersistentProfileCache для записи и TTL-валидности"
    )
    try:
        # Убедимся, что все пользовательские директории существуют
        try:
            app_config.paths.ensure_user_data_dirs()
        except Exception:
            # Даже если ensure не удался, попробуем создать только config_dir
            app_config.paths.get_config_dir().mkdir(parents=True, exist_ok=True)
        path = get_cache_path()
        # Сериализация
        with path.open("w", encoding="utf-8") as f:
            json.dump(profiles or {}, f, ensure_ascii=False, indent=2)
        logger.info("Сохранён кэш профилей в %s", path)
        return True
    except Exception as e:
        logger.warning("Ошибка сохранения кэша профилей: %s", e)
        return False
