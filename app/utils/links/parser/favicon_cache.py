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
from collections import OrderedDict

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
        if v in {"auto", "portalocker", "filelock"}:
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
    Если ни один из бэкендов недоступен — работаем без межпроцессной блокировки (логируем предупреждение).

    Семантика сохранена: при истечении таймаута — логируем предупреждение и продолжаем без фактической блокировки.
    Таймаут можно настроить через app_config.FAVICON_LOCK_TIMEOUT (секунды). Переданный аргумент
    ``timeout`` имеет приоритет над конфигом.
    """
    backend = _get_lock_backend()
    # Эффективный таймаут: параметр функции имеет приоритет, иначе берём из конфига
    try:
        cfg_timeout = getattr(app_config, "FAVICON_LOCK_TIMEOUT", timeout)
        eff_timeout = float(timeout if timeout is not None else cfg_timeout)
        if eff_timeout < 0:
            eff_timeout = 0.0
    except Exception:
        eff_timeout = timeout

    # 1) portalocker (если доступен и разрешён)
    if backend in ("auto", "portalocker"):
        try:
            import portalocker  # type: ignore

            # Блокирующая попытка с внутренним таймаутом — используем контекстный менеджер
            try:
                with portalocker.Lock(lock_path, timeout=max(0.0, float(eff_timeout))):
                    yield
                return
            except Exception as e:
                # Для таймаута portalocker бросает LockException; логируем как предупреждение
                try:
                    from portalocker import exceptions as _pl_exc  # type: ignore
                    if isinstance(e, getattr(_pl_exc, "LockException", tuple())):
                        logger.warning("favicon lock timeout: %s (%s)", lock_path, e)
                        yield
                        return
                except Exception:
                    pass
                logger.debug("portalocker lock error: %s", e, exc_info=True)
                # Переходим к следующему бэкенду
        except Exception:
            if backend == "portalocker":
                # Явно выбранный бэкенд недоступен — продолжаем без блокировки
                logger.warning(
                    "favicon lock backend unavailable; proceeding without interprocess lock: %s",
                    lock_path,
                )
                yield
                return
            # auto: продолжаем к filelock

    # 2) filelock (если доступен и разрешён; сработает и для auto при отсутствии portalocker)
    if backend in ("auto", "filelock"):
        try:
            from filelock import FileLock, Timeout as FileLockTimeout  # type: ignore

            lock = FileLock(lock_path)
            try:
                lock.acquire(timeout=max(0.0, float(eff_timeout)))
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
                # Явно выбранный бэкенд недоступен — продолжаем без блокировки
                logger.warning(
                    "favicon lock backend unavailable; proceeding without interprocess lock: %s",
                    lock_path,
                )
                yield
                return

    # Нет доступных бэкендов — продолжаем без межпроцессной блокировки
    logger.warning("favicon lock backend unavailable; proceeding without interprocess lock: %s", lock_path)
    yield


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
        return float(time.time())

    def _maybe_cleanup(self, db: shelve.Shelf, *, now: Optional[float] = None) -> None:
        """Периодическая очистка: удаление протухших и, при необходимости, самых старых записей.

        Чтобы избежать частых полных проходов, используем метку времени последней очистки,
        хранимую в специальном ключе "__last_cleanup_ts__".
        """
        try:
            last_ts = float(db.get("__last_cleanup_ts__", 0.0))
        except Exception as exc:
            last_ts = 0.0
            logger.debug(
                "favicon_cache: failed to read last cleanup ts: %s", exc, exc_info=True
            )
        now = self._now() if now is None else float(now)
        if (now - last_ts) < self._cleanup_interval_sec:
            return

        removed = 0
        try:
            # Загружаем/создаём упорядоченный индекс по времени: key -> ts (по возрастанию вставок)
            index: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
            # 1) Удаляем протухшие и несогласованные записи, проходя по индексу (не по всей БД)
            for k, ts in list(index.items()):
                try:
                    item = db.get(k)
                    if not isinstance(item, dict):
                        # отсутствует или невалиден — удалить
                        index.pop(k, None)
                        try:
                            if k in db:
                                del db[k]
                                removed += 1
                        except Exception:
                            pass
                        continue
                    ttl = self._compute_effective_ttl(item)
                    if ttl <= 0 or (now - ts) >= ttl:
                        index.pop(k, None)
                        try:
                            del db[k]
                            removed += 1
                        except Exception:
                            pass
                except Exception as exc:
                    index.pop(k, None)
                    try:
                        if k in db:
                            del db[k]
                            removed += 1
                    except Exception:
                        pass
                    logger.debug(
                        "favicon_cache: failed to inspect entry '%s' during cleanup: %s",
                        k,
                        exc,
                        exc_info=True,
                    )

            # 2) ограничиваем размер БД, удаляя самые старые по минимальному timestamp
            max_size = self._get_max_size()
            while len(index) > max_size:
                try:
                    oldest_key = min(index.items(), key=lambda kv: kv[1])[0]
                except ValueError:
                    break
                index.pop(oldest_key, None)
                try:
                    if oldest_key in db:
                        del db[oldest_key]
                        removed += 1
                except Exception as exc:
                    logger.debug(
                        "favicon_cache: failed to evict key '%s': %s",
                        oldest_key,
                        exc,
                        exc_info=True,
                    )
        finally:
            try:
                db["__last_cleanup_ts__"] = now
                db["__ts_index__"] = index
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
                    if ttl <= 0 or (self._now() - ts) >= ttl:
                        # Удаляем протухшую запись, чтобы база не разрасталась
                        try:
                            del db[key]
                            # удаляем из индекса
                            try:
                                idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                                if key in idx:
                                    idx.pop(key, None)
                                    db["__ts_index__"] = idx
                                    try:
                                        sync = getattr(db, "sync", None)
                                        if callable(sync):
                                            sync()
                                    except Exception:
                                        pass
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
                        if ttl <= 0 or (self._now() - ts) >= ttl:
                            try:
                                del db2[key]
                                # удалить из индекса
                                try:
                                    idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                                    if key in idx:
                                        idx.pop(key, None)
                                        db2["__ts_index__"] = idx
                                        try:
                                            sync = getattr(db2, "sync", None)
                                            if callable(sync):
                                                sync()
                                        except Exception:
                                            pass
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
                    # Предочистку перед записью не выполняем; ограничение размера делаем индексом ниже
                    if isinstance(value, dict):
                        to_store = dict(value)
                    else:
                        to_store = {"value": value}
                    ts_now = self._now()
                    to_store.setdefault("timestamp", ts_now)
                    if ttl is not None:
                        to_store["ttl"] = float(ttl)
                    db[key] = to_store
                    # Обновляем индекс времени: перемещаем ключ в конец как самый новый
                    try:
                        idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                        if key in idx:
                            idx.pop(key, None)
                        idx[key] = float(to_store.get("timestamp", ts_now))
                        db["__ts_index__"] = idx
                    except Exception:
                        pass
                    logger.debug("[cache] SAVE %s", key)
                    try:
                        sync = getattr(db, "sync", None)
                        if callable(sync):
                            sync()
                    except Exception:
                        pass
                    # Мгновенное ограничение размера через индекс (без полной сортировки)
                    try:
                        max_size = self._get_max_size()
                        idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                        # Удалим фантомные ключи, которых нет в БД
                        for k in list(idx.keys()):
                            if k not in db or k.startswith("__"):
                                idx.pop(k, None)
                        # Эвикт по индексу
                        while len(idx) > max_size:
                            try:
                                oldest_key = min(idx.items(), key=lambda kv: kv[1])[0]
                            except ValueError:
                                break
                            idx.pop(oldest_key, None)
                            try:
                                if oldest_key in db:
                                    del db[oldest_key]
                            except Exception:
                                pass
                        db["__ts_index__"] = idx
                        # Фоллбек: если индекс пуст/неполон и лимит не соблюден — разовый лёгкий проход по БД
                        try:
                            non_service = [k for k in db.keys() if not k.startswith("__")]
                            if len(non_service) > max_size:
                                items: list[tuple[str, float]] = []
                                for k in non_service:
                                    try:
                                        it = db.get(k)
                                        ts = float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                                    except Exception:
                                        ts = 0.0
                                    items.append((k, ts))
                                items.sort(key=lambda x: x[1])
                                for k, _ in items[: len(non_service) - max_size]:
                                    try:
                                        if k in db:
                                            del db[k]
                                        if k in idx:
                                            idx.pop(k, None)
                                    except Exception:
                                        pass
                                db["__ts_index__"] = idx
                        except Exception:
                            pass
                        try:
                            sync = getattr(db, "sync", None)
                            if callable(sync):
                                sync()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    # Установим маркер последней очистки (для тестов и отложенной периодической очистки)
                    try:
                        db["__last_cleanup_ts__"] = ts_now
                    except Exception:
                        pass
                else:
                    # Непостоянный режим: открываем/закрываем на каждую операцию (поведение как прежде)
                    try:
                        icon_path_service.ensure_user_icons_dir()
                    except Exception:
                        pass
                    with closing(shelve.open(current_path)) as db2:
                        # Предочистку перед записью не выполняем; ограничение размера делаем индексом ниже
                        if isinstance(value, dict):
                            to_store = dict(value)
                        else:
                            to_store = {"value": value}
                        ts_now = self._now()
                        to_store.setdefault("timestamp", ts_now)
                        if ttl is not None:
                            to_store["ttl"] = float(ttl)
                        db2[key] = to_store
                        # Обновляем индекс времени в непостоянном режиме
                        try:
                            idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                            if key in idx:
                                idx.pop(key, None)
                            idx[key] = float(to_store.get("timestamp", ts_now))
                            db2["__ts_index__"] = idx
                        except Exception:
                            pass
                        logger.debug("[cache] SAVE %s", key)
                        # Мгновенное ограничение размера через индекс (без полной сортировки)
                        try:
                            max_size = self._get_max_size()
                            idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                            # Удалим фантомные ключи, которых нет в БД
                            for k in list(idx.keys()):
                                if k not in db2 or k.startswith("__"):
                                    idx.pop(k, None)
                            # Эвикт по индексу
                            while len(idx) > max_size:
                                try:
                                    oldest_key = min(idx.items(), key=lambda kv: kv[1])[0]
                                except ValueError:
                                    break
                                idx.pop(oldest_key, None)
                                try:
                                    if oldest_key in db2:
                                        del db2[oldest_key]
                                except Exception:
                                    pass
                            db2["__ts_index__"] = idx
                            # Фоллбек: если индекс пуст/неполон и лимит не соблюден — разовый лёгкий проход по БД
                            try:
                                non_service = [k for k in db2.keys() if not k.startswith("__")]
                                if len(non_service) > max_size:
                                    items: list[tuple[str, float]] = []
                                    for k in non_service:
                                        try:
                                            it = db2.get(k)
                                            ts = float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                                        except Exception:
                                            ts = 0.0
                                        items.append((k, ts))
                                    items.sort(key=lambda x: x[1])
                                    for k, _ in items[: len(non_service) - max_size]:
                                        try:
                                            if k in db2:
                                                del db2[k]
                                            if k in idx:
                                                idx.pop(k, None)
                                        except Exception:
                                            pass
                                    db2["__ts_index__"] = idx
                            except Exception:
                                pass
                        except Exception:
                            pass
                        # Установим маркер последней очистки (для тестов и отложенной периодической очистки)
                        try:
                            db2["__last_cleanup_ts__"] = ts_now
                        except Exception:
                            pass

    def _get_max_size(self) -> int:
        """Возвращает максимально допустимый размер кэша.
        Поддерживает как новый get_* API, так и старый атрибут `favicon_cache_max_size` (для обратной совместимости тестов).
        """
        values: list[int] = []
        # Атрибут
        if hasattr(app_config, "favicon_cache_max_size"):
            try:
                values.append(int(getattr(app_config, "favicon_cache_max_size")))
            except Exception:
                pass
        # Метод
        if hasattr(app_config, "get_favicon_cache_max_size"):
            try:
                values.append(int(getattr(app_config, "get_favicon_cache_max_size")()))  # type: ignore[misc]
            except Exception:
                pass
        # Выбираем наиболее строгий (минимальный) валидный предел
        values = [v for v in values if v is not None]
        if values:
            return max(1, min(values))
        return 5000

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
                            # убрать из индекса
                            try:
                                idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                                if key in idx:
                                    idx.pop(key, None)
                                    db["__ts_index__"] = idx
                            except Exception:
                                pass
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
                                try:
                                    idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                                    if key in idx:
                                        idx.pop(key, None)
                                        db2["__ts_index__"] = idx
                                except Exception:
                                    pass
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
