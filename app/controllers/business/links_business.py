# app/controllers/links_business.py

import logging
from typing import Any, Dict, List, Optional, Union
from functools import wraps, lru_cache
from app.controllers.business.cache_mixin import CacheMixin
from app.controllers.business.pending_tasks_mixin import PendingTasksMixin
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer, pyqtSlot
from PyQt6.QtWidgets import QApplication

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services import LinksService
from app.utils.db.api import run_db
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.synchronization import tasks_lock


def validate_link_form(func):
    """Декоратор для валидации данных ссылки."""
    @wraps(func)
    def wrapper(self, link_data: Dict, *args, **kwargs):
        if not isinstance(link_data, dict):
            raise ValueError("Invalid link data provided: not a dict")
        from app.utils.validators.link_validators import validate_link_form_data

        name = link_data.get("name")
        url = link_data.get("url")
        link_type = link_data.get("type")
        category_id = link_data.get("category_id")
        if not (
            validate_link_form_data(name, url, link_type)
            and isinstance(category_id, int)
            and category_id > 0
        ):
            raise ValueError("Invalid link data provided")
        return func(self, link_data, *args, **kwargs)
    return wrapper


def handle_errors_with_default(default_value):
    """Декоратор с безопасным значением по умолчанию для соблюдения типовых контрактов."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self.logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                if handle_db_error(e, self):
                    return default_value  # Возвращаем типобезопасное значение
                raise
        return wrapper
    return decorator


# Устаревший декоратор handle_errors удалён, используем только handle_errors_with_default


class LinksBusinessLogic(QObject, CacheMixin, PendingTasksMixin):
    """
    Бизнес-логика для работы со ссылками.

    Потокобезопасность:
    - self._tasks_lock: защищает self.pending_tasks (см. PendingTasksMixin)
    - self._cache: не потокобезопасен, но используется только из главного потока или с QTimer.singleShot
    - self._pending_toggles: set, используется только из главного потока
    """

    """Бизнес-логика для работы со ссылками."""

    # Константы
    DEFAULT_SHUTDOWN_TIMEOUT = 2000
    DEFAULT_RECENT_LIMIT = 10

    # Сигналы для уведомления UI (PyQt6 синтаксис с типизацией)
    links_loaded = pyqtSignal(list, int, int)  # List[Dict], int, int - ссылки, ID категории, ID задачи
    search_results_ready = pyqtSignal(list)  # List[Dict] - результаты поиска
    favorites_counted = pyqtSignal(int, list, object)  # int, List[Dict], Optional[Dict] - количество, ссылки, текущая ссылка
    link_updated = pyqtSignal(dict)  # Dict - обновленная ссылка
    error_occurred = pyqtSignal(str)  # str - сообщение об ошибке
    link_deleted = pyqtSignal(int)  # int - ID удаленной ссылки
    recent_links_loaded = pyqtSignal(list)  # List[Dict] - недавние ссылки
    favorite_links_loaded = pyqtSignal(list)  # List[Dict] - избранные ссылки
    favorites_cleared = pyqtSignal(bool)  # bool - успех очистки
    link_by_id_loaded = pyqtSignal(dict, int)  # Dict, int - ссылка, ID
    next_position_loaded = pyqtSignal(int, int)  # int, int - позиция, category_id
    batch_updated = pyqtSignal(bool)  # bool - успех пакетного обновления

    def __init__(self, db: Database, parent: Optional[QObject] = None, 
                 logger=None, tasks_lock_instance=None, scheduler=None):
        super().__init__(parent)  # Правильное управление памятью через parent

        self.db = db
        # Сервисный слой поверх репозитория для снижения дублирования и транзакций
        self.links = LinksService(db)
        # Инжекция зависимостей
        self.scheduler = scheduler or get_task_scheduler()
        # Потокобезопасность обеспечивается PendingTasksMixin
        # self._tasks_lock защищает self.pending_tasks (PendingTasksMixin)
        if tasks_lock_instance is not None:
            self._tasks_lock = tasks_lock_instance
        # self.pending_tasks: dict, защищён self._tasks_lock (PendingTasksMixin)
        self.task_counter = 0
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # self._cache: dict, не потокобезопасен, используется только из главного потока (CacheMixin)
        # Заменяем QMutex на set для отслеживания операций toggle в процессе
        self._pending_toggles = set()  # Для предотвращения race conditions в toggle_favorite

    def shutdown(self, timeout: int = DEFAULT_SHUTDOWN_TIMEOUT):
        """Корректное завершение работы с синхронизацией реального пула потоков."""
        try:
            # Получаем тот же пул, который использует run_db
            from app.utils.db.executors.pool import get_thread_pool
            actual_pool = get_thread_pool()
            
            active_threads = actual_pool.activeThreadCount()
            if active_threads > 0:
                self.logger.debug(f"Waiting for {active_threads} active threads...")
            
            # Ждем завершения всех задач в правильном пуле
            actual_pool.waitForDone(timeout)
            
            self._clear_pending_tasks()
            self._pending_toggles.clear()
            self._cache.clear()
            
            self.logger.debug("LinksBusinessLogic shutdown completed")
        except Exception as e:
            self.logger.error(
                "Error during LinksBusinessLogic shutdown: %s", e, exc_info=True
            )

    # Метод _clear_pending_tasks реализован в PendingTasksMixin

    def load_links(self, category_id: int):
        """Загрузить ссылки для категории."""
        self.task_counter += 1
        task_id = self.task_counter

        with self._tasks_lock:
            self.pending_tasks[task_id] = category_id

        self.logger.debug(
            "Loading links for category %s, task_id=%s", category_id, task_id
        )

        def _fetch():
            rows = self.db.links.get_links(category_id)
            return rows or []

        run_db(
            _fetch,
            description=f"load_links(category_id={category_id})",
            on_finished=lambda links: self._on_links_loaded(
                links, category_id, task_id
            ),
            on_error=lambda e: self._on_worker_error(str(e), task_id=task_id),
        )

    @handle_errors_with_default([])
    def _get_links(self, category_id: int) -> List[Dict]:
        """Синхронно вернуть ссылки для категории (унифицированный метод)."""
        self.logger.info("Using synchronous get_links; consider using load_links for async operation")
        cache_key = f"links_{category_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        links = self.links.get_links(category_id)
        self._cache[cache_key] = links
        return links

    def search_links(self, query: str):
        """Поиск ссылок по запросу."""
        q = (query or "").strip()
        if not q:
            self.logger.debug(
                "Searching links: empty query -> return ALL links (global)"
            )
            run_db(
                lambda: self.db.links.get_all_links() or [],
                description="search_links(all)",
                on_finished=self._on_search_finished,
                on_error=lambda e: self._on_worker_error(str(e)),
            )
            return

        self.logger.debug("Searching links for query: %s", q)

        run_db(
            lambda: self.db.links.search_links(q) or [],
            description=f"search_links(query={q!r})",
            on_finished=self._on_search_finished,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def update_link_order(self, link_ids: list):
        """Обновить порядок ссылок."""
        if not link_ids:
            return

        self.logger.debug("Updating order for %s links", len(link_ids))

        def _on_reorder_finished(_):
            self._invalidate_cache()
            self.logger.debug("Updated order for %s links", len(link_ids))
        
        run_db(
            lambda: self.links.reorder(link_ids),
            description="update_link_order",
            on_finished=_on_reorder_finished,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def count_favorites(self, link: Optional[Dict] = None):
        """Подсчитать количество избранных ссылок."""

        def _count():
            return self.db.links.count_favorites()

        run_db(
            _count,
            description="count_favorites()",
            on_finished=lambda fav_count: self._on_favorites_counted(
                int(fav_count), [], link
            ),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def delete_link(self, link_id: int):
        """Удалить ссылку."""
        if not self._validate_link_id(link_id):
            return

        def _on_delete_finished(_):
            self._invalidate_cache()
            self.link_deleted.emit(link_id)
        
        run_db(
            lambda: self.links.delete_link(link_id),
            description=f"delete_link({link_id})",
            on_finished=_on_delete_finished,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @validate_link_form
    @handle_errors_with_default(None)
    def save_link(self, link_data: Dict) -> Optional[int]:
        """Сохранить ссылку (публичный метод)."""
        return self._save_link(link_data)

    @validate_link_form
    @handle_errors_with_default(None)
    def _save_link(self, link_data: Dict) -> Optional[int]:
        """Сохранить ссылку."""
        self.logger.warning("Using synchronous save_link; consider using save_link_async for async")

        result = self.links.create_or_update_link(link_data)
        if result and not link_data.get("id"):
            link_data["id"] = result

        self.logger.info("Link saved: %s", link_data.get("id", "[new]"))

        try:
            self._invalidate_cache()
            self.link_updated.emit(link_data)
        except Exception as emit_err:
            self.logger.warning("Failed to emit link_updated: %s", emit_err)

        return result

    @validate_link_form
    def save_link_async(self, link_data: Dict):
        """Асинхронно сохранить ссылку."""
        run_db(
            lambda: self.links.create_or_update_link(link_data),
            description="save_link_async",
            on_finished=lambda result: self._on_link_saved(link_data, result),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def _on_link_saved(self, link_data: Dict, result: int):
        if result and not link_data.get("id"):
            link_data["id"] = result
        self._invalidate_cache()
        self.link_updated.emit(link_data)
        self.logger.info("Link saved async: %s", link_data.get("id", "[new]"))

    def update_link_last_used(self, link_id: int):
        """Обновить время последнего использования ссылки."""
        if not self._validate_link_id(link_id):
            return

        def _on_last_used_updated(_):
            self._invalidate_cache()
            self.logger.debug("Link last_used updated: %s", link_id)
        
        run_db(
            lambda: self.links.update_last_used(link_id),
            description=f"update_link_last_used({link_id})",
            on_finished=_on_last_used_updated,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def toggle_favorite(self, link: Dict):
        """Переключить статус избранного для ссылки (исправлено для PyQt6)."""
        if (
            not isinstance(link, dict)
            or not isinstance(link.get("id"), int)
            or link["id"] <= 0
        ):
            raise ValueError("Invalid link data for toggle_favorite")

        link_id = link.get("id")
        
        # Проверяем, не выполняется ли уже операция для этой ссылки
        if link_id in self._pending_toggles:
            self.logger.debug(f"Toggle already in progress for link {link_id}")
            return
        
        self._pending_toggles.add(link_id)
        
        def _toggle_atomic():
            """Атомарная операция в одной БД-транзакции."""
            current_link = self.links.get_link_by_id(link_id)
            if not current_link:
                raise ValueError("Link not found")
            old_status = current_link.get("is_favorite", False)
            new_status = not old_status
            self.logger.debug(
                "Toggle favorite for link %s: %s -> %s", link_id, old_status, new_status
            )
            link_data = current_link.copy()
            link_data["is_favorite"] = new_status
            result = self.links.create_or_update_link(link_data)
            return result, link_data

        run_db(
            _toggle_atomic,
            description=f"toggle_favorite({link_id})",
            on_finished=lambda data: self._on_favorite_toggled(link_id, data[0], data[1]),
            on_error=lambda e: self._on_toggle_error(link_id, e),
        )

    def _on_favorite_toggled(self, link_id: int, result: int, link_data: Dict):
        """Обработка успешного переключения избранного."""
        self._pending_toggles.discard(link_id)
        self.logger.info(
            "Favorite status updated successfully, result ID: %s", result
        )
        self._invalidate_cache()
        self.count_favorites(link_data)
        
    def _on_toggle_error(self, link_id: int, error: Exception):
        """Обработка ошибки переключения избранного."""
        self._pending_toggles.discard(link_id)
        self._on_worker_error(str(error))

    @handle_errors_with_default([])
    def _get_recent_links(self, limit: int = DEFAULT_RECENT_LIMIT) -> List[Dict]:
        """Получить недавние ссылки."""
        self.logger.info("Using synchronous get_recent_links; consider using load_recent_links for async")
        if limit <= 0:
            self.logger.warning("Invalid limit for recent links: %s", limit)
            return []

        cache_key = f"recent_links_{limit}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        links = self.links.get_recent_links(limit)
        self._cache[cache_key] = links
        return links

    def load_recent_links(self, limit: int = DEFAULT_RECENT_LIMIT):
        """Асинхронно загрузить недавние ссылки."""
        if limit <= 0:
            self.logger.warning("Invalid limit for recent links: %s", limit)
            self.recent_links_loaded.emit([])
            return

        cache_key = f"recent_links_{limit}"
        if cache_key in self._cache:
            self.recent_links_loaded.emit(self._cache[cache_key])
            return

        run_db(
            lambda: self.links.get_recent_links(limit),
            description="load_recent_links",
            on_finished=lambda links: self._cache_links_and_emit(cache_key, links or [], self.recent_links_loaded.emit),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @handle_errors_with_default([])
    def _get_favorite_links(self) -> List[Dict]:
        """Получить избранные ссылки."""
        self.logger.info("Using synchronous get_favorite_links; consider using load_favorite_links for async")
        cache_key = "favorite_links"
        if cache_key in self._cache:
            return self._cache[cache_key]
        links = self.links.get_favorite_links()
        self._cache[cache_key] = links
        return links

    def load_favorite_links(self):
        """Асинхронно загрузить избранные ссылки."""
        cache_key = "favorite_links"
        if cache_key in self._cache:
            self.favorite_links_loaded.emit(self._cache[cache_key])
            return

        run_db(
            lambda: self.links.get_favorite_links(),
            description="load_favorite_links",
            on_finished=lambda links: self._cache_links_and_emit(cache_key, links or [], self.favorite_links_loaded.emit),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @handle_errors_with_default(False)
    def _clear_favorites(self) -> bool:
        """Очистить все избранные ссылки."""
        self.logger.info("Using synchronous clear_favorites; consider using clear_favorites_async for async")
        result = self.links.clear_favorites() or True
        self._invalidate_cache()
        self.logger.info("Избранные ссылки очищены")
        return result

    def clear_favorites_async(self):
        """Асинхронно очистить все избранные ссылки."""
        def _on_clear_finished(result):
            self._invalidate_cache()
            self.favorites_cleared.emit(result)
        
        run_db(
            lambda: self.links.clear_favorites() or True,
            description="clear_favorites_async",
            on_finished=_on_clear_finished,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @handle_errors_with_default(None)
    def _get_link_by_id(self, link_id: int) -> Optional[Dict]:
        """Получает ссылку по ID."""
        self.logger.info("Using synchronous get_link_by_id; consider using load_link_by_id for async")
        if not self._validate_link_id(link_id):
            return None

        cache_key = f"link_{link_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        link = self.links.get_link_by_id(link_id)
        self._cache[cache_key] = link
        return link

    def load_link_by_id(self, link_id: int):
        """Асинхронно получить ссылку по ID."""
        if not self._validate_link_id(link_id):
            self.link_by_id_loaded.emit({}, link_id)
            return

        cache_key = f"link_{link_id}"
        if cache_key in self._cache:
            self.link_by_id_loaded.emit(self._cache[cache_key], link_id)
            return

        run_db(
            lambda: self.links.get_link_by_id(link_id) or {},
            description=f"load_link_by_id({link_id})",
            on_finished=lambda link: self._cache_links_and_emit(cache_key, link, lambda l: self.link_by_id_loaded.emit(l, link_id)),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @handle_errors_with_default(0)
    def _get_next_position(self, category_id: int) -> int:
        """Получает следующую позицию для новой ссылки в категории."""
        self.logger.info("Using synchronous get_next_position; consider using load_next_position for async")
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                "Invalid category_id for get_next_position: %s", category_id
            )
            return 0

        cache_key = f"next_pos_{category_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        pos = self.links.get_next_position(category_id)
        self._cache[cache_key] = pos
        return pos

    def load_next_position(self, category_id: int):
        """Асинхронно получить следующую позицию."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                "Invalid category_id for load_next_position: %s", category_id
            )
            self.next_position_loaded.emit(0, category_id)
            return

        cache_key = f"next_pos_{category_id}"
        if cache_key in self._cache:
            self.next_position_loaded.emit(self._cache[cache_key], category_id)
            return

        run_db(
            lambda: self.links.get_next_position(category_id),
            description=f"load_next_position({category_id})",
            on_finished=lambda pos: self._cache_links_and_emit(cache_key, pos, lambda p: self.next_position_loaded.emit(p, category_id)),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @handle_errors_with_default(False)
    def _batch_update_links(self, links_data: List[Dict]) -> bool:
        """Выполняет пакетное обновление ссылок в транзакции."""
        self.logger.info("Using synchronous batch_update_links; consider using batch_update_links_async for async")
        if not links_data:
            self.logger.warning("Empty links_data for batch_update_links")
            return True

        for i, link_data in enumerate(links_data):
            if not isinstance(link_data, dict) or not link_data:
                self.logger.error("Invalid link data at index %s: %s", i, link_data)
                return False

        result = self.links.batch_update(links_data)
        self._invalidate_cache()
        return result

    def batch_update_links_async(self, links_data: List[Dict]):
        """Асинхронно выполнить пакетное обновление ссылок."""
        if not links_data:
            self.logger.warning("Empty links_data for batch_update_links_async")
            self.batch_updated.emit(True)
            return

        for i, link_data in enumerate(links_data):
            if not isinstance(link_data, dict) or not link_data:
                self.logger.error("Invalid link data at index %s: %s", i, link_data)
                self.batch_updated.emit(False)
                return

        def _on_batch_finished(result):
            self._invalidate_cache()
            self.batch_updated.emit(result)
        
        run_db(
            lambda: self.links.batch_update(links_data),
            description="batch_update_links_async",
            on_finished=_on_batch_finished,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    @validate_link_form
    def create_link_for_import(self, link_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую ссылку для импорта.

        Этот метод предназначен для создания ссылок во время импорта данных.
        Не эмитит UI сигналы, так как импорт происходит в фоновом режиме.

        Args:
            link_data: Словарь с данными ссылки

        Returns:
            ID созданной ссылки или None при ошибке
        """
        try:
            result_id = self.links.create_or_update_link(link_data)
            if result_id:
                self._invalidate_cache()
                self.logger.debug(
                    "Создана ссылка для импорта: %s", link_data.get("name", "без имени")
                )
                return result_id
            else:
                self.logger.warning("Не удалось создать ссылку для импорта")
                return None
        except Exception as e:
            self.logger.error(f"Error in create_link_for_import: {e}", exc_info=True)
            if not handle_db_error(e, self):
                raise
            return None

    # Приватные методы для валидации и вспомогательных операций

    def _validate_link_id(self, link_id: int) -> bool:
        """Валидация ID ссылки."""
        if not isinstance(link_id, int) or link_id <= 0:
            self.logger.warning("Invalid link_id: %s", link_id)
            return False
        return True

    @lru_cache(maxsize=32)
    def _get_all_links_safe(self) -> List[Dict]:
        """Безопасное получение всех ссылок для внутреннего использования."""
        return self.links.get_all_links()

    # Метод _invalidate_cache реализован в CacheMixin

    def _cache_links_and_emit(self, key: str, data: Any, emit_func):
        """Безопасное кэширование и эмиссия сигнала в GUI потоке."""
        def _safe_cache_and_emit():
            self._cache[key] = data
            emit_func(data)

        # Используем QTimer.singleShot для кросс-потоковой эмиссии
        QTimer.singleShot(0, _safe_cache_and_emit)

    # Слоты для обработки результатов воркеров (PyQt6 слоты)

    @pyqtSlot(list, int, int)
    def _on_links_loaded(self, links: List[Dict], category_id: int, task_id: int):
        """Обработка загруженных ссылок."""
        with self._tasks_lock:
            if task_id in self.pending_tasks:
                del self.pending_tasks[task_id]
                self.links_loaded.emit(links, category_id, task_id)

    @pyqtSlot(list)
    def _on_search_finished(self, search_results: List[Dict]):
        """Обработка результатов поиска."""
        self.search_results_ready.emit(search_results)

    @pyqtSlot(int, list, object)
    def _on_favorites_counted(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Обработка подсчета избранного."""
        self.favorites_counted.emit(fav_count, links, link)

    @pyqtSlot(str)
    def _on_worker_error(self, error_msg: str, task_id: Optional[int] = None):
        """Обработка ошибок воркеров."""
        self.logger.error("Worker error: %s", error_msg)
        self.error_occurred.emit(str(error_msg))
        if task_id and task_id in self.pending_tasks:
            with self._tasks_lock:
                del self.pending_tasks[task_id]