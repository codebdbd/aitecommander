"""
Главный загрузчик конфигурации приложения.
Объединяет все специализированные конфигурационные модули.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .limits_config import LimitsConfig
from .path_config import PathConfig
from .settings_config import SettingsConfig
from .ui_config import UIConfig
from .utils import get_by_path


class AppConfig:
    """Управление конфигурацией приложения из JSON файла."""

    def __init__(self, config_path: Optional[str] = None):
        """Инициализация загрузчика конфигурации."""
        if config_path is None:
            config_path = Path(__file__).parent / "app_config.json"
        self._config_path = Path(config_path)
        self._config = self._load_config()

        # Инициализация специализированных конфигураций
        self.ui = UIConfig(self._config)
        self.paths = PathConfig(self._config)
        self.limits = LimitsConfig(self._config)
        self.settings = SettingsConfig(self._config)

    # Карта обратной совместимости: старое_имя -> новое_имя.
    # Заполняется по мере переименований. Оставляем пустой по умолчанию.
    _COMPAT_MAP: dict[str, str] = {}

    def __getattr__(self, name: str):
        """Делегирование отсутствующих атрибутов/методов к подконфигурациям.

        Порядок поиска: `ui`, `paths`, `limits`, `settings`.

        Также поддерживает карту обратной совместимости `_COMPAT_MAP`,
        позволяющую прозрачно перенаправлять вызовы переименованных методов.
        """
        # Поддержка переименований: подменяем имя, если присутствует в маппинге
        mapped_name = self._COMPAT_MAP.get(name, name)

        for section in ("ui", "paths", "limits", "settings"):
            obj = getattr(self, section, None)
            if obj is not None and hasattr(obj, mapped_name):
                return getattr(obj, mapped_name)

        # Если ни в одной секции не найдено — стандартное поведение
        raise AttributeError(f"{self.__class__.__name__!s} has no attribute '{name}'")

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из JSON файла."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Файл конфигурации не найден: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Получение значения из конфигурации по пути к ключу."""
        return get_by_path(self._config, key_path, default)

    def get_full_config(self) -> Dict[str, Any]:
        """Получение полной конфигурации."""
        return self._config.copy()

    # === МЕТОДЫ ОБРАТНОЙ СОВМЕСТИМОСТИ ===
    # Все старые методы делегируются к соответствующим модулям

    # === Пути ===

    def get_ui_icons_path(self) -> str:
        """Возвращает путь к UI-иконкам как строку."""
        return str(self.paths.get_ui_icons_dir())

    def get_chrome_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Chrome."""
        p = self.paths.get_chrome_profiles_dir()
        return str(p) if p else None

    def get_firefox_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Firefox."""
        p = self.paths.get_firefox_profiles_dir()
        return str(p) if p else None

    def get_edge_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Edge."""
        p = self.paths.get_edge_profiles_dir()
        return str(p) if p else None

    def get_brave_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Brave."""
        p = self.paths.get_brave_profiles_dir()
        return str(p) if p else None

    def get_vivaldi_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Vivaldi."""
        p = self.paths.get_vivaldi_profiles_dir()
        return str(p) if p else None

    def get_opera_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Opera."""
        p = self.paths.get_opera_profiles_dir()
        return str(p) if p else None

    def get_yandex_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Yandex."""
        p = self.paths.get_yandex_profiles_dir()
        return str(p) if p else None

    # === Лимиты / Настройки ===
    # Удалены простые делегаторы — теперь используются напрямую через __getattr__
