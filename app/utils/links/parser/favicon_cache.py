"""
Файловый кэш для фавиконок с TTL и файловой блокировкой.

Использует shelve для хранения. Блокировка реализована через lock-файл .lock рядом с БД.
Совместим по данным с предыдущей версией (ключи = URL, значения = dict с полями icon/title/...)
"""
from __future__ import annotations

import os
import time
import shelve
import threading
from contextlib import contextmanager, closing
from typing import Any, Optional

from app.utils.cache.base import BaseCache
from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service
from .constants import CACHE_TTL, SHORT_NEGATIVE_TTL, logger

# Опционально используем resolve_icon_for_link, как и раньше, чтобы определять negative TTL
try:  # noqa: SIM105
    from app.utils.ui.icon.icon_resolver import resolve_icon_for_link  # type: ignore
except Exception:  # noqa: BLE001
    resolve_icon_for_link = None  # type: ignore


@contextmanager
def _file_lock(lock_path: str, *, timeout: float = 5.0, poll_interval: float = 0.05):
    """Кроссплатформенная файловая блокировка.

    Пытаемся использовать portalocker для надёжной блокировки (в т.ч. на сетевых ФС).
    Если portalocker недоступен, используем простой lock-файл с таймаутом как фоллбек.
    """
    try:
        import portalocker  # type: ignore

        # Используем отдельный lock-файл, чтобы не блокировать саму БД на уровне shelve
        # и избегать конфликтов форматов (dir/dat/bak).
        with open(lock_path, "a+b") as fp:
            try:
                portalocker.lock(fp, portalocker.LOCK_EX | portalocker.LOCK_NB)
            except Exception:
                # Ждём с опросом до таймаута
                start = time.time()
                while True:
                    try:
                        portalocker.lock(fp, portalocker.LOCK_EX | portalocker.LOCK_NB)
                        break
                    except Exception:
                        if (time.time() - start) >= timeout:
                            logger.warning("favicon lock timeout: %s", lock_path)
                            break
                        time.sleep(poll_interval)
            try:
                yield
            finally:
                try:
                    portalocker.unlock(fp)
                except Exception:
                    pass
        return
    except Exception:
        # Фоллбек: самодельная блокировка через эксклюзивное создание файла
        start = time.time()
        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode())
                finally:
                    os.close(fd)
                break
            except FileExistsError:
                if (time.time() - start) >= timeout:
                    logger.warning("favicon lock timeout(fallback): %s", lock_path)
                    lock_path = None  # type: ignore[assignment]
                    break
                time.sleep(poll_interval)
        try:
            yield
        finally:
            if lock_path and os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass


def _db_path() -> str:
    return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")


