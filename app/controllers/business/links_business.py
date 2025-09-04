# app/controllers/links_business.py

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services import LinksService
from app.utils.db.api import run_db
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.synchronization import tasks_lock


class LinksBusinessLogic(QObject):
    """Бизнес-логика для работы со ссылками."""

    # Сигналы для уведомления UI
    links_loaded: pyqtSignal = pyqtSignal(
        list, int, int
    )  # List[Dict], int, int - ссылки, ID категории, ID задачи
    search_results_ready: pyqtSignal = pyqtSignal(
        list
    )  # List[Dict] - результаты поиска
    favorites_counted: pyqtSignal = pyqtSignal(
        int, list, object
    )  # int, List[Dict], Optional[Dict] - количество, ссылки, текущая ссылка
    link_updated: pyqtSignal = pyqtSignal(dict)  # Dict - обновленная ссылка
    error_occurred: pyqtSignal = pyqtSignal(str)  # str - сообщение об ошибке

    def __init__(self, db: Database, logger=None):
        super().__init__()
        self.db = db
        # Используем унифицированную LinkModel напрямую из database
        self.links_model = db.links
        # Сервисный слой поверх репозитория для снижения дублирования и транзакций
        self.links = LinksService(db)
        # Единый глобальный планировщик задач
        self.scheduler = get_task_scheduler()
        self.pending_tasks = set()
        self.task_counter = 0
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # worker-сигналы не требуются: используем собственные сигналы класса + run_db

    def shutdown(self, timeout: int = 2000):
        """Корректное завершение работы."""
        try:
            # Ждём завершения задач через единый пул
            self.scheduler.get_thread_pool().waitForDone(timeout)
            self.logger.debug("LinksBusinessLogic shutdown completed")
        except Exception as e:
            self.logger.error(f"Error during LinksBusinessLogic shutdown: {e}")

    def load_links(self, category_id: int):
        """Загрузить ссылки для категории."""
        self.task_counter += 1
        task_id = self.task_counter

        with tasks_lock:
            self.pending_tasks.add(task_id)

        self.logger.debug(
            f"Loading links for category {category_id}, task_id={task_id}"
        )

        def _fetch():
            rows = self.db.links.get_links(category_id)
            return rows or []

        run_db(
            _fetch,
            description=f"load_links(category_id={category_id})",
            on_finished=lambda links: self._on_links_loaded(links, category_id, task_id),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def get_links(self, category_id: int) -> List[Dict]:
        """Синхронно вернуть ссылки для категории (унифицированный метод)."""
        try:
            return self.links.get_links(category_id)
        except Exception as e:
            self.logger.error(
                f"Ошибка получения ссылок для категории {category_id}: {e}"
            )
            if not handle_db_error(e, self):
                raise
            return []

    def search_links(self, query: str):
        """Поиск ссылок по запросу."""
        if not query.strip():
            return

        self.logger.debug(f"Searching links for query: {query}")

        run_db(
            lambda: self.db.links.search_links(query) or [],
            description=f"search_links(query={query!r})",
            on_finished=self._on_search_finished,
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    def update_link_order(self, link_ids: list):
        """Обновить порядок ссылок."""
        if not link_ids:
            return

        self.logger.debug(f"Updating order for {len(link_ids)} links")

        try:
            self.links.reorder(link_ids)
            self.logger.debug(f"Updated order for {len(link_ids)} links")
        except Exception as e:
            self.logger.error(f"Error updating link order: {e}")
            if not handle_db_error(e, self):
                raise

    def count_favorites(self, link: Optional[Dict] = None):
        """Подсчитать количество избранных ссылок."""
        def _count():
            return self.db.links.count_favorites()

        run_db(
            _count,
            description="count_favorites()",
            # Передаём пустой список вместо полной выборки ссылок, чтобы не грузить БД/память
            on_finished=lambda fav_count: self._on_favorites_counted(
                int(fav_count), [], link
            ),
            on_error=lambda e: self._on_worker_error(str(e)),
        )

    

    def delete_link(self, link_id: int):
        """Удалить ссылку."""
        if not self._validate_link_id(link_id):
            return

        try:
            self.links.delete_link(link_id)
            self.logger.info(f"Link deleted: {link_id}")
        except Exception as e:
            self.logger.error(f"Ошибка удаления ссылки {link_id}: {e}")
            if not handle_db_error(e, self):
                raise

    def save_link(self, link_data: Dict) -> int:
        """Сохранить ссылку."""
        # Строгая валидация через общий валидатор + проверка category_id
        if not isinstance(link_data, dict):
            raise ValueError("Invalid link data provided: not a dict")
        # Ленивая загрузка валидатора, чтобы избежать циклических импортов при старте
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

        try:
            result = self.links.create_or_update_link(link_data)
            # Гарантируем, что в link_data есть актуальный id (для новых ссылок)
            if result and not link_data.get("id"):
                link_data["id"] = result

            self.logger.info(f"Link saved: {link_data.get('id', '[new]')}")

            # Уведомляем UI о том, что ссылка сохранена/обновлена
            try:
                self.link_updated.emit(link_data)
            except Exception as emit_err:
                # Не прерываем основной поток, просто логируем
                self.logger.warning(f"Failed to emit link_updated: {emit_err}")

            return result
        except Exception as e:
            self.logger.error(
                f"Ошибка сохранения ссылки {link_data.get('id', '[new]')}: {e}"
            )
            if not handle_db_error(e, self):
                raise

    def update_link_last_used(self, link_id: int):
        """Обновить время последнего использования ссылки."""
        if not self._validate_link_id(link_id):
            return

        try:
            self.links.update_last_used(link_id)
            self.logger.debug(f"Link last_used updated: {link_id}")
        except Exception as e:
            self.logger.error(
                f"Ошибка обновления времени использования ссылки {link_id}: {e}"
            )
            if not handle_db_error(e, self):
                # Не прерываем выполнение для этой операции
                pass

    def toggle_favorite(self, link: Dict):
        """Переключить статус избранного для ссылки."""
        # Для переключения избранного достаточно валидного словаря и корректного id
        if not isinstance(link, dict) or not isinstance(link.get("id"), int) or link["id"] <= 0:
            raise ValueError("Invalid link data for toggle_favorite")

        old_status = link.get("is_favorite", False)
        new_status = not old_status
        link_id = link.get("id")

        self.logger.debug(
            f"Toggle favorite for link {link_id}: {old_status} -> {new_status}"
        )

        link_data = link.copy()
        link_data["is_favorite"] = new_status

        try:
            result = self.save_link(link_data)
            self.logger.info(
                f"Favorite status updated successfully, result ID: {result}"
            )

            # Сигнал link_updated уже эмитится внутри save_link; не дублируем

            # Обновляем счетчик избранного
            self.count_favorites(link_data)

        except Exception as e:
            self.logger.error(f"Ошибка при сохранении избранного: {e}")
            raise

    def get_recent_links(self, limit: int = 10) -> List[Dict]:
        """Получить недавние ссылки."""
        if limit <= 0:
            self.logger.warning(f"Invalid limit for recent links: {limit}")
            return []

        try:
            return self.links.get_recent_links(limit)
        except Exception as e:
            self.logger.error(f"Ошибка получения недавних ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return []

    def get_favorite_links(self) -> List[Dict]:
        """Получить избранные ссылки."""
        try:
            return self.links.get_favorite_links()
        except Exception as e:
            self.logger.error(f"Ошибка получения избранных ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return []

    def clear_favorites(self) -> bool:
        """Очистить все избранные ссылки."""
        try:
            result = self.links.clear_favorites() or True
            self.logger.info("Избранные ссылки очищены")
            return result
        except Exception as e:
            self.logger.error(f"Ошибка очистки избранных ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return False

    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        """Получает ссылку по ID."""
        if not self._validate_link_id(link_id):
            return None

        try:
            return self.links.get_link_by_id(link_id)
        except Exception as e:
            self.logger.error(f"Ошибка получения ссылки {link_id}: {e}")
            if not handle_db_error(e, self):
                raise
            return None

    def get_next_position(self, category_id: int) -> int:
        """Получает следующую позицию для новой ссылки в категории."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                f"Invalid category_id for get_next_position: {category_id}"
            )
            return 0

        try:
            return self.links.get_next_position(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка получения следующей позиции: {e}")
            if not handle_db_error(e, self):
                raise
            return 0

    def batch_update_links(self, links_data: List[Dict]) -> bool:
        """Выполняет пакетное обновление ссылок в транзакции."""
        if not links_data:
            self.logger.warning("Empty links_data for batch_update_links")
            return True

        # Валидация всех ссылок перед обновлением
        for i, link_data in enumerate(links_data):
            # Нестрогая проверка: ожидаем непустые словари записей
            if not isinstance(link_data, dict) or not link_data:
                self.logger.error(f"Invalid link data at index {i}: {link_data}")
                return False

        try:
            return self.links.batch_update(links_data)
        except Exception as e:
            self.logger.error(f"Ошибка пакетного обновления ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return False

    def create_link_for_import(self, link_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую ссылку для импорта.

        Этот метод предназначен для создания ссылок во время импорта данных.
        Не эмитит UI сигналы, так как импорт происходит в фоновом режиме.

        Args:
            link_data: Словарь с данными ссылки

        Returns:
            ID созданной ссылки или None при ошибке
        """
        # Строгая валидация для импорта
        if not isinstance(link_data, dict):
            self.logger.warning(f"Invalid link data for import: {link_data}")
            return None
        # Ленивая загрузка валидатора, чтобы избежать циклических импортов при старте
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
            self.logger.warning(f"Invalid link data for import: {link_data}")
            return None

        try:
            # Используем сервисный слой (UnitOfWork внутри LinksService)
            result_id = self.links.create_or_update_link(link_data)
            if result_id:
                self.logger.debug(
                    f"Создана ссылка для импорта: {link_data.get('name', 'без имени')}"
                )
                return result_id
            else:
                self.logger.warning("Не удалось создать ссылку для импорта")
                return None
        except Exception as e:
            self.logger.error(f"Ошибка создания ссылки для импорта: {e}")
            if not handle_db_error(e, self):
                raise
            return None

    # Приватные методы для валидации и вспомогательных операций

    def _validate_link_id(self, link_id: int) -> bool:
        """Валидация ID ссылки."""
        if not isinstance(link_id, int) or link_id <= 0:
            self.logger.warning(f"Invalid link_id: {link_id}")
            return False
        return True

    

    def _get_all_links_safe(self) -> List[Dict]:
        """Безопасное получение всех ссылок для внутреннего использования."""
        try:
            return self.links.get_all_links()
        except Exception as e:
            self.logger.error(f"Error getting all links: {e}")
            return []

    # Слоты для обработки результатов воркеров

    def _on_links_loaded(self, links: List[Dict], category_id: int, task_id: int):
        """Обработка загруженных ссылок."""
        with tasks_lock:
            if task_id in self.pending_tasks:
                self.pending_tasks.remove(task_id)
                self.links_loaded.emit(links, category_id, task_id)

    def _on_search_finished(self, search_results: List[Dict]):
        """Обработка результатов поиска."""
        self.search_results_ready.emit(search_results)

    def _on_favorites_counted(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Обработка подсчета избранного."""
        self.favorites_counted.emit(fav_count, links, link)

    def _on_worker_error(self, error_msg: str):
        """Обработка ошибок воркеров."""
        self.logger.error(f"Worker error: {error_msg}")
        self.error_occurred.emit(str(error_msg))
