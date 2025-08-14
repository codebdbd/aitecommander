# app/controllers/structure_modules/async_operations.py

"""Модуль для асинхронных операций структуры."""

import logging
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QThreadPool

from app.models.db import Database
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
        self._thread_pool = QThreadPool.globalInstance()
        self._worker_signals = StructureWorkerSignals()
    
    def get_worker_signals(self):
        """Возвращает объект сигналов воркеров для подключения."""
        return self._worker_signals
    
    def load_spheres_async(self) -> None:
        """Асинхронная загрузка всех сфер."""
        worker = LoadSpheresWorker(self.db, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug("Запущена асинхронная загрузка сфер")

    def load_structure_async(self, current_sphere_id: int) -> None:
        """Асинхронная загрузка структуры для сферы."""
        worker = LoadStructureWorker(self.db, current_sphere_id, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущена асинхронная загрузка структуры для сферы {current_sphere_id}")

    def load_sections_async(self, sphere_id: int) -> None:
        """Асинхронная загрузка разделов для сферы."""
        worker = LoadSectionsWorker(self.db, sphere_id, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущена асинхронная загрузка разделов для сферы {sphere_id}")

    def load_categories_async(self, section_id: int) -> None:
        """Асинхронная загрузка категорий для раздела."""
        worker = LoadCategoriesWorker(self.db, section_id, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущена асинхронная загрузка категорий для раздела {section_id}")

    def create_section_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание раздела."""
        worker = CreateItemWorker(self.db, "section", data, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущено асинхронное создание раздела: {data.get('name', 'Unnamed')}")

    def create_category_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание категории."""
        worker = CreateItemWorker(self.db, "category", data, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущено асинхронное создание категории: {data.get('name', 'Unnamed')}")

    def update_section_async(self, section_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление раздела."""
        worker = UpdateItemWorker(self.db, "section", section_id, data, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущено асинхронное обновление раздела {section_id}")

    def update_category_async(self, category_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление категории."""
        worker = UpdateItemWorker(self.db, "category", category_id, data, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущено асинхронное обновление категории {category_id}")

    def delete_section_async(self, section_id: int) -> None:
        """Асинхронное удаление раздела."""
        worker = DeleteItemWorker(self.db, "section", section_id, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущено асинхронное удаление раздела {section_id}")

    def delete_category_async(self, category_id: int) -> None:
        """Асинхронное удаление категории."""
        worker = DeleteItemWorker(self.db, "category", category_id, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущено асинхронное удаление категории {category_id}")

    def count_nested_objects_async(self, section_id: int) -> None:
        """Асинхронный подсчет вложенных объектов (категорий и ссылок)."""
        worker = CountNestedObjectsWorker(self.db, section_id, self._worker_signals)
        self._thread_pool.start(worker)
        self.logger.debug(f"Запущен асинхронный подсчет вложенных объектов для раздела {section_id}")


class AsyncSignalHandlers:
    """Класс для обработки сигналов от асинхронных операций."""
    
    def __init__(self, controller_instance):
        self.controller = controller_instance
        self.logger = controller_instance.logger
    
    def on_spheres_loaded(self, spheres: List[Dict[str, Any]]) -> None:
        """Обработчик завершения загрузки сфер."""
        self.logger.debug(f"Загружено {len(spheres)} сфер")
        self.controller.spheres_loaded.emit(spheres)

    def on_structure_loaded(self, structure: List[Dict[str, Any]], sphere_id: int) -> None:
        """Обработчик завершения загрузки структуры."""
        self.logger.debug(f"Загружена структура для сферы {sphere_id}: {len(structure)} разделов")
        self.controller.structure_loaded.emit(structure)

    def on_sections_loaded(self, sections: List[Dict[str, Any]], sphere_id: int) -> None:
        """Обработчик завершения загрузки разделов."""
        self.logger.debug(f"Загружено {len(sections)} разделов для сферы {sphere_id}")

    def on_categories_loaded(self, categories: List[Dict[str, Any]], section_id: int) -> None:
        """Обработчик завершения загрузки категорий."""
        self.logger.debug(f"Загружено {len(categories)} категорий для раздела {section_id}")
        self.controller.section_selected.emit(section_id, categories)
