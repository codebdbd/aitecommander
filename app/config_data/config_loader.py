"""Primary entry point that wires together specialized configuration modules."""

import json
from pathlib import Path
from typing import Any, Optional

from app.core.paths.path_manager import PathManager

from .limits_config import LimitsConfig
from .path_config import PathConfig
from .settings_config import SettingsConfig
from .ui_config import UIConfig
from .utils import get_by_path

_LEGACY_TABLE_FONT_KEYS = (
    "table_opened_col_px",
    "table_notes_col_px",
    "table_cols_px",
)


def normalize_app_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy configuration shapes once after loading."""
    if not isinstance(config, dict):
        return config

    ui = config.setdefault("ui", {})
    if not isinstance(ui, dict):
        return config

    from app.views.widgets.link.columns import LINK_TABLE_COLUMN_MAP

    current_columns = dict(LINK_TABLE_COLUMN_MAP)
    configured_columns = ui.get("links_table_columns")
    normalized_columns: dict[str, int] | None = None
    if isinstance(configured_columns, dict):
        try:
            normalized_columns = {
                key: int(configured_columns[key]) for key in current_columns
            }
        except (KeyError, TypeError, ValueError):
            normalized_columns = None

    if normalized_columns != current_columns:
        ui["links_table_columns"] = current_columns
    else:
        ui["links_table_columns"] = normalized_columns

    fonts = ui.get("fonts")
    if isinstance(fonts, dict):
        for key in _LEGACY_TABLE_FONT_KEYS:
            fonts.pop(key, None)

    return config


class AppConfig:
    """Access application configuration backed by a JSON file."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the loader and read the configuration payload."""
        if config_path is None:
            self._config_path = PathManager.config_data_root() / "app_config.json"
        else:
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

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from a JSON file."""
        # 1) Try pkgutil (works when bundled with PyInstaller as package data)
        try:
            from pkgutil import get_data

            raw = get_data(__package__, "app_config.json")
            if raw is not None:
                return normalize_app_config(json.loads(raw.decode("utf-8")))
        except Exception:
            pass

        # 2) Try importlib.resources (handles namespace/zip packages)
        try:
            from importlib import resources

            cfg_resource = resources.files(__package__).joinpath("app_config.json")
            with resources.as_file(cfg_resource) as cfg_path:
                with cfg_path.open("r", encoding="utf-8") as handle:
                    return normalize_app_config(json.load(handle))
        except Exception:
            pass

        # 3) Direct filesystem path (development mode)
        try:
            with open(self._config_path, encoding="utf-8") as handle:
                return normalize_app_config(json.load(handle))
        except (FileNotFoundError, PermissionError):
            pass

        # 4) Bundled fallback (PyInstaller one-file or relocated data)
        candidate = PathManager.config_data_root() / "app_config.json"
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                return normalize_app_config(json.load(handle))
        except (FileNotFoundError, PermissionError):
            pass

        # 5) Fallback to in-memory payload as last resort
        try:
            from .app_config_payload import APP_CONFIG_JSON

            return normalize_app_config(json.loads(APP_CONFIG_JSON))
        except Exception as exc:
            raise FileNotFoundError(
                f"Configuration file not found: {self._config_path}"
            ) from exc

    def get(self, key_path: str, default: Any = None) -> Any:
        """Return a value from the raw configuration via dotted key path."""
        return get_by_path(self._config, key_path, default)

    def get_full_config(self) -> dict[str, Any]:
        """Return the complete configuration dictionary copy."""
        return self._config.copy()

    def get_ui_icons_path(self) -> str:
        """Return the path to UI icons as a string."""
        return str(self.paths.get_ui_icons_dir())

    # Former get_* proxies were removed. Requests are delegated through
    # ``__getattr__`` to ``ui``/``paths``/``limits``/``settings`` configurations.
