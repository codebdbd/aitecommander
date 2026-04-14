"""Centralized settings persistence for user preferences and app state."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.log_manager import LogManager
from app.core.paths.path_manager import PathManager


class SettingsManager:
    """Static API for settings stored in user app data."""

    _lock = RLock()
    _loaded = False
    _data: dict[str, Any] = {}

    @classmethod
    def _settings_path(cls) -> Path:
        return PathManager.get_app_data_path("settings.json")

    @classmethod
    def load(cls) -> None:
        with cls._lock:
            if cls._loaded:
                return
            path = cls._settings_path()
            if not path.exists():
                cls._data = {}
                cls._loaded = True
                return
            try:
                cls._data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(cls._data, dict):
                    cls._data = {}
            except (OSError, json.JSONDecodeError) as exc:
                cls._safe_log(f"Failed to load settings: {exc}")
                cls._data = {}
            cls._loaded = True

    @classmethod
    def save(cls) -> None:
        with cls._lock:
            path = cls._settings_path()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(cls._data, ensure_ascii=True, indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                cls._safe_log(f"Failed to save settings: {exc}")

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        if not cls._loaded:
            cls.load()
        with cls._lock:
            return cls._data.get(key, default)

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        if not cls._loaded:
            cls.load()
        with cls._lock:
            cls._data[key] = value

    @staticmethod
    def _safe_log(message: str) -> None:
        try:
            LogManager.get_logger("app.settings_manager").warning(message)
        except Exception:
            pass
