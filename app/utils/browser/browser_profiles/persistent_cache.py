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
        # Отложенная/пакетная запись
        try:
            _delay = getattr(app_config, "get_profile_cache_flush_delay", None)
            self._flush_delay_sec: float = float(_delay()) if callable(_delay) else 0.5
        except Exception:
            self._flush_delay_sec = 0.5
        self._dirty: bool = False
        self._next_flush_ts: float = 0.0
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

    # --- механика отложенного сброса ---
    def _mark_dirty_locked(self) -> None:
        self._dirty = True
        now = time.time()
        # если не запланировано, планируем
        if self._next_flush_ts <= 0:
            self._next_flush_ts = now + self._flush_delay_sec

    def _maybe_flush_locked(self, *, force: bool = False) -> None:
        if not self._dirty:
            return
        now = time.time()
        if force or (self._next_flush_ts > 0 and now >= self._next_flush_ts):
            try:
                self._dump_to_disk()
            except Exception:
                # Не проваливаемся на ошибке диска
                pass
            finally:
                # Сбрасываем флаги независимо от результата, чтобы не писать бесконечно
                self._dirty = False
                self._next_flush_ts = 0.0

    # --- BaseCache API ---
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            rec = self._store.get(key)
            if rec is None:
                return None
            # проверяем TTL
            if not rec.is_valid():
                # Протухло — удаляем из памяти и отмечаем необходимость отложенной записи
                self._store.pop(key, None)
                self._mark_dirty_locked()
                self._maybe_flush_locked()
                return None
            return rec.value

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._store[key] = CacheRecord(
                value=value,
                ts=time.time(),
                ttl=self._default_ttl if ttl is None else ttl,
            )
            # Отмечаем грязное состояние и откладываем запись
            self._mark_dirty_locked()
            self._maybe_flush_locked()

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
            self._mark_dirty_locked()
            self._maybe_flush_locked()

    # --- публичные методы управления сбросом ---
    def flush(self) -> None:
        """Принудительно сбросить изменения на диск."""
        with self._lock:
            self._maybe_flush_locked(force=True)

    def periodic_flush(self) -> None:
        """Внешняя периодическая точка: выполнить сброс, если подошёл срок.

        Вызывайте из места, где уже есть периодический цикл/таймер в приложении.
        """
        with self._lock:
            self._maybe_flush_locked(force=False)

    # Контекстный менеджер для гарантированного сброса
    def __enter__(self) -> "PersistentProfileCache":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        # При выходе всегда пытаемся сбросить на диск
        try:
            self.flush()
        except Exception:
            pass
