# app/controllers/domain/structure/structure_business.py

"""Рефакторированная бизнес-логика для управления структурой (сферы, разделы, категории)."""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.db import Database
from app.models.structure_model import StructureModel

# Импорты модульной архитектуры
from app.controllers.structure_modules import (
    AsyncOperations,
    AsyncSignalHandlers,
    CacheManager,
    CategoryOperations,
    ItemTypes,
    ItemTypeStr,
    SectionOperations,
    SphereOperations,
    StructureBusinessLogicLegacy,
    StructureItemType,
)
from app.controllers.structure_modules.coordination import OperationCoordinator
from app.controllers.structure_modules.positioning_operations import PositioningOperations


class StructureBusinessLogic(QObject):
    """Рефакторированная бизнес-логика для управления структурой.
    
    Управляет сферами, разделами и категориями через модульную архитектуру.
    Также поддерживает создание ссылок через методы импорта для интеграции с LinksBusinessLogic.
    """
    
    # Сигналы для уведомления UI о изменениях
    structure_loaded = pyqtSignal(list)  # List[Dict[str, Any]] - разделы с категориями
    active_sphere_changed = pyqtSignal(int)  # int - ID новой активной сферы
    
    # Сигналы изменения элементов
    # item_added(item_type: ItemTypeStr, parent_id: int, item_data: Dict[str, Any])
    # Где:
    # - item_type: "section" | "category" (ссылки обрабатываются LinksBusinessLogic)
    # - parent_id: для "section" = sphere_id, для "category" = section_id
    # - item_data: Dict с полями элемента включая 'id'
    item_added = pyqtSignal(str, int, dict)  # str, int, Dict - тип элемента, ID родителя, данные
    
    # item_updated(item_type: ItemTypeStr, item_id: int, item_data: Dict[str, Any])
    # Где:
    # - item_type: "section" | "category" (ссылки обрабатываются LinksBusinessLogic)
    # - item_id: ID обновленного элемента
    # - item_data: Dict с обновленными полями включая 'id'
    item_updated = pyqtSignal(str, int, dict)  # str, int, Dict - тип элемента, ID элемента, данные
    
    # item_deleted(item_type: ItemTypeStr, item_id: int)
    # Где:
    # - item_type: "section" | "category" (ссылки обрабатываются LinksBusinessLogic)
    # - item_id: ID удаленного элемента
    item_deleted: pyqtSignal = pyqtSignal(str, int)  # str, int - тип элемента, ID элемента
    
    section_selected: pyqtSignal = pyqtSignal(int, list)  # int, List[Dict] - ID раздела, категории
    category_selected: pyqtSignal = pyqtSignal(int)  # int - ID категории
    error_occurred: pyqtSignal = pyqtSignal(str, str)  # str, str - заголовок, сообщение
    spheres_loaded: pyqtSignal = pyqtSignal(list)  # List[Dict] - список сфер

    def __init__(self, db: Database, logger: Optional[logging.Logger] = None):
        super().__init__()
        self.db = db
        self.structure_model = StructureModel(db)
        self.logger = logger or logging.getLogger(__name__)
        self.current_sphere_id: Optional[int] = None
        
        # Инициализация модульной архитектуры
        self._init_modules()
        self._setup_async_signals()
    
    def _init_modules(self):
        """Инициализирует все модули."""
        # Координатор операций
        self.coordinator = OperationCoordinator(self.structure_model, self.logger)
        
        # Кэш-менеджер
        self.cache_manager = CacheManager(self.logger)
        
        # Операции со сферами
        self.sphere_operations = SphereOperations(
            self.structure_model, self.logger, self.coordinator.execute_with_error_handling
        )
        
        # Операции с разделами
        self.section_operations = SectionOperations(
            self.structure_model, self.logger,
            self.coordinator.execute_with_error_handling, self.coordinator.execute_with_validation,
            self._emit_signal
        )
        
        # Операции с категориями
        self.category_operations = CategoryOperations(
            self.structure_model, self.logger,
            self.coordinator.execute_with_error_handling, self.coordinator.execute_with_validation,
            self._emit_signal, self.cache_manager
        )
        
        # Операции со ссылками удалены - используйте LinksBusinessLogic
        
        # Операции с позиционированием
        self.positioning_operations = PositioningOperations(
            self.structure_model, self.logger,
            self.coordinator.execute_with_error_handling
        )
        
        # Асинхронные операции
        self.async_operations = AsyncOperations(self.db, self.logger)
    
    def _setup_async_signals(self):
        """Настраивает подключения сигналов от асинхронных воркеров."""
        self.async_signal_handlers = AsyncSignalHandlers(self)
        worker_signals = self.async_operations.get_worker_signals()
        
        # Подключаем сигналы
        worker_signals.spheres_loaded.connect(self.async_signal_handlers.on_spheres_loaded)
        worker_signals.structure_loaded.connect(self.async_signal_handlers.on_structure_loaded)
        worker_signals.sections_loaded.connect(self.async_signal_handlers.on_sections_loaded)
        worker_signals.categories_loaded.connect(self.async_signal_handlers.on_categories_loaded)
    
    def _emit_signal(self, signal_type: str, *args):
        """Callback для эмиссии сигналов из операций."""
        if signal_type == "item_added":
            self.item_added.emit(*args)
        elif signal_type == "item_updated":
            self.item_updated.emit(*args)
        elif signal_type == "item_deleted":
            self.item_deleted.emit(*args)
    
    # =============================================================================
    # ОСНОВНЫЕ МЕТОДЫ КОНТРОЛЛЕРА
    # =============================================================================
    
    def set_current_sphere(self, sphere_id: int) -> None:
        """Устанавливает текущую сферу."""
        self.current_sphere_id = sphere_id
        self.logger.info(f"Установлена текущая сфера: {sphere_id}")
        self.active_sphere_changed.emit(sphere_id)
    
    def load_structure(self, sphere_id: Optional[int] = None) -> None:
        """Загружает структуру для указанной сферы с оптимизированными запросами."""
        if sphere_id is not None:
            self.current_sphere_id = sphere_id
        
        if self.current_sphere_id is None:
            self.structure_loaded.emit([])
            return
        
        result = self.coordinator.load_structure_with_categories(
            self.current_sphere_id, self.category_operations, self._emit_error
        )
        self.structure_loaded.emit(result)
    
    def select_section(self, section_id: int) -> None:
        """Выбирает раздел и загружает его категории (асинхронная версия)."""
        self.async_operations.load_categories_async(section_id)
        self.logger.debug(f"Запущена асинхронная загрузка категорий для раздела {section_id}")
        # Defensive check to prevent 'NoneType' iterable error
        categories = self.category_operations.get_categories(section_id) or []
        self.section_selected.emit(section_id, categories)
    
    def select_category(self, category_id: int) -> None:
        """Выбирает категорию."""
        self.category_selected.emit(category_id)
        self.logger.debug(f"Выбрана категория {category_id}")
    
    # =============================================================================
    # ДЕЛЕГИРОВАНИЕ К МОДУЛЯМ ОПЕРАЦИЙ
    # =============================================================================
    
    # Операции со сферами
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Получает список всех сфер."""
        return self.sphere_operations.get_spheres()
    
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные сферы по ID."""
        return self.sphere_operations.get_sphere_by_id(sphere_id)
    
    def get_next_sphere_id(self) -> Optional[int]:
        """Определяет и возвращает ID следующей сферы в списке (циклически)."""
        return self.sphere_operations.get_next_sphere_id(self.current_sphere_id)
    
    def get_target_section_id(self) -> Optional[int]:
        """Получает ID первого доступного раздела в текущей сфере."""
        return self.sphere_operations.get_target_section_id(self.current_sphere_id)
    
    # Операции с разделами
    def create_section(self, data: Dict[str, Any]) -> bool:
        """Создает новый раздел."""
        return self.section_operations.create_section(data)
    
    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет существующий раздел."""
        return self.section_operations.update_section(section_id, data)
    
    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        """Удаляет раздел."""
        return self.section_operations.delete_section(section_id)
    
    def confirm_delete_section(self, section_id: int) -> bool:
        """Подтверждает и выполняет удаление раздела."""
        return self.section_operations.confirm_delete_section(section_id)
    
    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные раздела."""
        return self.section_operations.get_section_data(section_id)
    
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает список разделов для указанной сферы."""
        return self.section_operations.get_sections(sphere_id)
    
    # Операции с категориями
    def create_category(self, data: Dict[str, Any]) -> bool:
        """Создает новую категорию."""
        return self.category_operations.create_category(data)
    
    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет существующую категорию."""
        return self.category_operations.update_category(category_id, data)
    
    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        """Удаляет категорию."""
        return self.category_operations.delete_category(category_id)
    
    def confirm_delete_category(self, category_id: int) -> bool:
        """Подтверждает и выполняет удаление категории."""
        return self.category_operations.confirm_delete_category(category_id)
    
    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные категории."""
        return self.category_operations.get_category_data(category_id)
    
    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Получает список категорий для указанного раздела."""
        return self.category_operations.get_categories(section_id)
    
    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории с кэшированием."""
        return self.category_operations.get_first_category_id()
    
    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает иерархию для категории."""
        return self.category_operations.get_category_hierarchy(category_id)
    
    def has_duplicate_category(self, section_id: int, category_name: str, exclude_id: Optional[int] = None) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        return self.category_operations.has_duplicate_category(section_id, category_name, exclude_id)
    
    # =============================================================================
    # АСИНХРОННЫЕ МЕТОДЫ
    # =============================================================================
    
    def load_spheres_async(self) -> None:
        """Асинхронная загрузка всех сфер."""
        self.async_operations.load_spheres_async()

    def load_structure_async(self, sphere_id: Optional[int] = None) -> None:
        """Асинхронная загрузка структуры для сферы."""
        if sphere_id is not None:
            self.current_sphere_id = sphere_id

        if self.current_sphere_id is None:
            self.structure_loaded.emit([])
            return

        self.async_operations.load_structure_async(self.current_sphere_id)

    def load_sections_async(self, sphere_id: int) -> None:
        """Асинхронная загрузка разделов для сферы."""
        self.async_operations.load_sections_async(sphere_id)

    def load_categories_async(self, section_id: int) -> None:
        """Асинхронная загрузка категорий для раздела."""
        self.async_operations.load_categories_async(section_id)

    def create_section_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание раздела."""
        self.async_operations.create_section_async(data)

    def create_category_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание категории."""
        self.async_operations.create_category_async(data)

    def update_section_async(self, section_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление раздела."""
        self.async_operations.update_section_async(section_id, data)

    def update_category_async(self, category_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление категории."""
        self.async_operations.update_category_async(category_id, data)

    def delete_section_async(self, section_id: int) -> None:
        """Асинхронное удаление раздела."""
        self.async_operations.delete_section_async(section_id)

    def delete_category_async(self, category_id: int) -> None:
        """Асинхронное удаление категории."""
        self.async_operations.delete_category_async(category_id)

    def count_nested_objects_async(self, section_id: int) -> None:
        """Асинхронный подсчет вложенных объектов."""
        self.async_operations.count_nested_objects_async(section_id)
    
    # =============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =============================================================================
    
    def get_current_sphere_id(self) -> Optional[int]:
        """Возвращает ID текущей активной сферы."""
        return self.current_sphere_id
    
    def get_first_category_id_async(self) -> None:
        """Асинхронно получает ID первой категории."""
        category_id = self.get_first_category_id()
        self.logger.debug(f"Получена первая категория асинхронно: {category_id}")
    
    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> bool:
        """Обновляет позиции элементов в указанной таблице."""
        return self.positioning_operations.update_item_positions(table_name, ids_in_order)
    
    def get_item_for_editing(self, item_id: int, item_type: StructureItemType) -> Optional[Dict[str, Any]]:
        """Универсальный метод получения данных элемента для редактирования."""
        if item_type == StructureItemType.SECTION:
            return self.section_operations.get_section_data(item_id)
        else:
            return self.category_operations.get_category_data(item_id)
    
    def get_section_for_editing(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные раздела для редактирования в диалоге."""
        return self.get_item_for_editing(section_id, StructureItemType.SECTION)

    def get_category_for_editing(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные категории для редактирования в диалоге."""
        return self.get_item_for_editing(category_id, StructureItemType.CATEGORY)
    
    # =============================================================================
    # МЕТОДЫ ДЛЯ ИМПОРТА И ИНТЕГРАЦИИ
    # =============================================================================
    
    def create_category_for_import(self, category_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую категорию для импорта."""
        return self.category_operations.create_category_for_import(category_data)
    
    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """Получает список ссылок для указанной категории.
        
        DEPRECATED: Используйте LinksBusinessLogic.get_links_for_category() вместо этого метода.
        Этот метод сохранен только для обратной совместимости.
        """
        # Прямой вызов модели для обратной совместимости
        try:
            return self.structure_model.get_links(category_id) or []
        except Exception as e:
            self.logger.error(f"Ошибка получения ссылок для категории {category_id}: {e}")
            return []
    
    # =============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ КОНТРОЛЛЕРА
    # =============================================================================
    
    def _emit_error(self, title: str, message: str, exc_info: bool = False) -> None:
        """Отправляет сигнал об ошибке с опциональным трейсбеком."""
        self.error_occurred.emit(title, message)
        self.logger.error(f"{title}: {message}", exc_info=exc_info)


# Backward compatibility aliases (устаревшие методы)
StructureBusinessLogicLegacy = StructureBusinessLogicLegacy
