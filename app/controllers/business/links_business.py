# app/controllers/links_business.py

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.utils.db.db_error_handler import handle_db_error
from app.controllers.business.links_repository_adapter import LinksRepositoryAdapter
from app.utils.validators.validate_link_payload import (
    validate_link_payload,
    ValidationError,
)
from app.controllers.business.link_async_controller import LinkAsyncController
from app.utils.validators.links_business_validators import (
    validate_toggle_favorite_input,
    validate_batch_update_links_input,
)


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
        int
    )  # int - количество избранных
    link_updated: pyqtSignal = pyqtSignal(dict)  # Dict - обновленная ссылка
    error_occurred: pyqtSignal = pyqtSignal(str)  # str - сообщение об ошибке

    def __init__(
        self,
        *,
        repository: LinksRepositoryAdapter,
        async_controller: LinkAsyncController,
        logger=None,
    ):
        super().__init__()
        # Единый слой доступа к данным
        self.repo = repository
        # Единый контроллер асинхронных задач
        self.async_controller = async_controller
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        # worker-сигналы не требуются: используем собственные сигналы класса + run_db

    def shutdown(self, timeout: int = 2000):
        """Корректное завершение работы.

        Прокидывает таймаут ожидания во внутренний `LinkAsyncController.shutdown(timeout_ms)`,
        чтобы корректно дождаться завершения фоновых задач и очистки пулов потоков.
        """
        try:
            # Делегируем завершение асинхронному контроллеру
            if hasattr(self, "async_controller") and self.async_controller:
                self.async_controller.shutdown(timeout_ms=timeout)
            self.logger.debug("LinksBusinessLogic shutdown completed")
        except Exception as e:
            self.logger.error(f"Error during LinksBusinessLogic shutdown: {e}")

    def load_links(self, category_id: int):
        """Загрузить ссылки для категории (асинхронно через контроллер)."""
        # Делегируем управление задачей контроллеру
        self.async_controller.load_links_async(
            category_id=category_id,
            fetch_fn=lambda: self.repo.fetch_links(category_id),
            on_loaded=self._on_links_loaded,
            on_error=self._on_worker_error,
        )

    def search_links(self, query: str) -> Optional[int]:
        """Поиск ссылок по запросу (асинхронно через контроллер). Возвращает task_id или None для пустого запроса."""
        if not query.strip():
            return None
        return self.async_controller.search_links_async(
            query=query,
            search_fn=lambda: self.repo.search_links(query),
            on_finished=self._on_search_finished,
            on_error=self._on_worker_error,
        )

    def update_link_order(self, link_ids: list):
        """Обновить порядок ссылок."""
        if not link_ids:
            return

        self.logger.debug(f"Updating order for {len(link_ids)} links")

        try:
            self.repo.reorder(link_ids)
            self.logger.debug(f"Updated order for {len(link_ids)} links")
        except Exception as e:
            self.logger.error(f"Error updating link order: {e}")
            if not handle_db_error(e, self):
                raise

    def count_favorites(self) -> int:
        """Подсчитать количество избранных ссылок (асинхронно через контроллер). Возвращает task_id.

        Передаём только функцию подсчёта; UI больше не получает снапшот ссылок.
        """
        return self.async_controller.count_favorites_async(
            count_fn=lambda: self.repo.count_favorites(),
            on_finished=self._on_favorites_counted,
            on_error=self._on_worker_error,
        )

    def get_links_for_category(self, category_id: int) -> List[Dict]:
        """Получить ссылки для категории синхронно."""
        try:
            return self.repo.get_links_for_category(category_id)
        except Exception as e:
            self.logger.error(
                f"Ошибка получения ссылок для категории {category_id}: {e}"
            )
            if not handle_db_error(e, self):
                raise
            return []

    def delete_link(self, link_id: int):
        """Удалить ссылку."""
        if not self._validate_link_id(link_id):
            return

        try:
            self.repo.delete_link(link_id)
            self.logger.info(f"Link deleted: {link_id}")
        except Exception as e:
            self.logger.error(f"Ошибка удаления ссылки {link_id}: {e}")
            if not handle_db_error(e, self):
                raise

    def save_link(self, link_data: Dict) -> int:
        """Сохранить ссылку."""
        # Централизованная валидация входных данных
        try:
            validated = validate_link_payload(link_data)
        except ValidationError as ve:
            raise ValueError(str(ve))

        try:
            result = self.repo.create_or_update_link(validated)
            # Гарантируем, что в link_data есть актуальный id (для новых ссылок)
            if result and not validated.get("id"):
                validated["id"] = result

            self.logger.info(f"Link saved: {link_data.get('id', '[new]')}")

            # Уведомляем UI о том, что ссылка сохранена/обновлена
            try:
                self.link_updated.emit(validated)
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
            self.repo.update_last_used(link_id)
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
        # Централизованная валидация входных данных
        validate_toggle_favorite_input(link)

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

            # Обновляем счетчик избранного
            self.count_favorites()

        except Exception as e:
            self.logger.error(f"Ошибка при сохранении избранного: {e}")
            raise

    def get_recent_links(self, limit: int = 10) -> List[Dict]:
        """Получить недавние ссылки."""
        if limit <= 0:
            self.logger.warning(f"Invalid limit for recent links: {limit}")
            return []

        try:
            return self.repo.get_recent_links(limit)
        except Exception as e:
            self.logger.error(f"Ошибка получения недавних ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return []

    def get_favorite_links(self) -> List[Dict]:
        """Получить избранные ссылки."""
        try:
            return self.repo.get_favorite_links()
        except Exception as e:
            self.logger.error(f"Ошибка получения избранных ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return []

    def clear_favorites(self) -> int:
        """Очистить все избранные ссылки. Возвращает количество удалённых записей."""
        try:
            deleted_count = int(self.repo.clear_favorites() or 0)
            self.logger.info(f"Избранные ссылки очищены: удалено {deleted_count}")
            return deleted_count
        except Exception as e:
            self.logger.error(f"Ошибка очистки избранных ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return 0

    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        """Получает ссылку по ID."""
        if not self._validate_link_id(link_id):
            return None

        try:
            return self.repo.get_link_by_id(link_id)
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
            return self.repo.get_next_position(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка получения следующей позиции: {e}")
            if not handle_db_error(e, self):
                raise
            return 0

    def batch_update_links(self, links_data: List[Dict]) -> bool:
        """Выполняет пакетное обновление ссылок в транзакции."""
        # Централизованная валидация входных данных
        try:
            if not validate_batch_update_links_input(links_data):
                return False
        except ValidationError as ve:
            self.logger.error(f"Invalid batch update payload: {ve}")
            return False

        try:
            return self.repo.batch_update(links_data)
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
        # Централизованная валидация
        try:
            validated = validate_link_payload(link_data)
        except ValidationError as ve:
            self.logger.warning(f"Invalid link data for import: {ve}")
            return None

        try:
            # Используем адаптер/сервисный слой
            result_id = self.repo.create_or_update_link(validated)
            if result_id:
                self.logger.debug(
                    f"Создана ссылка для импорта: {validated.get('name', 'без имени')}"
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

    

    # Слоты для обработки результатов воркеров

    def _on_links_loaded(self, links: List[Dict], category_id: int, task_id: int):
        """Обработка загруженных ссылок."""
        # Асинхронный контроллер сам управляет pending задачами.
        # Здесь просто эмитим результат для UI без проверки legacy pending_tasks.
        self.links_loaded.emit(links, category_id, task_id)

    def _on_search_finished(self, search_results: List[Dict]):
        """Обработка результатов поиска."""
        self.search_results_ready.emit(search_results)

    def _on_favorites_counted(self, fav_count: int):
        """Обработка подсчёта избранного: эмитим только число."""
        self.favorites_counted.emit(fav_count)

    def _on_worker_error(self, error_msg: str):
        """Обработка ошибок воркеров."""
        self.logger.error(f"Worker error: {error_msg}")
        self.error_occurred.emit(str(error_msg))
