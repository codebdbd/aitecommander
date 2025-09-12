"""
Файловый кэш для фавиконок с TTL и файловой блокировкой.

Использует shelve для хранения. Блокировка реализована через lock-файл .lock рядом с БД.
Совместим по данным с предыдущей версией (ключи = URL, значения = dict с полями icon/title/...)
"""

from __future__ import annotations

import os
import atexit
import shelve
import threading
import time
from contextlib import closing, contextmanager
from typing import Any, Optional

from app.config_data import app_config
from app.utils.cache.base import BaseCache
from app.utils.ui.icon.path_service import icon_path_service

from .constants import CACHE_TTL, SHORT_NEGATIVE_TTL, logger

# Опционально используем resolve_icon_for_link, как и раньше, чтобы определять negative TTL
try:  # noqa: SIM105
    from app.utils.ui.icon.icon_resolver import resolve_icon_for_link  # type: ignore
except Exception:  # noqa: BLE001
    resolve_icon_for_link = None  # type: ignore


def _get_lock_backend() -> str:
    """Returns desired lock backend from config: 'auto'|'portalocker'|'filelock'|'fallback'."""
    try:
        v = getattr(app_config, "FAVICON_LOCK_BACKEND", "auto")
        if not isinstance(v, str):
            return "auto"
        v = v.lower().strip()
        if v in {"auto", "portalocker", "filelock", "fallback"}:
            return v
    except Exception:  # noqa: BLE001
        pass
    return "auto"


