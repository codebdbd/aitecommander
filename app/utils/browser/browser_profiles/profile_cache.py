"""Кэш профилей браузеров (JSON) в пользовательской директории.

Файл: <user_data_dir>/cache/profiles.json
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.config_data.path_config import PathConfig

logger = logging.getLogger(__name__)


@dataclass
class CacheMeta:
    version: int = 1
    ttl_sec: int = 24 * 60 * 60  # 24 часа по умолчанию


class ProfileCache:
    def __init__(self, ttl_sec: Optional[int] = None) -> None:
        self._cfg = PathConfig()
        self._cache_dir = self._cfg.get_user_data_dir() / "cache"
        self._cache_path = self._cache_dir / "profiles.json"
        self._meta = CacheMeta(ttl_sec=ttl_sec or CacheMeta.ttl_sec)
        # Убедимся, что директория существует
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._cache_path

    def load(self) -> Optional[Dict[str, Any]]:
        """Читает кэш, если он валиден. Возвращает словарь {browser_key: [profiles]} или None."""
        try:
            if not self._cache_path.exists():
                logger.debug("ProfileCache.load: cache file not found")
                return None
            with self._cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not self._is_valid(data):
                logger.info("ProfileCache.load: cache invalid or expired")
                return None
            browsers = data.get("browsers", {})
            # Поддержка альтернативной структуры (список записей)
            if isinstance(browsers, list):
                browsers = {item.get("name") or item.get("key"): item.get("profiles", []) for item in browsers}
            return browsers  # { browser_key: [ {..profile..}, ... ] }
        except Exception as e:
            logger.warning(f"ProfileCache.load: failed to read cache: {e}")
            return None

    def save(self, profiles_by_browser: Dict[str, Any]) -> bool:
        """Сохраняет кэш атомарно. profiles_by_browser: {browser_key: [profiles]}"""
        try:
            payload = {
                "version": self._meta.version,
                "generated_at": int(time.time()),
                "ttl_sec": self._meta.ttl_sec,
                "env": self._env_info(),
                "browsers": profiles_by_browser,
                "source": "scan",
            }
            tmp_path = self._cache_path.with_suffix(".tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._cache_path)
            logger.info("ProfileCache.save: cache saved")
            return True
        except Exception as e:
            logger.warning(f"ProfileCache.save: failed to write cache: {e}")
            # best-effort: cleanup tmp
            try:
                tmp_path = self._cache_path.with_suffix(".tmp")
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass
            return False

    def _is_valid(self, data: Dict[str, Any]) -> bool:
        try:
            if data.get("version") != self._meta.version:
                return False
            gen = int(data.get("generated_at", 0))
            ttl = int(data.get("ttl_sec", self._meta.ttl_sec))
            if gen <= 0:
                return False
            if time.time() - gen > ttl:
                return False
            return True
        except Exception:
            return False

    def _env_info(self) -> Dict[str, Any]:
        try:
            import platform
            from app.config_data import app_config
            return {
                "os": platform.platform(),
                "py": platform.python_version(),
                "pyqt": app_config.get_pyqt_version() if hasattr(app_config, "get_pyqt_version") else None,
            }
        except Exception:
            return {}
