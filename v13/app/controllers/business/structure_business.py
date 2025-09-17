# app/controllers/structure_business.py

"""
Полностью рефакторированная бизнес-логика для управления структурой (сферы, разделы, категории).
Совместима с существующей программой, сохраняет все необходимые интерфейсы и сигналы.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.controllers.structure_modules import (
    CacheManager,
    ValidationResult,
    handle_exceptions,
)
from app.controllers.business.structure_async import (
    create_async_layer,
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
from app.controllers.business.structure_cache import StructureCache
from app.controllers.business.structure_signals import StructureSignalsManager
from app.controllers.structure_modules.batch_manager import BatchUpdateCoordinator
from app.controllers.structure_modules.warm_cache import WarmCacheHelper
from app.controllers.structure_modules.crud import StructureCrud
from app.controllers.structure_modules.queries import StructureQueries
from app.controllers.structure_modules.error_emitter import ErrorEmitter
from app.controllers.structure_modules.sphere_switch import SphereSwitchCoordinator
from app.controllers.structure_modules.selection_coordinator import SelectionCoordinator


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
    item_added = pyqtSignal(
        str, int, dict
    )  # str, int, Dict - тип элемента, ID родителя, данные
    item_updated = pyqtSignal(
        str, int, dict
    )  # str, int, Dict - тип элемента, ID элемента, данные
    item_deleted = pyqtSignal(str, int)  # str, int - тип элемента, ID элемента
    # Новый батч-сигнал: единое событие вместо множества per-item
    items_batch_deleted = pyqtSignal(str, list)  # str - тип, list[int] - IDs элементов

    # Сигналы выбора
    section_selected = pyqtSignal(int)  # int - ID раздела
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
        # Фасад кэша для централизованного управления
        self.cache = StructureCache(
            cache_manager=self.cache_manager,
            get_current_sphere_id=self.get_current_sphere_id,
            logger=self.logger,
        )

        # Сервисы
        self.export_service = ExportService()
        self.integrity_service = IntegrityService()
        self.loader_service = LoaderService()
        self.selection_service = SelectionService()
        self.validation_service = ValidationService()
        self.import_service = ImportService()
        self.utility_service = UtilityService()

        # Реальный асинхронный слой для операций структуры (через TaskScheduler)
        # Конструируем через адаптер, чтобы изолироваться от физического расположения реализаций
        self.async_operations = create_async_layer(self.db, self.logger)
        self._async_handlers = AsyncSignalHandlers(self)
        self.async_operations.connect_signal_handlers(self._async_handlers)

        # Менеджер сигналов/дебаунса перезагрузки структуры
        self._signals = StructureSignalsManager(self, self.logger)

        # Координатор batch-режима: консолидация множественных обновлений
        self._batch = BatchUpdateCoordinator(
            logger=self.logger,
            on_load_categories=self.async_operations.load_categories_async,
            on_invalidate=self._invalidate_structure_cache,
            on_schedule_reload=self._signals.schedule_structure_reload,
        )

        # Хелпер тёплого кэширования после загрузки структуры
        self._warm_cache = WarmCacheHelper(self.logger)

        # CRUD-координатор: инкапсулирует операции и соблюдает кэш/сигналы
        self._crud = StructureCrud(
            service=self.structure_service,
            cache=self.cache,
            async_ops=self.async_operations,
            emit_item_added=self.item_added.emit,
            emit_item_updated=self.item_updated.emit,
            emit_item_deleted=self.item_deleted.emit,
            schedule_structure_reload=self._schedule_structure_reload,
            logger=self.logger,
        )

        # Фасад чтения с кэшированием
        self._queries = StructureQueries(
            service=self.structure_service,
            model=self.structure_model,
            cache_manager=self.cache_manager,
            utility_service=self.utility_service,
            logger=self.logger,
        )

        # Единый эмиттер ошибок
        self._errors = ErrorEmitter(self.error_occurred.emit, logger=self.logger)

        # Координатор переключения сфер
        self._sphere_switch = SphereSwitchCoordinator(self, logger=self.logger)

        # Координатор выбора разделов/категорий
        self._selection = SelectionCoordinator(self, logger=self.logger)

        # Метрики: момент начала переключения сферы (для последующего логирования времени)
        self._last_switch_started_ms: Optional[float] = None

        # Инициализация
        self._initialize_system()

        # Подключение обработчиков вынесено в менеджер сигналов
        self._signals.connect()

    def set_top_panels_controller(self, top_panels_controller: Any) -> None:
        """Внедрить TopPanelsController и распространить зависимость во все уровни.

        Явно сохраняем ссылку и прокидываем её в AsyncOperations и AsyncSignalHandlers,
        чтобы обработчики сигналов вызывали методы контроллера напрямую без getattr.
        """
        if top_panels_controller is None:
            raise ValueError("TopPanelsController must not be None")

        issues: list[str] = []

        # 1) Локальная ссылка в бизнес-логике
        setattr(self, "top_panels_controller", top_panels_controller)

        # 2) Прямая ссылка для асинхронного слоя
        if not hasattr(self, "async_operations") or not getattr(self, "async_operations"):
            issues.append("async_operations is missing or not initialized")
        else:
            target = getattr(self, "async_operations")
            if not hasattr(target, "top_panels"):
                issues.append("AsyncOperations has no attribute 'top_panels'")
            else:
                try:
                    setattr(target, "top_panels", top_panels_controller)
                except (AttributeError, RuntimeError, TypeError) as e:
                    issues.append(f"AsyncOperations injection failed: {e}")

        # 3) Для уже подключённых обработчиков сигналов
        if not hasattr(self, "_async_handlers") or not getattr(self, "_async_handlers"):
            issues.append("AsyncSignalHandlers is missing or not initialized")
        else:
            target = getattr(self, "_async_handlers")
            if not hasattr(target, "top_panels"):
                issues.append("AsyncSignalHandlers has no attribute 'top_panels'")
            else:
                try:
                    setattr(target, "top_panels", top_panels_controller)
                except (AttributeError, RuntimeError, TypeError) as e:
                    issues.append(f"AsyncSignalHandlers injection failed: {e}")

        if issues:
            raise ValueError(
                "Failed to inject TopPanelsController: " + "; ".join(issues)
            )

    def _initialize_system(self) -> None:
        """Инициализация системы."""
        self.logger.info("Инициализация StructureBusinessLogic")

        # Таймеры и дополнительные компоненты настраиваются напрямую в __init__


    def set_current_sphere(self, sphere_id: int) -> None:
        """Устанавливает текущую сферу (делегировано SphereSwitchCoordinator)."""
        try:
            self._sphere_switch.set_current_sphere(sphere_id)
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
        self.logger.debug("Загружена структура для сферы %s", self.current_sphere_id)

    def load_structure_async(self, sphere_id: Optional[int] = None) -> None:
        """Асинхронно загружает структуру текущей/указанной сферы через AsyncOperations.

        Предпочтительный путь для UI: не блокирует главный поток и использует
        батч-запрос категорий по всем разделам сферы.
        """
        # Обновляем текущую сферу, если передана явно
        if sphere_id is not None:
            self.current_sphere_id = sphere_id

        # Валидация текущего идентификатора сферы
        if not isinstance(self.current_sphere_id, int) or self.current_sphere_id <= 0:
            # Сообщаем UI пустую структуру, чтобы очистить вид
            try:
                self.structure_loaded.emit([])
            except Exception:
                pass
            return

        # Запускаем асинхронную загрузку через общий слой
        try:
            self.async_operations.load_structure_async(int(self.current_sphere_id))
        except Exception as e:
            # В случае сбоя не подменяем на синхронный путь, а эскалируем через обработчик ошибок
            self._handle_error("Ошибка асинхронной загрузки структуры", e)

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
    def _on_item_added(
        self, item_type: str, parent_id: int, item_data: Dict[str, Any]
    ) -> None:
        """Элемент добавлен: инвалидируем кэш и запускаем асинхронную перезагрузку."""
        try:
            self.logger.info(
                "[BL] item_added: type=%s, parent_id=%s", item_type, parent_id
            )
            # Для ссылок не требуется немедленная полная перезагрузка структуры
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                self._invalidate_categories_cache(category_id)
                # Лёгкая консистентность дерева: отложенная общая перезагрузка (коалесцирует частые события)
                self._schedule_structure_reload(200)
                return
            if item_type == "category":
                # parent_id здесь — это section_id для категории
                section_id = parent_id or (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self._invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            # Для надёжности всегда инвалидируем общую структуру
            self._invalidate_structure_cache()
            # Коалесцируем перезагрузку структуры, чтобы избежать дублей
            self._schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error(
                "Ошибка в обработчике _on_item_added: %s", e, exc_info=True
            )
        except Exception:
            # Неожиданная программная ошибка — не скрываем
            self.logger.exception("_on_item_added: unexpected error")
            raise

    def _on_item_updated(
        self, item_type: str, item_id: int, item_data: Dict[str, Any]
    ) -> None:
        """Элемент обновлён: инвалидируем кэш и запускаем асинхронную перезагрузку."""
        try:
            self.logger.info("[BL] item_updated: type=%s, id=%s", item_type, item_id)
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                self._invalidate_categories_cache(category_id)
                # Раньше здесь планировалась полная перезагрузка структуры сферы.
                # Отключено для «мелких» правок ссылок: таблицу/избранное обновляют UI-команды,
                # а структура сферы не меняется.
                return
            if item_type == "category":
                section_id = (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self._invalidate_categories_cache(section_id)
                # Если активен батч-режим — аккумулируем раздел и выходим
                if self._batch.in_batch:
                    self._batch.touch_section(section_id)
                    return
                # Обычный режим: сразу подгрузим категории раздела
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            self._invalidate_structure_cache()
            # Коалесцируем перезагрузку структуры, чтобы избежать дублей
            self._schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error(
                "Ошибка в обработчике _on_item_updated: %s", e, exc_info=True
            )
        except Exception:
            self.logger.exception("_on_item_updated: unexpected error")
            raise

    # =============================================================================
    # BATСH-РЕЖИМ ДЛЯ КОНСОЛИДАЦИИ МНОЖЕСТВЕННЫХ ОБНОВЛЕНИЙ
    # =============================================================================
    def begin_batch(self) -> None:
        """Включает батч-режим: пер-item обновления коалесцируются."""
        self._batch.begin()

    def end_batch(self) -> None:
        """Завершает батч-режим: выполняет одну консолидацию загрузок/перезагрузки."""
        self._batch.end()

    def _schedule_structure_reload(self, delay_ms: int = 200) -> None:
        """Планирует отложенную перезагрузку структуры (делегировано менеджеру сигналов)."""
        self._signals.schedule_structure_reload(delay_ms)

    def _perform_structure_reload(self) -> None:
        """Фактическая перезагрузка структуры делегирована менеджеру сигналов."""
        # Вызываем публичную обёртку менеджера сигналов (без зависимости от приватных имён)
        try:
            self._signals.perform_structure_reload()
        except Exception as e:
            self.logger.error("perform_structure_reload (delegate) failed: %s", e, exc_info=True)

    
    def _on_structure_loaded_warm_cache(self, _payload: list) -> None:
        """Лёгкий прогрев per-sphere кэша первой категории после загрузки структуры."""
        try:
            helper = getattr(self, "_warm_cache", None)
        except Exception:
            helper = None
        if helper is None:
            # Фолбэк для тестовых двойников, создаёт временный хелпер с безопасным логгером
            try:
                logger = getattr(self, "logger", None)
            except Exception:
                logger = None
            helper = WarmCacheHelper(logger)
        helper.handle(self, _payload)

    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        """Элемент удалён: инвалидируем кэш и запускаем асинхронную перезагрузку.

        Примечание: данная сигнатура не содержит старых данных (section_id для категорий),
        поэтому для надёжности перезагружаем всю структуру текущей сферы.
        """
        try:
            self.logger.info("[BL] item_deleted: type=%s, id=%s", item_type, item_id)
            # Для ссылок используем отложенную перезагрузку структуры, чтобы
            # коалесцировать серию удалений в одну перезагрузку
            if item_type == "link":
                self._schedule_structure_reload(200)
                return
            # Для остальных типов: инвалидируем и планируем общую перезагрузку структуры
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error(
                "Ошибка в обработчике _on_item_deleted: %s", e, exc_info=True
            )
        except Exception:
            self.logger.exception("_on_item_deleted: unexpected error")
            raise

    def _on_items_batch_deleted(self, item_type: str, ids: list) -> None:
        """Батч-удаление элементов: одна инвалидизация и одна перезагрузка.

        Для совместимости по умолчанию выполняем консолидацию как для одиночных
        удалений, но без лавины событий.
        """
        try:
            total = len(ids) if isinstance(ids, (list, tuple)) else 0
            self.logger.info(
                "[BL] items_batch_deleted: type=%s, count=%s", item_type, total
            )
            # Для ссылок используем небольшую задержку, чтобы коалесцировать
            if item_type == "link":
                self._schedule_structure_reload(200)
                return
            # Для категорий/разделов: немедленная консолидация
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            self.logger.error(
                "Ошибка в обработчике _on_items_batch_deleted: %s", e, exc_info=True
            )
        except Exception:
            self.logger.exception("_on_items_batch_deleted: unexpected error")
            raise

    @handle_exceptions()
    def select_section(self, section_id: int) -> None:
        """Выбирает раздел и загружает его категории (делегировано SelectionCoordinator)."""
        self._selection.select_section(section_id)

    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        """Выбирает категорию (делегировано SelectionCoordinator)."""
        self._selection.select_category(category_id)

    

    @handle_exceptions(default_return=[])
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Получает список всех сфер (делегировано в StructureQueries)."""
        return self._queries.get_spheres()

    # --- Совместимые методы, ранее предоставлялись Mixin-ами ---
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает разделы для сферы (делегировано в StructureQueries)."""
        return self._queries.get_sections(sphere_id)

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Получает категории для раздела (делегировано в StructureQueries)."""
        return self._queries.get_categories(section_id)

    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """Получает ссылки для категории (совместимость со старым интерфейсом)."""
        return self._queries.get_links(category_id)

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

    def get_item_for_editing(
        self, item_id: int, item_type: Union[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Совместимый метод получения данных элемента для редактирования."""
        return self._queries.get_item_for_editing(item_id, item_type)

    def get_first_category_id(self) -> Optional[int]:
        """Возвращает id первой доступной категории в текущей сфере (с кэшированием)."""
        return self._queries.get_first_category_id(self.current_sphere_id)

    # =============================================================================
    # СИГНАЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ ПОДКЛЮЧЕНИЯ ИЗ НАСТРОЙКИ ОКНА
    # =============================================================================
    def on_active_sphere_changed(self, *_args: Any) -> None:
        """Обработчик смены активной сферы для подключения напрямую к сигналу.

        Предпочитает асинхронную перезагрузку структуры, если доступен соответствующий
        метод, иначе выполняет синхронную загрузку через `load_structure()`.

        Замечание: неожиданные исключения не перехватываются здесь намеренно, чтобы
        логика настройки могла эскалировать ошибку в SetupError при необходимости.
        """
        # Попытка вызвать явный async-метод, если он предоставлен бизнес-логикой
        loader_async = getattr(self, "load_structure_async", None)
        if callable(loader_async):
            loader_async()
            return

        # Фолбэк на синхронную загрузку (метод существует в текущей реализации)
        loader_sync = getattr(self, "load_structure", None)
        if callable(loader_sync):
            loader_sync()
            return

        # Если ни один метод не обнаружен — зафиксируем и завершим без исключения
        self.logger.error(
            "StructureBusinessLogic has no load_structure_async() or load_structure(); skipping reload"
        )

    def get_target_section_id(self) -> Optional[int]:
        """Совместимое имя-обёртка для получения первой категории текущей сферы."""
        return self._queries.get_target_section_id(self.current_sphere_id)

    
    @handle_exceptions()
    def create_section(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Создаёт раздел (делегировано в StructureCrud)."""
        return self._crud.create_section(data)

    @handle_exceptions()
    def update_section(
        self, section_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Обновляет раздел (делегировано в StructureCrud)."""
        return self._crud.update_section(section_id, data)

    @handle_exceptions()
    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        """Удаляет раздел (делегировано в StructureCrud)."""
        return self._crud.delete_section(section_id)

    @handle_exceptions()
    def create_category(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Создаёт категорию (делегировано в StructureCrud)."""
        return self._crud.create_category(data)

    @handle_exceptions(default_return=[])
    def move_categories_batch(
        self, category_ids: List[int], target_section_id: int, base_row: int = 0
    ) -> List[int]:
        """Пакетно переносит категории; использует batch-режим и делегирует в StructureCrud."""
        if (
            not category_ids
            or not isinstance(target_section_id, int)
            or target_section_id <= 0
        ):
            return []
        self.begin_batch()
        try:
            return self._crud.move_categories_batch(category_ids, target_section_id, base_row)
        finally:
            self.end_batch()

    @handle_exceptions(default_return=[])
    def create_categories_bulk(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Пакетно создаёт категории (делегировано в StructureCrud)."""
        return self._crud.create_categories_bulk(items)

    @handle_exceptions()
    def update_category(
        self, category_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Обновляет категорию (делегировано в StructureCrud)."""
        return self._crud.update_category(category_id, data)

    @handle_exceptions()
    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        """Удаляет категорию (делегировано в StructureCrud)."""
        return self._crud.delete_category(category_id)

    
    def load_spheres_async(self) -> None:
        """Загружает список сфер и эмитит сигнал spheres_loaded (совместимость с UI)."""
        try:
            # Переход на реальную асинхронную загрузку через AsyncOperations
            self.async_operations.load_spheres_async()
        except Exception as e:
            self.logger.error("load_spheres_async failed: %s", e)

    @handle_exceptions()
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные сферы по ID."""
        spheres = self.get_spheres()
        return next((sphere for sphere in spheres if sphere["id"] == sphere_id), None)

    @handle_exceptions()
    def get_next_sphere_id(self) -> Optional[int]:
        """Определяет и возвращает ID следующей сферы в списке (циклически)."""
        spheres = self.get_spheres()
        if not spheres:
            return None

        if self.current_sphere_id is None:
            return spheres[0]["id"]

        current_index = next(
            (
                i
                for i, sphere in enumerate(spheres)
                if sphere["id"] == self.current_sphere_id
            ),
            -1,
        )

        if current_index == -1:
            return spheres[0]["id"]

        next_index = (current_index + 1) % len(spheres)
        return spheres[next_index]["id"]

    @handle_exceptions(default_return=False)
    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        categories = self.get_categories(section_id)

        for category in categories:
            if (
                category["name"].lower() == category_name.lower().strip()
                and category["id"] != exclude_id
            ):
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
    def create_category_for_import(
        self, category_data: Dict[str, Any]
    ) -> Optional[int]:
        """Создает новую категорию для импорта (делегировано в сервис)."""
        category_id = self.import_service.create_category_for_import(
            self.structure_model, category_data, self.logger
        )
        if category_id:
            # Инвалидируем кэш для раздела
            section_id = category_data.get("section_id")
            if section_id:
                self._invalidate_categories_cache(section_id)
        return category_id

    # =============================================================================
    # ВНУТРЕННИЕ МЕТОДЫ - ВАЛИДАЦИЯ
    # =============================================================================

    def _validate_section_data(
        self, data: Dict[str, Any], section_id: Optional[int] = None
    ) -> ValidationResult:
        """Валидирует данные раздела (делегировано в ValidationService)."""
        return self.validation_service.validate_section_data(
            data=data,
            section_id=section_id,
            get_sections=self.get_sections,
        )

    def _validate_category_data(
        self, data: Dict[str, Any], category_id: Optional[int] = None
    ) -> ValidationResult:
        """Валидирует данные категории (делегировано в ValidationService)."""
        return self.validation_service.validate_category_data(
            data=data,
            category_id=category_id,
            has_duplicate_category=self.has_duplicate_category,
        )

    

    def _invalidate_structure_cache(self) -> None:
        """Инвалидирует кэш структуры (делегировано StructureCache)."""
        self.cache.invalidate_structure()

    def _invalidate_categories_cache(self, section_id: Optional[int]) -> None:
        """Инвалидирует кэш категорий для раздела (делегировано StructureCache)."""
        self.cache.invalidate_categories(section_id)

    

    def _handle_error(self, title: str, error: Exception) -> None:
        """Обрабатывает ошибки с полным логированием (делегировано ErrorEmitter)."""
        self._errors.handle(title, error)

    def _emit_error(self, title: str, message: str) -> None:
        """Отправляет сигнал об ошибке (делегировано ErrorEmitter)."""
        self._errors.emit(title, message)

    

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
        try:
            self.cache.clear_all()
        finally:
            self.logger.info("Кэш полностью очищен")
