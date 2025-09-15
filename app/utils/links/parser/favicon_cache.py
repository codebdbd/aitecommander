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


# --- Централизованные помощники по обработке ошибок shelve/блокировок ---
def _is_portalocker_lock_exception(exc: Exception) -> bool:
    """True если exc является исключением блокировок portalocker."""
    try:  # noqa: SIM105
        from portalocker import exceptions as _pl_exc  # type: ignore

        return isinstance(exc, getattr(_pl_exc, "LockException", tuple()))
    except Exception:
        return False


def _is_filelock_timeout(exc: Exception) -> bool:
    """True если exc является таймаутом блокировки filelock."""
    try:  # noqa: SIM105
        from filelock import Timeout as FileLockTimeout  # type: ignore

        return isinstance(exc, FileLockTimeout)
    except Exception:
        return False


def _is_known_cache_io_error(exc: Exception) -> bool:
    """Распознаёт ожидаемые ошибки работы с файловым кэшем.

    Сюда относятся системные ошибки ввода-вывода и ошибки shelve/блокировок.
    """
    if isinstance(exc, (OSError, shelve.Error)):
        return True
    if _is_portalocker_lock_exception(exc) or _is_filelock_timeout(exc):
        return True
    return False


def _safe_try(action: str, func, default=None):
    """Выполняет func(), обрабатывая ожидаемые ошибки как warning, а неожиданные — пробрасывает.

    - action: человекочитаемое описание операции (для логов)
    - func: нулеаргументная функция/лямбда для выполнения
    - default: возвращаемое значение при ожидаемой ошибке
    """
    try:
        return func()
    except Exception as exc:  # noqa: BLE001
        if _is_known_cache_io_error(exc):
            logger.warning("favicon_cache: %s failed: %s", action, exc)
            return default
        logger.exception("favicon_cache: unexpected error during %s", action)
        raise


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
            # Ensure directory exists before opening
            _safe_try("ensure_user_icons_dir()", lambda: icon_path_service.ensure_user_icons_dir(), default=None)
            def _do_open():
                return shelve.open(current_path)
            db = _safe_try(f"open db {current_path}", _do_open, default=None)
            self._db = db if db is not None else None
            self._db_path_str = current_path

    def _close_db(self) -> None:
        db = self._db
        self._db = None
        if db is not None:
            _safe_try("close db", lambda: db.close(), default=None)

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
                        _safe_try("delete expired key (persistent)", lambda: db.__delitem__(key), default=None)
                        # удаляем из индекса
                        def _update_idx_del():
                            idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                            if key in idx:
                                idx.pop(key, None)
                                db["__ts_index__"] = idx
                                sync = getattr(db, "sync", None)
                                if callable(sync):
                                    sync()
                        _safe_try("update __ts_index__ after expired delete (persistent)", _update_idx_del, default=None)
                        return None
                    return item
                else:
                    # Непостоянный режим: открываем/закрываем на каждую операцию (поведение как прежде)
                    _safe_try("ensure_user_icons_dir()", lambda: icon_path_service.ensure_user_icons_dir(), default=None)
                    # Открываем shelve с явной обработкой ошибок
                    db2 = _safe_try(f"open db {current_path}", lambda: shelve.open(current_path), default=None)
                    if db2 is None:
                        return None
                    with closing(db2):
                        item = db2.get(key)
                        if not item:
                            return None
                        ts = float(item.get("timestamp", 0.0))
                        ttl = self._compute_effective_ttl(item)
                        if ttl <= 0 or (self._now() - ts) >= ttl:
                            # Удаляем протухшую запись с безопасной обработкой ошибок
                            _safe_try("delete expired key", lambda: db2.__delitem__(key), default=None)
                            # удалить из индекса
                            def _update_idx_del():
                                idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                                if key in idx:
                                    idx.pop(key, None)
                                    db2["__ts_index__"] = idx
                                    sync = getattr(db2, "sync", None)
                                    if callable(sync):
                                        sync()
                            _safe_try("update __ts_index__ after expired delete", _update_idx_del, default=None)
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
                    def _update_idx_persistent():
                        idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                        if key in idx:
                            idx.pop(key, None)
                        idx[key] = float(to_store.get("timestamp", ts_now))
                        db["__ts_index__"] = idx
                    _safe_try("update __ts_index__ on set (persistent)", _update_idx_persistent, default=None)
                    logger.debug("[cache] SAVE %s", key)
                    _safe_try("sync after set (persistent)", lambda: getattr(db, "sync", lambda: None)(), default=None)
                    # Мгновенное ограничение размера через индекс (без полной сортировки)
                    def _enforce_size_limit_persistent():
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
                            _safe_try("delete oldest key during size enforcement (persistent)",
                                      lambda k=oldest_key: db.__delitem__(k), default=None)
                        db["__ts_index__"] = idx
                        # Фоллбек: если индекс пуст/неполон и лимит не соблюден — разовый лёгкий проход по БД
                        def _fallback_sweep_persistent():
                            non_service = [k for k in db.keys() if not k.startswith("__")]
                            if len(non_service) > max_size:
                                items: list[tuple[str, float]] = []
                                for k in non_service:
                                    it = db.get(k)
                                    ts = float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                                    items.append((k, ts))
                                items.sort(key=lambda x: x[1])
                                for k, _ in items[: len(non_service) - max_size]:
                                    _safe_try("delete overflow key during fallback sweep (persistent)",
                                              lambda kk=k: db.__delitem__(kk), default=None)
                                    if k in idx:
                                        idx.pop(k, None)
                                db["__ts_index__"] = idx
                        _safe_try("fallback sweep for size enforcement (persistent)", _fallback_sweep_persistent, default=None)
                        _safe_try("sync after size enforcement (persistent)", lambda: getattr(db, "sync", lambda: None)(), default=None)
                    _safe_try("enforce size limit on set (persistent)", _enforce_size_limit_persistent, default=None)
                    # Установим маркер последней очистки (для тестов и отложенной периодической очистки)
                    _safe_try("set __last_cleanup_ts__ (persistent)", lambda: db.__setitem__("__last_cleanup_ts__", ts_now), default=None)
                else:
                    # Непостоянный режим: открываем/закрываем на каждую операцию (поведение как прежде)
                    _safe_try("ensure_user_icons_dir()", lambda: icon_path_service.ensure_user_icons_dir(), default=None)
                    db2 = _safe_try(f"open db {current_path}", lambda: shelve.open(current_path), default=None)
                    if db2 is None:
                        return
                    with closing(db2):
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
                        def _update_idx_set():
                            idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                            if key in idx:
                                idx.pop(key, None)
                            idx[key] = float(to_store.get("timestamp", ts_now))
                            db2["__ts_index__"] = idx
                        _safe_try("update __ts_index__ on set", _update_idx_set, default=None)
                        logger.debug("[cache] SAVE %s", key)
                        # Мгновенное ограничение размера через индекс (без полной сортировки)
                        def _enforce_size_limit():
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
                                _safe_try("delete oldest key during size enforcement",
                                          lambda k=oldest_key: db2.__delitem__(k), default=None)
                            db2["__ts_index__"] = idx
                            # Фоллбек: если индекс пуст/неполон и лимит не соблюден — разовый лёгкий проход по БД
                            def _fallback_sweep():
                                non_service = [k for k in db2.keys() if not k.startswith("__")]
                                if len(non_service) > max_size:
                                    items: list[tuple[str, float]] = []
                                    for k in non_service:
                                        it = db2.get(k)
                                        ts = float(it.get("timestamp", 0.0)) if isinstance(it, dict) else 0.0
                                        items.append((k, ts))
                                    items.sort(key=lambda x: x[1])
                                    for k, _ in items[: len(non_service) - max_size]:
                                        _safe_try("delete overflow key during fallback sweep",
                                                  lambda kk=k: db2.__delitem__(kk), default=None)
                                        if k in idx:
                                            idx.pop(k, None)
                                    db2["__ts_index__"] = idx
                            _safe_try("fallback sweep for size enforcement", _fallback_sweep, default=None)
                        _safe_try("enforce size limit on set", _enforce_size_limit, default=None)
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
                                _safe_try(f"remove file {p}", lambda path=p: os.remove(path), default=None)
                        logger.debug("[cache] CLEAR ALL")
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
                        _safe_try("invalidate key (persistent)", lambda: db.__delitem__(key), default=None)
                        logger.debug("[cache] INVALIDATE %s", key)
                        # убрать из индекса
                        def _update_idx():
                            idx: "OrderedDict[str, float]" = db.get("__ts_index__") or OrderedDict()
                            if key in idx:
                                idx.pop(key, None)
                                db["__ts_index__"] = idx
                        _safe_try("update __ts_index__ on invalidate", _update_idx, default=None)
                        _safe_try("sync on invalidate", lambda: getattr(db, "sync", lambda: None)(), default=None)
                else:
                    _safe_try("ensure_user_icons_dir()", lambda: icon_path_service.ensure_user_icons_dir(), default=None)
                    db2 = _safe_try(f"open db {current_path}", lambda: shelve.open(current_path), default=None)
                    if db2 is None:
                        return
                    with closing(db2):
                        if key in db2:
                            _safe_try("invalidate key (non-persistent)", lambda: db2.__delitem__(key), default=None)
                            logger.debug("[cache] INVALIDATE %s", key)
                            def _update_idx2():
                                idx: "OrderedDict[str, float]" = db2.get("__ts_index__") or OrderedDict()
                                if key in idx:
                                    idx.pop(key, None)
                                    db2["__ts_index__"] = idx
                            _safe_try("update __ts_index__ on invalidate (non-persistent)", _update_idx2, default=None)


# Глобальный экземпляр
favicon_cache = FaviconCache()


__all__ = ["FaviconCache", "favicon_cache"]
