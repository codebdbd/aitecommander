# app/controllers/links_business.py

import logging
import threading
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.db import Database
from app.models.link_model import LinkModel
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.db_workers import (
    CountFavoritesWorker,
    LoadLinksWorker,
    SearchLinksWorker,
)
from app.utils.db.db_workers import StructureWorkerSignals as CountFavoritesWorkerSignals
from app.utils.db.db_workers import StructureWorkerSignals as LoadLinksWorkerSignals
from app.utils.db.db_workers import StructureWorkerSignals as SearchLinksWorkerSignals
from app.utils.db.db_workers import StructureWorkerSignals as UpdateLinkWorkerSignals
from app.utils.db.db_workers import UpdateLinkWorker
from app.utils.db.synchronization import tasks_lock
from app.utils.system.task_scheduler import LimitedThreadPool


class LinksBusinessLogic(QObject):
    """Бизнес-логика для работы со ссылками."""
    
    # Сигналы для уведомления UI
    links_loaded: pyqtSignal = pyqtSignal(list, int, int)  # List[Dict], int, int - ссылки, ID категории, ID задачи
    search_results_ready: pyqtSignal = pyqtSignal(list)  # List[Dict] - результаты поиска
    favorites_counted: pyqtSignal = pyqtSignal(int, list, object)  # int, List[Dict], Optional[Dict] - количество, ссылки, текущая ссылка
    link_updated: pyqtSignal = pyqtSignal(dict)  # Dict - обновленная ссылка
    error_occurred: pyqtSignal = pyqtSignal(str)  # str - сообщение об ошибке
    
    def __init__(self, db: Database, logger=None):
        super().__init__()
        self.db = db
        # Используем унифицированную LinkModel напрямую из database
        self.links_model = db.links
        self.thread_pool = LimitedThreadPool(max_threads=2)
        self.pending_tasks = set()
        self.task_counter = 0
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._setup_worker_signals()
    
    def _setup_worker_signals(self):
        """Настройка сигналов для воркеров."""
        # Сигналы для загрузки ссылок
        self.load_signals = LoadLinksWorkerSignals()
        self.load_signals.links_loaded.connect(self._on_links_loaded)
        self.load_signals.error.connect(self._on_worker_error)
        
        # Сигналы для поиска
        self.search_signals = SearchLinksWorkerSignals()
        self.search_signals.search_results.connect(self._on_search_finished)
        self.search_signals.error.connect(self._on_worker_error)
        
        # Сигналы для обновления ссылок
        self.update_signals = UpdateLinkWorkerSignals()
        self.update_signals.update_ui.connect(self._on_update_finished)
        self.update_signals.error.connect(self._on_worker_error)
        
        # Сигналы для подсчета избранного
        self.count_signals = CountFavoritesWorkerSignals()
        self.count_signals.count_finished.connect(self._on_favorites_counted)
        self.count_signals.error.connect(self._on_worker_error)
    
    def shutdown(self, timeout: int = 2000):
        """Корректное завершение работы."""
        try:
            self.thread_pool.waitForDone(timeout)
            self.logger.debug("LinksBusinessLogic shutdown completed")
        except Exception as e:
            self.logger.error(f"Error during LinksBusinessLogic shutdown: {e}")
    
    def load_links(self, category_id: int):
        """Загрузить ссылки для категории."""
        self.task_counter += 1
        task_id = self.task_counter
        
        with tasks_lock:
            self.pending_tasks.add(task_id)
        
        self.logger.debug(f"Loading links for category {category_id}, task_id={task_id}")
        
        worker = LoadLinksWorker(
            self.db,
            category_id,
            self.load_signals,
            task_id
        )
        self.thread_pool.start(worker)
    
    def search_links(self, query: str):
        """Поиск ссылок по запросу."""
        if not query.strip():
            return
        
        self.logger.debug(f"Searching links for query: {query}")
        
        worker = SearchLinksWorker(
            self.db,
            query,
            self.search_signals
        )
        self.thread_pool.start(worker)
    
    def update_link_order(self, link_ids: list):
        """Обновить порядок ссылок."""
        if not link_ids:
            return
        
        # UpdateLinkWorker ожидает link, но мы передаем link_ids
        self.logger.debug(f"Updating link order: {link_ids}")
        # Нужно создать отдельный воркер для обновления порядка
        # Пока просто обновляем синхронно
        try:
            self.links_model.update_link_order(link_ids)
            logging.debug(f"Updated order for {len(link_ids)} links")
        except Exception as e:
            logging.error(f"Error updating link order: {e}")
    
    def count_favorites(self, link: Optional[Dict] = None):
        """Подсчитать количество избранных ссылок."""
        # CountFavoritesWorker ожидает (db, links, link, signals)
        # Получаем список всех ссылок
        all_links = self.links_model.get_all_links()
        worker = CountFavoritesWorker(
            self.db,
            all_links,
            link,
            self.count_signals
        )
        self.thread_pool.start(worker)
    
    def get_links_for_category(self, category_id: int) -> List[Dict]:
        """Получить ссылки для категории синхронно."""
        return self.links_model.get_links(category_id)
    
    def delete_link(self, link_id: int):
        """Удалить ссылку."""
        try:
            self.links_model.delete_link(link_id)
            self.logger.info(f"Link deleted: {link_id}")
        except Exception as e:
            # Используем централизованный обработчик ошибок
            self.logger.error(f"Ошибка удаления ссылки {link_id}: {e}")
            if not handle_db_error(e, self):
                raise
    
    def save_link(self, link_data: Dict) -> int:
        """Сохранить ссылку."""
        try:
            result = self.links_model.upsert_link(link_data)
            self.logger.info(f"Link saved: {link_data.get('id', '[new]')}")
            return result
        except Exception as e:
            # Используем централизованный обработчик ошибок
            self.logger.error(f"Ошибка сохранения ссылки {link_data.get('id', '[new]')}: {e}")
            if not handle_db_error(e, self):
                raise

    def update_link_last_used(self, link_id: int):
        """Обновить время последнего использования ссылки."""
        try:
            self.links_model.update_link_last_used(link_id)
            self.logger.debug(f"Link last_used updated: {link_id}")
        except Exception as e:
            # Используем централизованный обработчик ошибок
            self.logger.error(f"Ошибка обновления времени использования ссылки {link_id}: {e}")
            if not handle_db_error(e, self):
                pass

    
    def toggle_favorite(self, link: Dict):
        """Переключить статус избранного для ссылки."""
        old_status = link.get("is_favorite", False)
        new_status = not old_status
        link_id = link.get('id')
        link_name = link.get('name', 'Без названия')
        
        self.logger.info(f"Бизнес-логика toggle_favorite:")
        self.logger.info(f"  - ID ссылки: {link_id}")
        self.logger.info(f"  - Название: '{link_name}'")
        self.logger.info(f"  - Старый статус: {old_status}")
        self.logger.info(f"  - Новый статус: {new_status}")
        
        link_data = link.copy()
        link_data["is_favorite"] = new_status
        
        try:
            result = self.save_link(link_data)
            self.logger.info(f"Сохранение в БД успешно, ID результата: {result}")
            
            # Отправляем сигнал об обновлении ссылки
            self.link_updated.emit(link_data)
            self.logger.info(f"Сигнал link_updated отправлен")
            
            # Обновляем счетчик избранного
            self.count_favorites(link_data)
            
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении избранного: {e}")
            raise
    
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
    
    def _on_update_finished(self, category_id: int):
        """Обработка завершения обновления."""
        self.logger.debug(f"Links order updated successfully for category {category_id}")
    
    def _on_favorites_counted(self, fav_count: int, links: List[Dict], link: Optional[Dict]):
        """Обработка подсчета избранного."""
        self.favorites_counted.emit(fav_count, links, link)
    
    def _on_worker_error(self, error_msg: str):
        """Обработка ошибок воркеров."""
        self.logger.error(f"Worker error: {error_msg}")
        self.error_occurred.emit(error_msg)
    
    def get_recent_links(self, limit: int = 10) -> List[Dict]:
        """Получить недавние ссылки."""
        try:
            return self.links_model.get_recent_links(limit)
        except Exception as e:
            self.logger.error(f"Ошибка получения недавних ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return []
    
    def get_favorite_links(self) -> List[Dict]:
        """Получить избранные ссылки."""
        try:
            return self.links_model.get_favorite_links()
        except Exception as e:
            self.logger.error(f"Ошибка получения избранных ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return []
    
    def clear_favorites(self) -> bool:
        """Очистить все избранные ссылки."""
        try:
            result = self.links_model.clear_favorites()
            self.logger.info("Избранные ссылки очищены")
            return result
        except Exception as e:
            self.logger.error(f"Ошибка очистки избранных ссылок: {e}")
            if not handle_db_error(e, self):
                raise
            return False
    
    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        """Получает ссылку по ID."""
        try:
            return self.links_model.get_link_by_id(link_id)
        except Exception as e:
            self.logger.error(f"Ошибка получения ссылки {link_id}: {e}")
            if not handle_db_error(e, self):
                raise
            return None
    
    def get_next_position(self, category_id: int) -> int:
        """Получает следующую позицию для новой ссылки в категории."""
        try:
            return self.links_model.get_next_position(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка получения следующей позиции: {e}")
            if not handle_db_error(e, self):
                raise
            return 0
    
    def get_links_for_category(self, category_id: int) -> List[Dict]:
        """Получает все ссылки для категории."""
        try:
            return self.links_model.get_links_for_category(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка получения ссылок для категории {category_id}: {e}")
            if not handle_db_error(e, self):
                raise
            return []
    
    def batch_update_links(self, links_data: List[Dict]) -> bool:
        """Выполняет пакетное обновление ссылок в транзакции."""
        try:
            return self.links_model.batch_update_links(links_data)
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
        try:
            result_id = self.links_model.upsert_link(link_data)
            if result_id:
                self.logger.info(f"Создана ссылка для импорта: {link_data.get('name', 'без имени')}")
                return result_id
            else:
                self.logger.warning("Не удалось создать ссылку для импорта")
                return None
        except Exception as e:
            self.logger.error(f"Ошибка создания ссылки для импорта: {e}")
            if not handle_db_error(e, self):
                raise
            return None
