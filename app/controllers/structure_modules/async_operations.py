# app/controllers/structure_modules/async_operations.py

"""Модуль для асинхронных операций структуры."""

import logging
from typing import Any, Callable, Dict, List, Optional
import time

from app.models.db import Database
from app.utils.system.task_scheduler import get_task_scheduler
from app.utils.db.db_workers import (
    CountNestedObjectsWorker,
    CreateItemWorker,
    DeleteItemWorker,
    LoadCategoriesWorker,
    LoadSectionsWorker,
    LoadSpheresWorker,
    LoadStructureWorker,
    StructureWorkerSignals,
    UpdateItemWorker,
)


class AsyncOperations:
    """Класс для управления асинхронными операциями структуры."""
    
    def __init__(self, db: Database, logger: logging.Logger):
        self.db = db
        self.logger = logger
        # Единый глобальный планировщик задач вместо QThreadPool.globalInstance()
        self._scheduler = get_task_scheduler()
        self._worker_signals = StructureWorkerSignals()
        self._pending_tasks = {}
    
    def get_worker_signals(self) -> StructureWorkerSignals:
        """Возвращает объект сигналов воркеров для подключения."""
        return self._worker_signals
    
    def connect_signal_handlers(self, handlers: "AsyncSignalHandlers") -> None:
        """Подключает сигналы воркеров к обработчикам.

        Гарантирует согласованность подписок между `StructureWorkerSignals` и
        методами `AsyncSignalHandlers`.
        """
        # Загрузка
        self._worker_signals.spheres_loaded.connect(handlers.on_spheres_loaded)
        self._worker_signals.structure_loaded.connect(handlers.on_structure_loaded)
        self._worker_signals.sections_loaded.connect(handlers.on_sections_loaded)
        self._worker_signals.categories_loaded.connect(handlers.on_categories_loaded)
        # Поиск / ссылки
        self._worker_signals.search_results.connect(handlers.on_search_results)
        self._worker_signals.links_loaded.connect(handlers.on_links_loaded)
        self._worker_signals.link_info_finished.connect(handlers.on_link_info_finished)
        # Подсчет
        self._worker_signals.count_finished.connect(handlers.on_count_finished)
        # CRUD
        self._worker_signals.item_created.connect(handlers.on_item_created)
        self._worker_signals.item_updated.connect(handlers.on_item_updated)
        self._worker_signals.item_deleted.connect(handlers.on_item_deleted)
        # Состояние операций
        self._worker_signals.operation_started.connect(handlers.on_operation_started)
        self._worker_signals.operation_finished.connect(handlers.on_operation_finished)
        self._worker_signals.loading_started.connect(handlers.on_loading_started)
        # Обновление UI
        self._worker_signals.update_ui.connect(handlers.on_update_ui)
        self._worker_signals.update_favorites.connect(handlers.on_update_favorites)
        self._worker_signals.update_recent_links.connect(handlers.on_update_recent_links)
        # Ошибки
        self._worker_signals.error.connect(handlers.on_error)
        self._worker_signals.simple_error.connect(handlers.on_simple_error)

    def disconnect_signal_handlers(self, handlers: "AsyncSignalHandlers") -> None:
        """Отписывает обработчики от сигналов воркеров.

        Безопасно игнорирует уже отсоединённые связи.
        """
        try:
            self._worker_signals.spheres_loaded.disconnect(handlers.on_spheres_loaded)
            self._worker_signals.structure_loaded.disconnect(handlers.on_structure_loaded)
            self._worker_signals.sections_loaded.disconnect(handlers.on_sections_loaded)
            self._worker_signals.categories_loaded.disconnect(handlers.on_categories_loaded)
            self._worker_signals.search_results.disconnect(handlers.on_search_results)
            self._worker_signals.links_loaded.disconnect(handlers.on_links_loaded)
            self._worker_signals.link_info_finished.disconnect(handlers.on_link_info_finished)
            self._worker_signals.count_finished.disconnect(handlers.on_count_finished)
            self._worker_signals.item_created.disconnect(handlers.on_item_created)
            self._worker_signals.item_updated.disconnect(handlers.on_item_updated)
            self._worker_signals.item_deleted.disconnect(handlers.on_item_deleted)
            self._worker_signals.operation_started.disconnect(handlers.on_operation_started)
            self._worker_signals.operation_finished.disconnect(handlers.on_operation_finished)
            self._worker_signals.loading_started.disconnect(handlers.on_loading_started)
            self._worker_signals.update_ui.disconnect(handlers.on_update_ui)
            self._worker_signals.update_favorites.disconnect(handlers.on_update_favorites)
            self._worker_signals.update_recent_links.disconnect(handlers.on_update_recent_links)
            self._worker_signals.error.disconnect(handlers.on_error)
            self._worker_signals.simple_error.disconnect(handlers.on_simple_error)
        except Exception:
            # Тихое игнорирование частичных отписок
            pass
    
    def load_spheres_async(self) -> None:
        """Асинхронная загрузка всех сфер."""
        worker = LoadSpheresWorker(self.db, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info("Запущена асинхронная загрузка сфер")

    def load_structure_async(self, current_sphere_id: int) -> None:
        """Асинхронная загрузка структуры для сферы."""
        if not isinstance(current_sphere_id, int) or current_sphere_id <= 0:
            self.logger.error(f"Некорректный ID сферы: {current_sphere_id}")
            return
        worker = LoadStructureWorker(self.db, current_sphere_id, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущена асинхронная загрузка структуры для сферы {current_sphere_id}")

    def load_sections_async(self, sphere_id: int) -> None:
        """Асинхронная загрузка разделов для сферы."""
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.error(f"Некорректный ID сферы: {sphere_id}")
            return
        worker = LoadSectionsWorker(self.db, sphere_id, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущена асинхронная загрузка разделов для сферы {sphere_id}")

    def load_categories_async(self, section_id: int) -> None:
        """Асинхронная загрузка категорий для раздела."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(f"Некорректный ID раздела: {section_id}")
            return
        worker = LoadCategoriesWorker(self.db, section_id, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущена асинхронная загрузка категорий для раздела {section_id}")

    def create_section_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание раздела."""
        if not isinstance(data, dict):
            self.logger.error("Данные раздела должны быть словарём")
            return
        name = (data.get('name') or '').strip()
        sphere_id = data.get('sphere_id')
        if not name:
            self.logger.error("Имя раздела обязательно для создания")
            return
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.error("ID сферы обязателен и должен быть > 0 для создания раздела")
            return
        # Предчек дубликатов для улучшения UX: избегаем падения на ограничении уникальности
        try:
            existing = self.db.sections.get_sections(sphere_id) or []
            if any(str(row['name']).strip().lower() == name.lower() for row in existing):
                msg = f"Раздел с именем '{name}' уже существует в выбранной сфере"
                self.logger.info(msg)
                # Покажем пользователю понятное сообщение без запуска воркера
                self._worker_signals.simple_error.emit(msg)
                return
        except Exception as e:
            # Не блокируем создание при сбое проверки, только логируем
            self.logger.warning(f"Не удалось выполнить предчек дубликатов раздела: {e}")
        worker = CreateItemWorker(self.db, "section", data, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущено асинхронное создание раздела: {data.get('name', 'Unnamed')}")

    def create_category_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание категории."""
        if not isinstance(data, dict):
            self.logger.error("Данные категории должны быть словарём")
            return
        name = (data.get('name') or '').strip()
        section_id = data.get('section_id')
        if not name:
            self.logger.error("Имя категории обязательно для создания")
            return
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("ID раздела обязателен и должен быть > 0 для создания категории")
            return
        worker = CreateItemWorker(self.db, "category", data, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущено асинхронное создание категории: {data.get('name', 'Unnamed')}")

    def update_section_async(self, section_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление раздела."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(f"Некорректный ID раздела: {section_id}")
            return
        if not isinstance(data, dict):
            self.logger.error("Данные раздела должны быть словарём")
            return
        name = data.get('name')
        if name is not None and not str(name).strip():
            self.logger.error("Имя раздела должно быть непустой строкой")
            return
        worker = UpdateItemWorker(self.db, "section", section_id, data, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущено асинхронное обновление раздела {section_id}")

    def update_category_async(self, category_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление категории."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.error(f"Некорректный ID категории: {category_id}")
            return
        if not isinstance(data, dict):
            self.logger.error("Данные категории должны быть словарём")
            return
        name = data.get('name')
        if name is not None and not str(name).strip():
            self.logger.error("Имя категории должно быть непустой строкой")
            return
        worker = UpdateItemWorker(self.db, "category", category_id, data, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущено асинхронное обновление категории {category_id}")

    def delete_section_async(self, section_id: int) -> None:
        """Асинхронное удаление раздела."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(f"Некорректный ID раздела: {section_id}")
            return
        worker = DeleteItemWorker(self.db, "section", section_id, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущено асинхронное удаление раздела {section_id}")

    def delete_category_async(self, category_id: int) -> Optional[str]:
        """Асинхронное удаление категории с улучшенной обработкой ошибок
        
        Args:
            category_id: ID категории для удаления
            
        Returns:
            str: ID задачи или None при ошибке
        """
        try:
            if not isinstance(category_id, int) or category_id <= 0:
                error_msg = f"Invalid category ID: {category_id}"
                self.logger.error(error_msg)
                # Сигнал error ожидает (title: str, message: str)
                self._worker_signals.error.emit("Ошибка удаления", error_msg)
                return None
                
            self.logger.info(f"Starting async deletion of category {category_id}")
            self._worker_signals.operation_started.emit(f"delete_category_{category_id}")
            
            worker = DeleteItemWorker(
                self.db, "category", category_id, self._worker_signals
            )
            
            task_id = f"del_cat_{category_id}_{time.time()}"
            self._pending_tasks[task_id] = worker
            self._scheduler.submit_task(worker)
            
            return task_id
            
        except Exception as e:
            error_msg = f"Failed to start deletion worker: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            # Сигнал error ожидает (title: str, message: str)
            self._worker_signals.error.emit("Ошибка удаления", error_msg)
            return None

    def count_nested_objects_async(self, section_id: int) -> None:
        """Асинхронный подсчет вложенных объектов (категорий и ссылок)."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(f"Некорректный ID раздела: {section_id}")
            return
        worker = CountNestedObjectsWorker(self.db, section_id, self._worker_signals)
        self._scheduler.submit_task(worker)
        self.logger.info(f"Запущен асинхронный подсчет вложенных объектов для раздела {section_id}")


class AsyncSignalHandlers:
    """Класс для обработки сигналов от асинхронных операций."""
    
    def __init__(self, controller_instance):
        self.controller = controller_instance
        self.logger = controller_instance.logger
    
    def on_spheres_loaded(self, spheres: List[Dict[str, Any]]) -> None:
        """Обработчик завершения загрузки сфер."""
        try:
            self.logger.info(f"Загружено {len(spheres)} сфер")
            if hasattr(self.controller, 'spheres_loaded'):
                self.controller.spheres_loaded.emit(spheres)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_spheres_loaded: {e}", exc_info=True)

    def on_structure_loaded(self, structure: List[Dict[str, Any]], sphere_id: int) -> None:
        """Обработчик завершения загрузки структуры."""
        try:
            self.logger.info(f"Загружена структура для сферы {sphere_id}: {len(structure)} разделов")
            if hasattr(self.controller, 'structure_loaded'):
                self.controller.structure_loaded.emit(structure)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_structure_loaded: {e}", exc_info=True)

    def on_sections_loaded(self, sections: List[Dict[str, Any]], sphere_id: int) -> None:
        """Обработчик завершения загрузки разделов."""
        try:
            self.logger.info(f"Загружено {len(sections)} разделов для сферы {sphere_id}")
            if hasattr(self.controller, 'sections_loaded'):
                self.controller.sections_loaded.emit(sections, sphere_id)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_sections_loaded: {e}", exc_info=True)

    def on_categories_loaded(self, categories: List[Dict[str, Any]], section_id: int) -> None:
        """Обработчик завершения загрузки категорий.

        ВАЖНО: ретранслируем корректный сигнал `categories_loaded(categories, section_id)`,
        а не `section_selected`, чтобы UI получил именно событие загрузки категорий.
        """
        try:
            self.logger.info(f"Загружено {len(categories)} категорий для раздела {section_id}")
            if hasattr(self.controller, 'categories_loaded'):
                self.controller.categories_loaded.emit(categories, section_id)
            else:
                # Fallback на старое поведение, если новый сигнал не поддерживается контроллером
                if hasattr(self.controller, 'section_selected'):
                    self.controller.section_selected.emit(section_id, categories)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_categories_loaded: {e}", exc_info=True)

    # ===== CRUD =====
    def on_item_created(self, item_type: str, parent_id: int, item_data: Dict[str, Any]) -> None:
        """Создан элемент структуры."""
        try:
            name = item_data.get('name', 'Unknown') if isinstance(item_data, dict) else 'Unknown'
            self.logger.info(f"Создан {item_type} (parent_id={parent_id}): {name}")
            # Контроллер (StructureBusinessLogic) использует сигнал item_added
            if hasattr(self.controller, 'item_added'):
                self.controller.item_added.emit(item_type, parent_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == 'category':
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, '_invalidate_categories_cache'):
                        self.controller._invalidate_categories_cache(parent_id)
                    if hasattr(self.controller, 'async_operations'):
                        self.controller.async_operations.load_categories_async(parent_id)
                elif item_type == 'section':
                    sphere_id = getattr(self.controller, 'current_sphere_id', None)
                    if hasattr(self.controller, '_invalidate_structure_cache'):
                        self.controller._invalidate_structure_cache()
                    if isinstance(sphere_id, int) and sphere_id > 0 and hasattr(self.controller, 'async_operations'):
                        # Обновим и список разделов, и целиком структуру (дерево)
                        self.controller.async_operations.load_sections_async(sphere_id)
                        self.controller.async_operations.load_structure_async(sphere_id)
            except Exception as e2:
                self.logger.warning(f"Не удалось инициировать обновление UI после создания {item_type}: {e2}")
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_item_created: {e}", exc_info=True)

    def on_item_updated(self, item_type: str, item_id: int, item_data: Dict[str, Any]) -> None:
        """Обновлён элемент структуры."""
        try:
            self.logger.info(f"Обновлён {item_type} id={item_id}")
            if hasattr(self.controller, 'item_updated'):
                self.controller.item_updated.emit(item_type, item_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == 'category':
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, '_invalidate_categories_cache'):
                        self.controller._invalidate_categories_cache(item_data.get('section_id'))
                    if hasattr(self.controller, 'async_operations'):
                        self.controller.async_operations.load_categories_async(item_data.get('section_id'))
                elif item_type == 'section':
                    sphere_id = getattr(self.controller, 'current_sphere_id', None)
                    if hasattr(self.controller, '_invalidate_structure_cache'):
                        self.controller._invalidate_structure_cache()
                    if isinstance(sphere_id, int) and sphere_id > 0 and hasattr(self.controller, 'async_operations'):
                        self.controller.async_operations.load_sections_async(sphere_id)
            except Exception as e2:
                self.logger.warning(f"Не удалось инициировать обновление UI после обновления {item_type}: {e2}")
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_item_updated: {e}", exc_info=True)

    def on_item_deleted(self, item_type: str, item_id: int, old_data: Dict[str, Any]) -> None:
        """Удалён элемент структуры.

        Примечание: контроллер ожидает сигнатуру (str, int), поэтому `old_data`
        используется только для логирования и не передается далее.
        """
        try:
            self.logger.info(f"Удалён {item_type} id={item_id}")
            if hasattr(self.controller, 'item_deleted'):
                self.controller.item_deleted.emit(item_type, item_id)
            # Обновление после удаления
            try:
                if item_type == 'category':
                    section_id = (old_data or {}).get('section_id') if isinstance(old_data, dict) else None
                    if section_id and hasattr(self.controller, '_invalidate_categories_cache'):
                        self.controller._invalidate_categories_cache(section_id)
                    if section_id and hasattr(self.controller, 'async_operations'):
                        self.controller.async_operations.load_categories_async(section_id)
                elif item_type == 'section':
                    if hasattr(self.controller, '_invalidate_structure_cache'):
                        self.controller._invalidate_structure_cache()
                    sphere_id = getattr(self.controller, 'current_sphere_id', None)
                    if isinstance(sphere_id, int) and sphere_id > 0 and hasattr(self.controller, 'async_operations'):
                        self.controller.async_operations.load_sections_async(sphere_id)
            except Exception as e2:
                self.logger.warning(f"Не удалось инициировать обновление UI после удаления {item_type}: {e2}")
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_item_deleted: {e}", exc_info=True)

    def on_error(self, title: str, message: str) -> None:
        try:
            self.logger.error(f"{title}: {message}")
            # Новый сигнал контроллера
            if hasattr(self.controller, 'error_occurred'):
                self.controller.error_occurred.emit(title, message)
            # Совместимость со старым именем
            elif hasattr(self.controller, 'error'):
                self.controller.error.emit(title, message)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_error: {e}", exc_info=True)

    def on_simple_error(self, message: str) -> None:
        try:
            self.logger.error(message)
            if hasattr(self.controller, 'simple_error'):
                self.controller.simple_error.emit(message)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_simple_error: {e}", exc_info=True)

    def on_operation_started(self, description: str) -> None:
        try:
            self.logger.info(description)
            if hasattr(self.controller, 'operation_started'):
                self.controller.operation_started.emit(description)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_operation_started: {e}", exc_info=True)

    def on_operation_finished(self, description: str) -> None:
        try:
            self.logger.info(description)
            if hasattr(self.controller, 'operation_finished'):
                self.controller.operation_finished.emit(description)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_operation_finished: {e}", exc_info=True)

    def on_loading_started(self) -> None:
        try:
            self.logger.debug("Начата загрузка...")
            if hasattr(self.controller, 'loading_started'):
                self.controller.loading_started.emit()
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_loading_started: {e}", exc_info=True)

    # ===== Обновление UI =====
    def on_update_ui(self, category_id: int) -> None:
        try:
            self.logger.debug(f"Обновление UI для категории {category_id}")
            if hasattr(self.controller, 'update_ui'):
                self.controller.update_ui.emit(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_update_ui: {e}", exc_info=True)

    def on_update_favorites(self) -> None:
        try:
            self.logger.debug("Обновление избранного")
            if hasattr(self.controller, 'update_favorites'):
                self.controller.update_favorites.emit()
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_update_favorites: {e}", exc_info=True)

    def on_update_recent_links(self) -> None:
        try:
            self.logger.debug("Обновление недавних ссылок")
            if hasattr(self.controller, 'update_recent_links'):
                self.controller.update_recent_links.emit()
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_update_recent_links: {e}", exc_info=True)

    # ===== Поиск / Ссылки / Подсчёт =====
    def on_search_results(self, results: List[Dict[str, Any]]) -> None:
        try:
            self.logger.info(f"Результаты поиска: {len(results)}")
            if hasattr(self.controller, 'search_results'):
                self.controller.search_results.emit(results)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_search_results: {e}", exc_info=True)

    def on_links_loaded(self, links: List[Dict[str, Any]], category_id: int, task_id: int) -> None:
        try:
            self.logger.info(f"Загружено ссылок: {len(links)} (category_id={category_id}, task_id={task_id})")
            if hasattr(self.controller, 'links_loaded'):
                self.controller.links_loaded.emit(links, category_id, task_id)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_links_loaded: {e}", exc_info=True)

    def on_link_info_finished(self, info: Dict[str, Any]) -> None:
        try:
            self.logger.debug("Получена информация о ссылке")
            if hasattr(self.controller, 'link_info_finished'):
                self.controller.link_info_finished.emit(info)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_link_info_finished: {e}", exc_info=True)

    def on_count_finished(self, fav_count: int, links: List[Dict[str, Any]], link: object) -> None:
        try:
            self.logger.info(f"Подсчёт избранных завершён: {fav_count}")
            if hasattr(self.controller, 'count_finished'):
                self.controller.count_finished.emit(fav_count, links, link)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_count_finished: {e}", exc_info=True)
