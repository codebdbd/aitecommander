"""
Главный загрузчик конфигурации приложения.
Объединяет все специализированные конфигурационные модули.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .limits_config import LimitsConfig
from .path_config import PathConfig
from .settings_config import SettingsConfig
from .ui_config import UIConfig
from .utils import get_by_path


class AppConfig:
    """Управление конфигурацией приложения из JSON файла."""

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """Инициализация загрузчика конфигурации."""
        cfg_path: Path
        if config_path is None:
            cfg_path = Path(__file__).parent / "app_config.json"
        else:
            cfg_path = Path(config_path)
        self._config_path = cfg_path
        self._config = self._load_config()

        # Инициализация специализированных конфигураций
        self.ui = UIConfig(self._config)
        self.paths = PathConfig(self._config)
        self.limits = LimitsConfig(self._config)
        self.settings = SettingsConfig(self._config)

    def __getattr__(self, name: str):
        """Делегирование неизвестных атрибутов к подконфигурациям.

        Порядок: ui -> paths -> limits -> settings.
        Возвращает найденный атрибут (метод или свойство) соответствующего
        объекта подконфигурации. Если атрибут не найден ни в одном из них,
        возбуждается AttributeError как обычно.

        Это позволяет убрать дублирующие геттеры уровня AppConfig, сохраняя
        обратную совместимость: существующие методы остаются и работают, а
        новые обращения могут вызываться напрямую через app_config.<method>.
        """
        for sub in (self.ui, self.paths, self.limits, self.settings):
            if hasattr(sub, name):
                return getattr(sub, name)
        raise AttributeError(f"{self.__class__.__name__!s} has no attribute {name!r}")

    def __dir__(self):
        """Расширяет dir() за счет атрибутов подконфигураций для удобства IDE."""
        base = set(super().__dir__())
        for sub in (self.ui, self.paths, self.limits, self.settings):
            base.update(dir(sub))
        return sorted(base)

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

    def get_ui_icons_path(self) -> str:
        """Возвращает путь к UI-иконкам как строку."""
        return str(self.paths.get_ui_icons_dir())

    # Часть прежних get_* удалена как чистые прокси. Доступ к ним делегируется
    # через __getattr__ напрямую в ui/paths/limits/settings.
