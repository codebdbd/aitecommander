"""
Персистентный кэш профилей браузеров на базе BaseCache.
- In-memory хранение с TTL (валидность записей)
- Персистентность в JSON-файле: один общий файл для всех браузеров
Совместим с прежним форматом `profile_cache.py`.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.cache.base import BaseCache, CacheRecord
from app.config_data import app_config

def get_cache_path() -> Path:
    """Возвращает путь к файлу кэша профилей браузеров.

    Остаётся совместимым с прежним расположением: browser_profiles.json
    в config-директории пользователя.
    """
    return app_config.paths.get_config_dir() / "browser_profiles.json"


class PersistentProfileCache(BaseCache):
    def __init__(self, *, default_ttl: Optional[float] = None) -> None:
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._store: dict[str, CacheRecord] = {}
        self._path: Path = get_cache_path()
        self._load_from_disk()

    # --- файловые операции ---
    def _load_from_disk(self) -> None:
        try:
            if not self._path.exists():
                return
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            now = time.time()
            for key, profiles in data.items():
                if not isinstance(key, str):
                    continue
                # При старте считаем загруженные данные свежими
                self._store[key] = CacheRecord(value=profiles, ts=now, ttl=self._default_ttl)
        except Exception:
            # Тихо игнорируем проблемы загрузки, как и раньше
            pass

    def _ensure_dirs(self) -> None:
        try:
            app_config.paths.ensure_user_data_dirs()
        except Exception:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _dump_to_disk(self) -> None:
        # Сохраняем только значения (без внутренних полей) атомарно
        data: Dict[str, Any] = {key: rec.value for key, rec in self._store.items()}
        self._ensure_dirs()
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            # 1) Пишем во временный файл
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                try:
                    f.flush()
                    os.fsync(f.fileno())  # по возможности синхронизируем на диск
                except Exception:
                    # На некоторых ФС/ОС fsync может быть не нужен/недоступен — игнорируем
                    pass
            # 2) Атомарно заменяем основной файл
            os.replace(str(tmp_path), str(self._path))
        except Exception:
            # При любой ошибке пытаемся удалить временный файл, основной не трогаем
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            raise

    # --- BaseCache API ---
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            rec = self._store.get(key)
            if rec is None:
                return None
            # проверяем TTL
            if not rec.is_valid():
                # Протухло — удаляем из памяти и синхронно обновляем файл, чтобы не копить мусор
                self._store.pop(key, None)
                try:
                    self._dump_to_disk()
                except Exception:
                    # Игнорируем ошибки записи на диск, но из памяти уже удалили
                    pass
                return None
            return rec.value

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._store[key] = CacheRecord(
                value=value,
                ts=time.time(),
                ttl=self._default_ttl if ttl is None else ttl,
            )
            try:
                self._dump_to_disk()
            except Exception:
                # не проваливаемся на ошибке диска
                pass

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
            try:
                self._dump_to_disk()
            except Exception:
                pass
