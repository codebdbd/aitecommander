"""Primary entry point that wires together specialized configuration modules."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .limits_config import LimitsConfig
from .path_config import PathConfig
from .settings_config import SettingsConfig
from .ui_config import UIConfig
from .utils import get_by_path


class AppConfig:
    """Access application configuration backed by a JSON file."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the loader and read the configuration payload."""
        if config_path is None:
            config_path = Path(__file__).parent / "app_config.json"
        self._config_path = Path(config_path)
        self._config = self._load_config()

        # Initialize specialized configuration facades
        self.ui = UIConfig(self._config)
        self.paths = PathConfig(self._config)
        self.limits = LimitsConfig(self._config)
        self.settings = SettingsConfig(self._config)

    def __getattr__(self, name: str):
        """Delegate missing attributes to sub-configurations.

        Lookup order: UI -> paths -> limits -> settings. Returns the attribute
        (method or property) of the first configuration object that defines it.
        Falls back to :class:`AttributeError` when nothing matches. This removes
        redundant getters while keeping backwards compatibility for legacy code
        that expects ``app_config.<method>()`` delegates to sub-configs.
        """
        for sub in (self.ui, self.paths, self.limits, self.settings):
            if hasattr(sub, name):
                return getattr(sub, name)
        raise AttributeError(f"{self.__class__.__name__!s} has no attribute {name!r}")

    def __dir__(self):
        """Expose attributes from sub-configurations for improved IDE support."""
        base = set(super().__dir__())
        for sub in (self.ui, self.paths, self.limits, self.settings):
            base.update(dir(sub))
        return sorted(base)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from a JSON file."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Файл конфигурации не найден: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Return a value from the raw configuration via dotted key path."""
        return get_by_path(self._config, key_path, default)

    def get_full_config(self) -> Dict[str, Any]:
        """Return the complete configuration dictionary copy."""
        return self._config.copy()

    def get_ui_icons_path(self) -> str:
        """Return the path to UI icons as a string."""
        return str(self.paths.get_ui_icons_dir())

    # Former get_* proxies were removed. Requests are delegated through
    # ``__getattr__`` to ``ui``/``paths``/``limits``/``settings`` configurations.