class FaviconCache(BaseCache):
    def __init__(self, *, default_ttl: Optional[float] = CACHE_TTL) -> None:
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        # Кэшируем результат _get_default_icon(), чтобы не дергать resolver повторно
        self._default_icon_cached: Optional[str] = None
        # Параметры очистки (интервал фиксируем, а max_size читаем динамически из конфигурации)
        self._cleanup_interval_sec = self._get_cleanup_interval()

    # Вспомогательные методы
    def _get_default_icon(self) -> str:
        if self._default_icon_cached is not None:
            return self._default_icon_cached
        if resolve_icon_for_link is None:
            self._default_icon_cached = ""
            return self._default_icon_cached
        try:
            self._default_icon_cached = (
                resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
            )
        except Exception:  # noqa: BLE001
            self._default_icon_cached = ""
        return self._default_icon_cached

    def _compute_effective_ttl(self, item: dict[str, Any]) -> float:
        # Совместимость с прежней логикой: отсутствие "ttl" и default_icon => короткий негативный TTL
        if "ttl" not in item and item.get("icon", "") == self._get_default_icon():
            return float(SHORT_NEGATIVE_TTL)
        return float(item.get("ttl", self._default_ttl or CACHE_TTL))

    # --- Конфигурация и очистка ---
    @staticmethod
    def _get_max_size() -> int:
        """Максимальный размер БД кэша. Должен быть >=1.

        Пытаемся получить из app_config: метод get_favicon_cache_max_size() или атрибут favicon_cache_max_size.
        По умолчанию 5000.
        """
        default = 5000
        try:
            getter = getattr(app_config, "get_favicon_cache_max_size", None)
            if callable(getter):
                return max(1, int(getter()))
            raw = getattr(app_config, "favicon_cache_max_size", default)
            return max(1, int(raw))
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def _get_cleanup_interval() -> float:
        """Интервал периодической очистки (сек). По умолчанию 5 минут."""
        default = 300.0
        try:
            getter = getattr(app_config, "get_favicon_cache_cleanup_interval", None)
            if callable(getter):
                return max(30.0, float(getter()))
            raw = getattr(app_config, "favicon_cache_cleanup_interval", default)
            return max(30.0, float(raw))
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def _now() -> float:
        return time.time()

    def _maybe_cleanup(self, db: shelve.Shelf) -> None:
        """Периодическая очистка: удаление протухших и, при необходимости, самых старых записей.

        Чтобы избежать частых полных проходов, используем метку времени последней очистки,
        хранимую в специальном ключе "__last_cleanup_ts__".
        """
        try:
            last_ts = float(db.get("__last_cleanup_ts__", 0.0) or 0.0)
        except Exception:
            last_ts = 0.0
        now = self._now()
        if (now - last_ts) < self._cleanup_interval_sec:
            return

        removed = 0
        try:
            # 1) удаляем протухшие
            to_delete: list[str] = []
            for k in list(db.keys()):
                if k.startswith("__"):
                    continue
                try:
                    item = db.get(k)
                    if not isinstance(item, dict):
                        # Неподдерживаемый формат — удаляем
                        to_delete.append(k)
                        continue
                    ts = float(item.get("timestamp", 0.0))
                    ttl = self._compute_effective_ttl(item)
                    if ttl <= 0 or (now - ts) >= ttl:
                        to_delete.append(k)
                except Exception:
                    to_delete.append(k)
            for k in to_delete:
                try:
                    del db[k]
                    removed += 1
                except Exception:
                    pass

            # 2) ограничиваем размер БД, удаляя самые старые по timestamp
            max_size = self._get_max_size()
            # Собираем пары (k, ts)
            items: list[tuple[str, float]] = []
            for k in db.keys():
                if k.startswith("__"):
                    continue
                try:
                    it = db.get(k)
                    ts = float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                except Exception:
                    ts = 0.0
                items.append((k, ts))
            if len(items) > max_size:
                # Сортируем по возрастанию ts и удаляем лишние
                items.sort(key=lambda x: x[1])
                to_evict = len(items) - max_size
                for k, _ in items[:to_evict]:
                    try:
                        del db[k]
                        removed += 1
                    except Exception:
                        pass
        finally:
            try:
                db["__last_cleanup_ts__"] = now
                if removed:
                    logger.debug("[cache] CLEANUP removed=%s", removed)
            except Exception:
                pass

    # Реализация BaseCache
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            # Гарантируем, что каталог пользовательских иконок создан
            try:
                icon_path_service.ensure_user_icons_dir()
            except Exception:  # noqa: BLE001
                pass
            path = _db_path()
            lock_path = f"{path}.lock"
            with _file_lock(lock_path):
                with closing(shelve.open(path)) as db:
                    item = db.get(key)
                    if not item:
                        return None
                    ts = float(item.get("timestamp", 0.0))
                    ttl = self._compute_effective_ttl(item)
                    if ttl <= 0 or (time.time() - ts) >= ttl:
                        # Удаляем протухшую запись, чтобы база не разрасталась
                        try:
                            del db[key]
                        except Exception:
                            pass
                        return None
                    return item

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            # Гарантируем, что каталог пользовательских иконок создан
            try:
                icon_path_service.ensure_user_icons_dir()
            except Exception:  # noqa: BLE001
                pass
            path = _db_path()
            lock_path = f"{path}.lock"
            with _file_lock(lock_path):
                with closing(shelve.open(path)) as db:
                    # Очистка перед записью, чтобы ограничивать рост
                    try:
                        self._maybe_cleanup(db)
                    except Exception:
                        pass
                    if isinstance(value, dict):
                        to_store = dict(value)
                    else:
                        # Оборачиваем произвольное значение в словарь для совместимости
                        to_store = {"value": value}
                    to_store.setdefault("timestamp", time.time())
                    if ttl is not None:
                        to_store["ttl"] = float(ttl)
                    db[key] = to_store
                    logger.debug("[cache] SAVE %s", key)
                    # Жесткое ограничение размера сразу после записи
                    try:
                        max_size = self._get_max_size()
                        items: list[tuple[str, float]] = []
                        for k in db.keys():
                            if k.startswith("__"):
                                continue
                            try:
                                it = db.get(k)
                                ts = float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                            except Exception:
                                ts = 0.0
                            items.append((k, ts))
                        if len(items) > max_size:
                            items.sort(key=lambda x: x[1])
                            to_evict = len(items) - max_size
                            for k, _ in items[:to_evict]:
                                try:
                                    del db[k]
                                except Exception:
                                    pass
                    except Exception:
                        pass

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            # Гарантируем, что каталог пользовательских иконок создан
            try:
                icon_path_service.ensure_user_icons_dir()
            except Exception:  # noqa: BLE001
                pass
            path = _db_path()
            lock_path = f"{path}.lock"
            with _file_lock(lock_path):
                if key is None:
                    try:
                        # Полное удаление БД
                        for suffix in ("", ".bak", ".dat", ".dir"):
                            p = f"{path}{suffix}"
                            if os.path.exists(p):
                                os.remove(p)
                        logger.debug("[cache] CLEAR ALL")
                    except Exception:  # noqa: BLE001
                        pass
                    return
                with closing(shelve.open(path)) as db:
                    if key in db:
                        del db[key]
                        logger.debug("[cache] INVALIDATE %s", key)


# Глобальный экземпляр
favicon_cache = FaviconCache()


__all__ = ["FaviconCache", "favicon_cache"]