@contextmanager
def _file_lock(lock_path: str, *, timeout: float = 5.0, poll_interval: float = 0.05):
    """Кроссплатформенная файловая блокировка без активного ожидания.

    Порядок механизмов:
    1) portalocker.Lock(..., timeout=timeout)
    2) filelock.FileLock(...).acquire(timeout=timeout)
    3) Фоллбек: эксклюзивное создание файла с мягким backoff (последний рубеж)

    Семантика сохранена: при истечении таймаута — логируем предупреждение и продолжаем без фактической блокировки.
    """
    backend = _get_lock_backend()

    # 1) portalocker (если доступен и разрешён)
    if backend in ("auto", "portalocker"):
        try:
            import portalocker  # type: ignore

            # Используем неблокирующую попытку с мягким backoff до таймаута
            locked = False
            try:
                with open(lock_path, "a+b") as fp:
                    start = time.monotonic()
                    sleep_cur = max(0.01, float(poll_interval))
                    while True:
                        try:
                            portalocker.lock(fp, portalocker.LOCK_EX | portalocker.LOCK_NB)
                            locked = True
                            break
                        except Exception:
                            if (time.monotonic() - start) >= float(timeout):
                                logger.warning("favicon lock timeout: %s", lock_path)
                                break
                            time.sleep(sleep_cur)
                            sleep_cur = min(sleep_cur * 2.0, 0.25)
                    try:
                        yield
                    finally:
                        if locked:
                            try:
                                portalocker.unlock(fp)
                            except Exception:
                                pass
                return
            except Exception as e:
                logger.debug("portalocker lock error: %s", e, exc_info=True)
                # Переходим к следующему бэкенду
        except Exception:
            if backend == "portalocker":
                logger.debug("portalocker selected but unavailable; falling back")
            # иначе продолжаем к filelock

    # 2) filelock (если доступен и разрешён; сработает и для auto при отсутствии portalocker)
    if backend in ("auto", "filelock"):
        try:
            from filelock import FileLock, Timeout as FileLockTimeout  # type: ignore

            lock = FileLock(lock_path)
            try:
                lock.acquire(timeout=max(0.0, float(timeout)))
                try:
                    yield
                finally:
                    try:
                        lock.release()
                    except Exception:
                        pass
                return
            except FileLockTimeout as e:
                logger.warning("favicon lock timeout(filelock): %s (%s)", lock_path, e)
                yield
                return
            except Exception as e:
                logger.debug("filelock error: %s", e, exc_info=True)
                # Падать не будем — перейдём к фоллбеку
        except Exception:
            if backend == "filelock":
                logger.debug("filelock selected but unavailable; falling back")

    # 3) Фоллбек: самодельная блокировка через эксклюзивное создание файла, с мягким backoff
    start = time.time()
    sleep_cur = max(0.01, float(poll_interval))
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            got_lock = True
            break
        except FileExistsError:
            got_lock = False
            if (time.time() - start) >= timeout:
                logger.warning("favicon lock timeout(fallback): %s", lock_path)
                break
            time.sleep(sleep_cur)
            # Экспоненциальный рост до 250мс, чтобы не грузить CPU
            sleep_cur = min(sleep_cur * 2.0, 0.25)
        except Exception as e:
            logger.debug("fallback lock error: %s", e, exc_info=True)
            got_lock = False
            break
    try:
        yield
    finally:
        if got_lock and os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                logger.debug(
                    "favicon_lock: failed to remove fallback lock file",
                    exc_info=True,
                )


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
        # Постоянное соединение с shelve (включается конфигом)
        self._db_path_str: Optional[str] = None
        self._db: Optional[shelve.Shelf] = None
        try:
            self._persistent_enabled: bool = bool(
                getattr(app_config, "FAVICON_CACHE_PERSISTENT", False)
            )
        except Exception:
            self._persistent_enabled = False
        try:
            atexit.register(self._safe_shutdown)
        except Exception:
            pass

    # Управление shelve
    def _get_db_path(self) -> str:
        # Всегда вычисляем путь из текущего icon_path_service (важно для тестов и динамики)
        return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")

    def _open_db(self) -> None:
        current_path = self._get_db_path()
        # Если путь изменился — закрываем и переоткрываем
        if self._db_path_str and self._db_path_str != current_path:
            self._close_db()
        if self._db is None:
            try:
                # Ensure directory exists before opening
                try:
                    icon_path_service.ensure_user_icons_dir()
                except Exception:
                    pass
                self._db = shelve.open(current_path)
                self._db_path_str = current_path
            except Exception as exc:  # noqa: BLE001
                self._db = None
                self._db_path_str = current_path
                logger.debug("favicon_cache: failed to open db: %s", exc, exc_info=True)

    def _close_db(self) -> None:
        db = self._db
        self._db = None
        if db is not None:
            try:
                db.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("favicon_cache: failed to close db: %s", exc, exc_info=True)

    def _safe_shutdown(self) -> None:  # pragma: no cover - atexit path
        try:
            self._close_db()
        except Exception:
            pass

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
        except Exception as exc:
            last_ts = 0.0
            logger.debug(
                "favicon_cache: failed to read last cleanup ts: %s", exc, exc_info=True
            )
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
                except Exception as exc:
                    to_delete.append(k)
                    logger.debug(
                        "favicon_cache: failed to inspect entry '%s' during cleanup: %s",
                        k,
                        exc,
                        exc_info=True,
                    )
            for k in to_delete:
                try:
                    del db[k]
                    removed += 1
                except Exception as exc:
                    logger.debug(
                        "favicon_cache: failed to delete expired key '%s': %s",
                        k,
                        exc,
                        exc_info=True,
                    )

            # 2) ограничиваем размер БД, удаляя самые старые по timestamp
            max_size = self._get_max_size()
            # Собираем пары (k, ts)
            items: list[tuple[str, float]] = []
            for k in db.keys():
                if k.startswith("__"):
                    continue
                try:
                    it = db.get(k)
                    ts = (
                        float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                    )
                except Exception as exc:
                    ts = 0.0
                    logger.debug(
                        "favicon_cache: failed to get ts for key '%s': %s",
                        k,
                        exc,
                        exc_info=True,
                    )
                items.append((k, ts))
            if len(items) > max_size:
                # Сортируем по возрастанию ts и удаляем лишние
                items.sort(key=lambda x: x[1])
                to_evict = len(items) - max_size
                for k, _ in items[:to_evict]:
                    try:
                        del db[k]
                        removed += 1
                    except Exception as exc:
                        logger.debug(
                            "favicon_cache: failed to evict key '%s': %s",
                            k,
                            exc,
                            exc_info=True,
                        )
        finally:
            try:
                db["__last_cleanup_ts__"] = now
                try:
                    # Для постоянного соединения — синхронизируем на диск
                    sync = getattr(db, "sync", None)
                    if callable(sync):
                        sync()
                except Exception:
                    pass
                if removed:
                    logger.debug("[cache] CLEANUP removed=%s", removed)
            except Exception as exc:
                logger.debug(
                    "favicon_cache: failed to write last cleanup ts or log removed count: %s",
                    exc,
                    exc_info=True,
                )

    # Реализация BaseCache
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            # Лочим межпроцессно через lock-файл на время операции
            current_path = self._get_db_path()
            lock_path = f"{current_path}.lock"
            with _file_lock(lock_path):
                if self._persistent_enabled:
                    # Гарантируем, что db открыта
                    if self._db is None:
                        self._open_db()
                    db = self._db
                    if db is None:
                        return None
                    item = db.get(key)
                    if not item:
                        return None
                    ts = float(item.get("timestamp", 0.0))
                    ttl = self._compute_effective_ttl(item)
                    if ttl <= 0 or (time.time() - ts) >= ttl:
                        # Удаляем протухшую запись, чтобы база не разрасталась
                        try:
                            del db[key]
                            try:
                                sync = getattr(db, "sync", None)
                                if callable(sync):
                                    sync()
                            except Exception:
                                pass
                        except Exception as exc:
                            logger.debug(
                                "favicon_cache: failed to delete expired key '%s' in get(): %s",
                                key,
                                exc,
                                exc_info=True,
                            )
                        return None
                    return item
                else:
                    # Непостоянный режим: открываем/закрываем на каждую операцию (поведение как прежде)
                    try:
                        icon_path_service.ensure_user_icons_dir()
                    except Exception:
                        pass
                    with closing(shelve.open(current_path)) as db2:
                        item = db2.get(key)
                        if not item:
                            return None
                        ts = float(item.get("timestamp", 0.0))
                        ttl = self._compute_effective_ttl(item)
                        if ttl <= 0 or (time.time() - ts) >= ttl:
                            try:
                                del db2[key]
                            except Exception as exc:
                                logger.debug(
                                    "favicon_cache: failed to delete expired key '%s' in get(): %s",
                                    key,
                                    exc,
                                    exc_info=True,
                                )
                            return None
                        return item

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            # Лочим межпроцессно через lock-файл на время операции
            current_path = self._get_db_path()
            lock_path = f"{current_path}.lock"
            with _file_lock(lock_path):
                if self._persistent_enabled:
                    # Ensure db is open
                    if self._db is None:
                        self._open_db()
                    db = self._db
                    if db is None:
                        return
                    # Очистка перед записью, чтобы ограничивать рост
                    try:
                        self._maybe_cleanup(db)
                    except Exception as exc:
                        logger.debug(
                            "favicon_cache: cleanup before set failed: %s",
                            exc,
                            exc_info=True,
                        )
                    if isinstance(value, dict):
                        to_store = dict(value)
                    else:
                        to_store = {"value": value}
                    to_store.setdefault("timestamp", time.time())
                    if ttl is not None:
                        to_store["ttl"] = float(ttl)
                    db[key] = to_store
                    logger.debug("[cache] SAVE %s", key)
                    try:
                        sync = getattr(db, "sync", None)
                        if callable(sync):
                            sync()
                    except Exception:
                        pass
                    # Жесткое ограничение размера сразу после записи
                    try:
                        max_size = self._get_max_size()
                        items: list[tuple[str, float]] = []
                        for k in db.keys():
                            if k.startswith("__"):
                                continue
                            try:
                                it = db.get(k)
                                ts = (
                                    float(it.get("timestamp", 0.0))
                                    if isinstance(it, dict)
                                    else 0.0
                                )
                            except Exception as exc:
                                ts = 0.0
                                logger.debug(
                                    "favicon_cache: failed to read ts during enforce max size: %s",
                                    exc,
                                    exc_info=True,
                                )
                            items.append((k, ts))
                        if len(items) > max_size:
                            items.sort(key=lambda x: x[1])
                            to_evict = len(items) - max_size
                            for k, _ in items[:to_evict]:
                                try:
                                    del db[k]
                                except Exception as exc:
                                    logger.debug(
                                        "favicon_cache: failed to evict key '%s' after set(): %s",
                                        k,
                                        exc,
                                        exc_info=True,
                                    )
                    except Exception as exc:
                        logger.debug(
                            "favicon_cache: failed enforcing max size after set(): %s",
                            exc,
                            exc_info=True,
                        )
                else:
                    # Непостоянный режим: открываем/закрываем на каждую операцию (поведение как прежде)
                    try:
                        icon_path_service.ensure_user_icons_dir()
                    except Exception:
                        pass
                    with closing(shelve.open(current_path)) as db2:
                        # Очистка перед записью
                        try:
                            self._maybe_cleanup(db2)
                        except Exception as exc:
                            logger.debug(
                                "favicon_cache: cleanup before set failed: %s",
                                exc,
                                exc_info=True,
                            )
                        if isinstance(value, dict):
                            to_store = dict(value)
                        else:
                            to_store = {"value": value}
                        to_store.setdefault("timestamp", time.time())
                        if ttl is not None:
                            to_store["ttl"] = float(ttl)
                        db2[key] = to_store
                        logger.debug("[cache] SAVE %s", key)
                        # Жесткое ограничение размера сразу после записи
                        try:
                            max_size = self._get_max_size()
                            items: list[tuple[str, float]] = []
                            for k in db2.keys():
                                if k.startswith("__"):
                                    continue
                                try:
                                    it = db2.get(k)
                                    ts = (
                                        float(it.get("timestamp", 0.0))
                                        if isinstance(it, dict)
                                        else 0.0
                                    )
                                except Exception as exc:
                                    ts = 0.0
                                    logger.debug(
                                        "favicon_cache: failed to read ts during enforce max size: %s",
                                        exc,
                                        exc_info=True,
                                    )
                                items.append((k, ts))
                            if len(items) > max_size:
                                items.sort(key=lambda x: x[1])
                                to_evict = len(items) - max_size
                                for k, _ in items[:to_evict]:
                                    try:
                                        del db2[k]
                                    except Exception as exc:
                                        logger.debug(
                                            "favicon_cache: failed to evict key '%s' after set(): %s",
                                            k,
                                            exc,
                                            exc_info=True,
                                        )
                        except Exception as exc:
                            logger.debug(
                                "favicon_cache: failed enforcing max size after set(): %s",
                                exc,
                                exc_info=True,
                            )

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            current_path = self._get_db_path()
            lock_path = f"{current_path}.lock"
            with _file_lock(lock_path):
                if key is None:
                    # Полная очистка: закрыть shelve, удалить файлы, заново открыть
                    try:
                        self._close_db()
                        base = self._get_db_path()
                        for suffix in ("", ".bak", ".dat", ".dir"):
                            p = f"{base}{suffix}"
                            if os.path.exists(p):
                                os.remove(p)
                        logger.debug("[cache] CLEAR ALL")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(
                            "favicon_cache: failed to clear db files: %s",
                            exc,
                            exc_info=True,
                        )
                    finally:
                        if self._persistent_enabled:
                            self._open_db()
                    return
                # invalidate single key
                if self._persistent_enabled:
                    if self._db is None:
                        self._open_db()
                    db = self._db
                    if db is None:
                        return
                    if key in db:
                        try:
                            del db[key]
                            logger.debug("[cache] INVALIDATE %s", key)
                            try:
                                sync = getattr(db, "sync", None)
                                if callable(sync):
                                    sync()
                            except Exception:
                                pass
                        except Exception as exc:
                            logger.debug(
                                "favicon_cache: failed to invalidate key '%s': %s",
                                key,
                                exc,
                                exc_info=True,
                            )
                else:
                    try:
                        icon_path_service.ensure_user_icons_dir()
                    except Exception:
                        pass
                    with closing(shelve.open(current_path)) as db2:
                        if key in db2:
                            try:
                                del db2[key]
                                logger.debug("[cache] INVALIDATE %s", key)
                            except Exception as exc:
                                logger.debug(
                                    "favicon_cache: failed to invalidate key '%s': %s",
                                    key,
                                    exc,
                                    exc_info=True,
                                )


# Глобальный экземпляр
favicon_cache = FaviconCache()


__all__ = ["FaviconCache", "favicon_cache"]
