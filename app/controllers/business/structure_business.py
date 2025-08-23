# app/controllers/structure_business.py

"""
Полностью рефакторированная бизнес-логика для управления структурой (сферы, разделы, категории).
Совместима с существующей программой, сохраняет все необходимые интерфейсы и сигналы.
"""

import logging
from typing import Any, Dict, List, Optional, Union, Tuple

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.controllers.structure_modules import (
    CacheManager,
    ValidationResult,
    handle_exceptions,
)
from app.controllers.structure_modules.async_operations import (
    AsyncOperations,
    AsyncSignalHandlers,
)
from app.controllers.structure_services.exporter import ExportService
from app.controllers.structure_services.importer import ImportService
from app.controllers.structure_services.integrity import IntegrityService
from app.controllers.structure_services.loader import LoaderService
from app.controllers.structure_services.selection import SelectionService
from app.controllers.structure_services.utilities import UtilityService
from app.controllers.structure_services.validation import ValidationService
from app.models.db import Database
from app.models.structure_model import StructureModel
from app.services.structure_service import StructureService


class StructureBusinessLogic(QObject):
    """
    Полностью рефакторированная бизнес-логика для управления структурой.
    
    Сохраняет полную совместимость с существующим кодом программы,
    но с улучшенной внутренней архитектурой и обработкой ошибок.
    """
    
    # Основные сигналы (сохранены для совместимости)
    structure_loaded = pyqtSignal(list)  # List[Dict[str, Any]] - разделы с категориями
    active_sphere_changed = pyqtSignal(int)  # int - ID новой активной сферы
    
    # Сигналы изменения элементов (совместимость)
    item_added = pyqtSignal(str, int, dict)  # str, int, Dict - тип элемента, ID родителя, данные
    item_updated = pyqtSignal(str, int, dict)  # str, int, Dict - тип элемента, ID элемента, данные
    item_deleted = pyqtSignal(str, int)  # str, int - тип элемента, ID элемента
    
    # Сигналы выбора
    section_selected = pyqtSignal(int, list)  # int, List[Dict] - ID раздела, категории
    category_selected = pyqtSignal(int)  # int - ID категории
    
    # Служебные сигналы
    error_occurred = pyqtSignal(str, str)  # str, str - заголовок, сообщение
    spheres_loaded = pyqtSignal(list)  # List[Dict] - список сфер

    def __init__(self, db: Database, logger: Optional[logging.Logger] = None):
        """Инициализация бизнес-логики."""
        super().__init__()
        
        self.db = db
        self.structure_model = StructureModel(db)
        # Сервис структуры: маршрут к репозиторию через сервисный слой (без дублирования SQL)
        self.structure_service = StructureService(db)
        self.logger = logger or logging.getLogger(__name__)
        
        # Состояние
        self.current_sphere_id: Optional[int] = None
        
        # Кэш-менеджер
        self.cache_manager = CacheManager(self.logger)
        
        # Сервисы
        self.export_service = ExportService()
        self.integrity_service = IntegrityService()
        self.loader_service = LoaderService()
        self.selection_service = SelectionService()
        self.validation_service = ValidationService()
        self.import_service = ImportService()
        self.utility_service = UtilityService()
        
        # Реальный асинхронный слой для операций структуры (через TaskScheduler)
        self.async_operations = AsyncOperations(self.db, self.logger)
        self._async_handlers = AsyncSignalHandlers(self)
        self.async_operations.connect_signal_handlers(self._async_handlers)

        # Таймер для дебаунса перезагрузки структуры при изменениях ссылок
        self._structure_reload_timer: Optional[QTimer] = QTimer(self)
        self._structure_reload_timer.setSingleShot(True)
        self._structure_reload_timer.timeout.connect(self._perform_structure_reload)
        
        # Инициализация
        self._initialize_system()

        # Подключаем внутренние обработчики к бизнес-сигналам, чтобы
        # изменения, пришедшие не через воркеры, тоже приводили к
        # инвалидизации кэша и асинхронной перезагрузке UI
        try:
            self.item_added.connect(self._on_item_added)
            self.item_updated.connect(self._on_item_updated)
            self.item_deleted.connect(self._on_item_deleted)
            self.logger.info(f"[BL] Handlers connected for business id={id(self)}")
        except Exception:
            # Защита от ошибок подключения сигналов, не ломаем инициализацию
            self.logger.warning("Не удалось подключить внутренние обработчики бизнес-сигналов", exc_info=True)
    
    def _initialize_system(self) -> None:
        """Инициализация системы."""
        self.logger.info("Инициализация StructureBusinessLogic")
        
        # Настройка таймеров и дополнительных компонентов
        self._setup_periodic_tasks()
    
    def _setup_periodic_tasks(self) -> None:
        """Настройка периодических задач."""
        # Можно добавить периодические задачи если нужно
        pass
    
    # =============================================================================
    # ОСНОВНЫЕ МЕТОДЫ КОНТРОЛЛЕРА (СОВМЕСТИМОСТЬ)
    # =============================================================================
    
    def set_current_sphere(self, sphere_id: int) -> None:
        """Устанавливает текущую сферу."""
        try:
            old_sphere_id = self.current_sphere_id

            # Гард: если сфера не меняется — ничего не делаем
            if old_sphere_id == sphere_id:
                self.logger.debug("set_current_sphere: сфера не изменилась; пропуск")
                return

            self.current_sphere_id = sphere_id
            
            # Очищаем кэш при смене сферы
            if old_sphere_id != sphere_id:
                self.cache_manager.invalidate(f"sphere_{old_sphere_id}")
            
            self.logger.info(f"Установлена текущая сфера: {sphere_id}")
            self.active_sphere_changed.emit(sphere_id)
            
        except Exception as e:
            self._handle_error("Ошибка установки текущей сферы", e)
    
    @handle_exceptions(default_return=[])
    def load_structure(self, sphere_id: Optional[int] = None) -> None:
        """Загружает структуру для указанной сферы с оптимизированными запросами."""
        if sphere_id is not None:
            self.current_sphere_id = sphere_id
        
        if self.current_sphere_id is None:
            self.structure_loaded.emit([])
            return
        
        # Проверяем кэш
        cache_key = f"structure_{self.current_sphere_id}"
        cached_structure = self.cache_manager.get(cache_key)
        
        if cached_structure is not None:
            self.structure_loaded.emit(cached_structure)
            return
        
        # Загружаем из базы данных
        structure_data = self._load_structure_from_db(self.current_sphere_id)
        
        # Кэшируем результат
        self.cache_manager.set(cache_key, structure_data)
        
        self.structure_loaded.emit(structure_data)
        self.logger.debug(f"Загружена структура для сферы {self.current_sphere_id}")
    
    def _load_structure_from_db(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Загружает структуру из базы данных (делегировано в сервис)."""
        return self.loader_service.load_structure_from_db(
            structure_model=self.structure_model,
            sphere_id=sphere_id,
            logger=self.logger,
        )

    # =============================================================================
    # ВНУТРЕННИЕ ОБРАБОТЧИКИ БИЗНЕС-СИГНАЛОВ (от команд UI и проч.)
    # =============================================================================
    def _on_item_added(self, item_type: str, parent_id: int, item_data: Dict[str, Any]) -> None:
        """Элемент добавлен: инвалидируем кэш и запускаем асинхронную перезагрузку."""
        try:
            self.logger.info(f"[BL] item_added: type={item_type}, parent_id={parent_id}")
            # Для ссылок не требуется немедленная полная перезагрузка структуры
            if item_type == 'link':
                category_id = (item_data.get('category_id') if isinstance(item_data, dict) else None)
                self._invalidate_categories_cache(category_id)
                # Лёгкая консистентность дерева: отложенная общая перезагрузка (коалесцирует частые события)
                self._schedule_structure_reload(200)
                return
            if item_type == 'category':
                # parent_id здесь — это section_id для категории
                section_id = parent_id or (item_data.get('section_id') if isinstance(item_data, dict) else None)
                self._invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            # Для надёжности всегда инвалидируем общую структуру
            self._invalidate_structure_cache()
            # Коалесцируем перезагрузку структуры, чтобы избежать дублей
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике _on_item_added: {e}", exc_info=True)

    def _on_item_updated(self, item_type: str, item_id: int, item_data: Dict[str, Any]) -> None:
        """Элемент обновлён: инвалидируем кэш и запускаем асинхронную перезагрузку."""
        try:
            self.logger.info(f"[BL] item_updated: type={item_type}, id={item_id}")
            if item_type == 'link':
                category_id = (item_data.get('category_id') if isinstance(item_data, dict) else None)
                self._invalidate_categories_cache(category_id)
                # Раньше здесь планировалась полная перезагрузка структуры сферы.
                # Отключено для «мелких» правок ссылок: таблицу/избранное обновляют UI-команды,
                # а структура сферы не меняется.
                return
            if item_type == 'category':
                section_id = (item_data.get('section_id') if isinstance(item_data, dict) else None)
                self._invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            self._invalidate_structure_cache()
            # Коалесцируем перезагрузку структуры, чтобы избежать дублей
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике _on_item_updated: {e}", exc_info=True)

    def _schedule_structure_reload(self, delay_ms: int = 200) -> None:
        """Планирует отложенную перезагрузку структуры (дебаунсирует частые события)."""
        try:
            if not isinstance(delay_ms, int) or delay_ms < 0:
                delay_ms = 200
            # Перезапускаем одиночный таймер: несколько вызовов сольются в один
            if self._structure_reload_timer.isActive():
                self._structure_reload_timer.stop()
            self._structure_reload_timer.start(delay_ms)
        except Exception as e:
            self.logger.warning(f"_schedule_structure_reload: failed to schedule: {e}")

    def _perform_structure_reload(self) -> None:
        """Выполняет фактическую перезагрузку структуры текущей сферы."""
        try:
            self._invalidate_structure_cache()
            sphere_id = self.current_sphere_id
            if isinstance(sphere_id, int) and sphere_id > 0:
                self.async_operations.load_structure_async(sphere_id)
        except Exception as e:
            self.logger.error(f"_perform_structure_reload: {e}")

    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        """Элемент удалён: инвалидируем кэш и запускаем асинхронную перезагрузку.

        Примечание: данная сигнатура не содержит старых данных (section_id для категорий),
        поэтому для надёжности перезагружаем всю структуру текущей сферы.
        """
        try:
            self.logger.info(f"[BL] item_deleted: type={item_type}, id={item_id}")
            # Для ссылок используем отложенную перезагрузку структуры, чтобы
            # коалесцировать серию удалений в одну перезагрузку
            if item_type == 'link':
                self._schedule_structure_reload(200)
                return
            # Для остальных типов: инвалидируем и планируем общую перезагрузку структуры
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике _on_item_deleted: {e}", exc_info=True)
    
    @handle_exceptions()
    def select_section(self, section_id: int) -> None:
        """Выбирает раздел и загружает его категории."""
        categories = self.get_categories(section_id)
        self.section_selected.emit(section_id, categories)
        self.logger.debug(f"Выбран раздел {section_id} с {len(categories)} категориями")
    
    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        """Выбирает категорию."""
        self.category_selected.emit(category_id)
        self.logger.debug(f"Выбрана категория {category_id}")
        
    # =============================================================================
    # ОПЕРАЦИИ СО СФЕРАМИ (СОВМЕСТИМОСТЬ)
    # =============================================================================
    
    @handle_exceptions(default_return=[])
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Получает список всех сфер (с кэшированием, чтение через сервис)."""
        cache_key = "all_spheres"
        cached_spheres = self.cache_manager.get(cache_key)
        if cached_spheres is not None:
            return cached_spheres
        spheres = self.structure_service.get_spheres()
        self.cache_manager.set(cache_key, spheres)
        return spheres or []

    # --- Совместимые методы, ранее предоставлялись Mixin-ами ---
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает разделы для сферы с кэшированием (чтение через сервис)."""
        cache_key = f"sections_{sphere_id}"
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
        sections = self.structure_service.get_sections(sphere_id)
        self.cache_manager.set(cache_key, sections)
        return sections or []

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Получает категории для раздела с кэшированием (чтение через сервис)."""
        cache_key = f"categories_{section_id}"
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
        categories = self.structure_service.get_categories(section_id)
        self.cache_manager.set(cache_key, categories)
        return categories or []

    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """Получает ссылки для категории (совместимость со старым интерфейсом)."""
        # Делегируем в UtilityService, который обращается к модели.
        return self.utility_service.get_links(self.structure_model, category_id, self.logger)

    @handle_exceptions()
    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Совместимый метод получения данных раздела (для диалогов/операций UI)."""
        return self.structure_service.get_section_by_id(section_id)

    @handle_exceptions()
    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Совместимый метод получения данных категории (для диалогов/операций UI)."""
        return self.structure_service.get_category_by_id(category_id)

    @handle_exceptions()
    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Совместимый метод: возвращает {'sphere_id', 'section_id'} для категории."""
        return self.structure_service.get_category_hierarchy(category_id)

    def get_item_for_editing(self, item_id: int, item_type: Union[str, Any]) -> Optional[Dict[str, Any]]:
        """Совместимый метод получения данных элемента для редактирования."""
        return self.utility_service.get_item_for_editing(
            item_id=item_id,
            item_type=item_type,
            get_section_data=self.structure_model.get_section_data,
            get_category_data=self.structure_model.get_category_data,
            logger=self.logger,
        )

    def get_first_category_id(self) -> Optional[int]:
        """Возвращает id первой доступной категории в текущей сфере (с кэшированием)."""
        return self.utility_service.get_first_category_id(
            current_sphere_id=self.current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self.cache_manager.get,
            cache_set=self.cache_manager.set,
        )

    def get_target_section_id(self) -> Optional[int]:
        """Совместимое имя-обёртка для получения первой категории текущей сферы."""
        return self.utility_service.get_target_section_id(
            current_sphere_id=self.current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self.cache_manager.get,
            cache_set=self.cache_manager.set,
        )
    
    # =============================================================================
    # CRUD-ОПЕРАЦИИ ДЛЯ РАЗДЕЛОВ И КАТЕГОРИЙ (через StructureService)
    # =============================================================================
    @handle_exceptions()
    def create_section(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Создаёт раздел через сервис, эмитит сигнал и инвалидирует кэш."""
        section_id = self.structure_service.create_section(data)
        if not section_id:
            return None
        section_data = self.structure_service.get_section_by_id(section_id) or {}
        sphere_id = section_data.get('sphere_id') if isinstance(section_data, dict) else None
        try:
            self.item_added.emit('section', int(sphere_id) if sphere_id else 0, section_data)
        finally:
            # Инвалидируем кэш по разделам и структуре
            if sphere_id:
                self.cache_manager.invalidate(f"sections_{sphere_id}")
            self._invalidate_structure_cache()
        return section_data or None

    @handle_exceptions()
    def update_section(self, section_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обновляет раздел через сервис, эмитит сигнал и инвалидирует кэш."""
        ok = self.structure_service.update_section(section_id, data)
        if not ok:
            return None
        section_data = self.structure_service.get_section_by_id(section_id) or {}
        sphere_id = section_data.get('sphere_id') if isinstance(section_data, dict) else None
        try:
            self.item_updated.emit('section', section_id, section_data)
        finally:
            if sphere_id:
                self.cache_manager.invalidate(f"sections_{sphere_id}")
            self._invalidate_structure_cache()
        return section_data or None

    @handle_exceptions()
    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        """Удаляет раздел через сервис. Возвращает (успех, данные, кол-во категорий, кол-во ссылок).

        Примечание: считаем количество категорий до удаления для обратной совместимости.
        """
        section_before = self.structure_service.get_section_by_id(section_id) or {}
        if not section_before:
            return False, {}, 0, 0
        sphere_id = section_before.get('sphere_id') if isinstance(section_before, dict) else None
        categories_before = self.structure_service.get_categories(section_before.get('id', section_id)) if section_before else []
        categories_count = len(categories_before or [])
        # Информации о ссылках на уровне раздела нет в сервисе — возвращаем 0 для совместимости
        success = self.structure_service.delete_section(section_id)
        if success:
            try:
                self.item_deleted.emit('section', section_id)
            finally:
                if sphere_id:
                    self.cache_manager.invalidate(f"sections_{sphere_id}")
                self._invalidate_structure_cache()
        return success, section_before, categories_count, 0

    @handle_exceptions()
    def create_category(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Создаёт категорию через сервис, эмитит сигнал и инвалидирует кэш."""
        category_id = self.structure_service.create_category(data)
        if not category_id:
            return None
        category_data = self.structure_service.get_category_by_id(category_id) or {}
        section_id = category_data.get('section_id') if isinstance(category_data, dict) else None
        try:
            # parent_id для категории — это section_id
            self.item_added.emit('category', int(section_id) if section_id else 0, category_data)
        finally:
            self._invalidate_categories_cache(section_id)
        return category_data or None

    @handle_exceptions()
    def update_category(self, category_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обновляет категорию через сервис, эмитит сигнал и инвалидирует кэш."""
        ok = self.structure_service.update_category(category_id, data)
        if not ok:
            return None
        category_data = self.structure_service.get_category_by_id(category_id) or {}
        section_id = category_data.get('section_id') if isinstance(category_data, dict) else None
        try:
            self.item_updated.emit('category', category_id, category_data)
        finally:
            self._invalidate_categories_cache(section_id)
        return category_data or None

    @handle_exceptions()
    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        """Удаляет категорию через сервис. Возвращает (успех, данные, кол-во ссылок).

        Примечание: кол-во ссылок на уровне категории сейчас не подсчитываем — вернём 0.
        """
        category_before = self.structure_service.get_category_by_id(category_id) or {}
        if not category_before:
            return False, {}, 0
        section_id = category_before.get('section_id') if isinstance(category_before, dict) else None
        success = self.structure_service.delete_category(category_id)
        if success:
            try:
                self.item_deleted.emit('category', category_id)
            finally:
                self._invalidate_categories_cache(section_id)
        return success, category_before, 0
    
    # =============================================================================
    # ПУБЛИЧНЫЕ АСИНХРОННЫЕ ОБЁРТКИ ДЛЯ UI (совместимость)
    # =============================================================================
    def load_spheres_async(self) -> None:
        """Загружает список сфер и эмитит сигнал spheres_loaded (совместимость с UI)."""
        try:
            # Переход на реальную асинхронную загрузку через AsyncOperations
            self.async_operations.load_spheres_async()
        except Exception as e:
            self.logger.error(f"load_spheres_async failed: {e}")
    
    @handle_exceptions()
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные сферы по ID."""
        spheres = self.get_spheres()
        return next((sphere for sphere in spheres if sphere['id'] == sphere_id), None)
    
    @handle_exceptions()
    def get_next_sphere_id(self) -> Optional[int]:
        """Определяет и возвращает ID следующей сферы в списке (циклически)."""
        spheres = self.get_spheres()
        if not spheres:
            return None
        
        if self.current_sphere_id is None:
            return spheres[0]['id']
        
        current_index = next(
            (i for i, sphere in enumerate(spheres) if sphere['id'] == self.current_sphere_id), 
            -1
        )
        
        if current_index == -1:
            return spheres[0]['id']
        
        next_index = (current_index + 1) % len(spheres)
        return spheres[next_index]['id']
    
    @handle_exceptions(default_return=False)
    def has_duplicate_category(self, section_id: int, category_name: str, exclude_id: Optional[int] = None) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        categories = self.get_categories(section_id)
        
        for category in categories:
            if (category['name'].lower() == category_name.lower().strip() and 
                category['id'] != exclude_id):
                return True
        
        return False
    
    # =============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (СОВМЕСТИМОСТЬ)
    # =============================================================================
    
    def get_current_sphere_id(self) -> Optional[int]:
        """Возвращает ID текущей активной сферы."""
        return self.current_sphere_id
    
    def get_section_for_editing(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные раздела для редактирования в диалоге."""
        return self.get_item_for_editing(section_id, "section")

    def get_category_for_editing(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные категории для редактирования в диалоге."""
        return self.get_item_for_editing(category_id, "category")

    # =============================================================================
    # МЕТОДЫ ДЛЯ ИМПОРТА И ИНТЕГРАЦИИ (СОВМЕСТИМОСТЬ)
    # =============================================================================
    
    @handle_exceptions()
    def create_category_for_import(self, category_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую категорию для импорта (делегировано в сервис)."""
        category_id = self.import_service.create_category_for_import(
            self.structure_model, category_data, self.logger
        )
        if category_id:
            # Инвалидируем кэш для раздела
            section_id = category_data.get('section_id')
            if section_id:
                self._invalidate_categories_cache(section_id)
        return category_id
        
    # =============================================================================
    # ВНУТРЕННИЕ МЕТОДЫ - ВАЛИДАЦИЯ
    # =============================================================================
    
    def _validate_section_data(self, data: Dict[str, Any], section_id: Optional[int] = None) -> ValidationResult:
        """Валидирует данные раздела (делегировано в ValidationService)."""
        return self.validation_service.validate_section_data(
            data=data,
            section_id=section_id,
            get_sections=self.get_sections,
        )
    
    def _validate_category_data(self, data: Dict[str, Any], category_id: Optional[int] = None) -> ValidationResult:
        """Валидирует данные категории (делегировано в ValidationService)."""
        return self.validation_service.validate_category_data(
            data=data,
            category_id=category_id,
            has_duplicate_category=self.has_duplicate_category,
        )
    
    # =============================================================================
    # ВНУТРЕННИЕ МЕТОДЫ - УПРАВЛЕНИЕ КЭШЕМ
    # =============================================================================
    
    def _invalidate_structure_cache(self) -> None:
        """Инвалидирует кэш структуры."""
        if self.current_sphere_id:
            # Инвалидируем кэш структуры и разделов для текущей сферы
            self.cache_manager.invalidate(f"structure_{self.current_sphere_id}")
            self.cache_manager.invalidate(f"sections_{self.current_sphere_id}")
            self.cache_manager.invalidate(f"first_category_{self.current_sphere_id}")
    
    def _invalidate_categories_cache(self, section_id: Optional[int]) -> None:
        """Инвалидирует кэш категорий для раздела."""
        if section_id:
            self.cache_manager.invalidate(f"categories_{section_id}")
        
        # Также инвалидируем структуру, так как она содержит категории
        self._invalidate_structure_cache()
    
    # =============================================================================
    # ВНУТРЕННИЕ МЕТОДЫ - ОБРАБОТКА ОШИБОК
    # =============================================================================
    
    def _handle_error(self, title: str, error: Exception) -> None:
        """Обрабатывает ошибки с полным логированием."""
        error_msg = str(error)
        self.logger.error(f"{title}: {error_msg}", exc_info=True)
        self._emit_error(title, error_msg)
    
    def _emit_error(self, title: str, message: str) -> None:
        """Отправляет сигнал об ошибке."""
        self.error_occurred.emit(title, message)
        self.logger.error(f"{title}: {message}")
    
    # =============================================================================
    # ДОПОЛНИТЕЛЬНЫЕ СЛУЖЕБНЫЕ МЕТОДЫ
    # =============================================================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получает статистику по структуре (делегировано в сервис)."""
        return self.integrity_service.get_statistics(
            get_spheres=self.get_spheres,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            current_sphere_id=self.current_sphere_id,
            logger=self.logger,
        )
    
    def clear_all_cache(self) -> None:
        """Полностью очищает весь кэш."""
        self.cache_manager.invalidate()
        self.logger.info("Кэш полностью очищен")
