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

        # Режим батч-обновлений: коалесцирует множественные item_updated(category)
        self._batch_mode: bool = False
        self._batch_touched_sections: set[int] = set()

        # Метрики: момент начала переключения сферы (для последующего логирования времени)
        self._last_switch_started_ms: Optional[float] = None

        # Инициализация
        self._initialize_system()

        # Подключаем внутренние обработчики к бизнес-сигналам, чтобы
        # изменения, пришедшие не через воркеры, тоже приводили к
        # инвалидизации кэша и асинхронной перезагрузке UI
        try:
            self.item_added.connect(self._on_item_added)
            self.item_updated.connect(self._on_item_updated)
            self.item_deleted.connect(self._on_item_deleted)
            # Подключаем обработчик нового батч-сигнала
            self.items_batch_deleted.connect(self._on_items_batch_deleted)
            self.logger.info("[BL] Handlers connected for business id=%s", id(self))
        except Exception:
            # Защита от ошибок подключения сигналов, не ломаем инициализацию
            self.logger.warning(
                "Не удалось подключить внутренние обработчики бизнес-сигналов",
                exc_info=True,
            )

    def set_top_panels_controller(self, top_panels_controller: Any) -> None:
        """Внедрить TopPanelsController и распространить зависимость во все уровни.

        Явно сохраняем ссылку и прокидываем её в AsyncOperations и AsyncSignalHandlers,
        чтобы обработчики сигналов вызывали методы контроллера напрямую без getattr.
        """
        try:
            # Локальная ссылка в бизнес-логике (может использоваться UI/другими службами)
            setattr(self, "top_panels_controller", top_panels_controller)
        except Exception as e:
            self.logger.warning(
                f"Failed to set top_panels_controller on StructureBusinessLogic: {e}",
                exc_info=True,
            )
        try:
            # Прямая ссылка для асинхронного слоя
            if hasattr(self, "async_operations") and self.async_operations:
                self.async_operations.top_panels = top_panels_controller
        except Exception as e:
            self.logger.warning(
                f"Failed to inject TopPanelsController into AsyncOperations: {e}",
                exc_info=True,
            )
        try:
            # И немедленно для уже подключённых обработчиков сигналов
            if hasattr(self, "_async_handlers") and self._async_handlers:
                self._async_handlers.top_panels = top_panels_controller
        except Exception as e:
            self.logger.warning(
                f"Failed to inject TopPanelsController into AsyncSignalHandlers: {e}",
                exc_info=True,
            )

    def _initialize_system(self) -> None:
        """Инициализация системы."""
        self.logger.info("Инициализация StructureBusinessLogic")

        # Таймеры и дополнительные компоненты настраиваются напрямую в __init__

    

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

            # Зафиксируем момент старта переключения для последующей метрики
            try:
                self._last_switch_started_ms = time.monotonic()
            except Exception:
                self._last_switch_started_ms = None

            self.current_sphere_id = sphere_id

            # Очищаем кэш при смене сферы
            if old_sphere_id != sphere_id:
                self.cache_manager.invalidate(f"sphere_{old_sphere_id}")

            self.logger.info("Установлена текущая сфера: %s", sphere_id)
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
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике _on_item_added: %s", e, exc_info=True
            )

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
                # Если активен батч-режим — не запускаем загрузки/перезагрузку сразу
                if self._batch_mode:
                    try:
                        if isinstance(section_id, int) and section_id > 0:
                            self._batch_touched_sections.add(int(section_id))
                    except Exception:
                        pass
                    return
                # Обычный режим: сразу подгрузим категории раздела
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            self._invalidate_structure_cache()
            # Коалесцируем перезагрузку структуры, чтобы избежать дублей
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике _on_item_updated: %s", e, exc_info=True
            )

    # =============================================================================
    # BATСH-РЕЖИМ ДЛЯ КОНСОЛИДАЦИИ МНОЖЕСТВЕННЫХ ОБНОВЛЕНИЙ
    # =============================================================================
    def begin_batch(self) -> None:
        """Включает батч-режим: пер-item обновления коалесцируются."""
        try:
            self._batch_mode = True
            self._batch_touched_sections.clear()
        except Exception:
            # Даже при ошибке не падаем
            self._batch_mode = True

    def end_batch(self) -> None:
        """Завершает батч-режим: выполняет одну консолидацию загрузок/перезагрузки."""
        try:
            touched = set(self._batch_touched_sections)
        except Exception:
            touched = set()
        finally:
            self._batch_touched_sections.clear()
            self._batch_mode = False

        # Единожды загрузим категории для затронутых разделов
        try:
            for sid in touched:
                try:
                    if isinstance(sid, int) and sid > 0:
                        self.async_operations.load_categories_async(int(sid))
                except Exception as exc:
                    self.logger.debug("end_batch: failed to schedule load_categories_async for %s: %s", sid, exc, exc_info=True)
        except Exception as exc:
            self.logger.debug("end_batch: failed to iterate touched sections: %s", exc, exc_info=True)

        # И одна коалесцированная перезагрузка структуры сферы
        try:
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except Exception as exc:
            self.logger.debug("end_batch: failed to schedule structure reload: %s", exc, exc_info=True)

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
            self.logger.warning("_schedule_structure_reload: failed to schedule: %s", e, exc_info=True)

    def _perform_structure_reload(self) -> None:
        """Выполняет фактическую перезагрузку структуры текущей сферы."""
        try:
            self._invalidate_structure_cache()
            sphere_id = self.current_sphere_id
            if isinstance(sphere_id, int) and sphere_id > 0:
                self.async_operations.load_structure_async(sphere_id)
        except Exception as e:
            self.logger.error("_perform_structure_reload: %s", e, exc_info=True)

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
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике _on_item_deleted: %s", e, exc_info=True
            )

    def _on_items_batch_deleted(self, item_type: str, ids: list) -> None:
        """Батч-удаление элементов: одна инвалидизация и одна перезагрузка.

        Для совместимости по умолчанию выполняем консолидацию как для одиночных
        удалений, но без лавины событий.
        """
        try:
            total = len(ids) if isinstance(ids, (list, tuple)) else 0
            self.logger.info("[BL] items_batch_deleted: type=%s, count=%s", item_type, total)
            # Для ссылок используем небольшую задержку, чтобы коалесцировать
            if item_type == "link":
                self._schedule_structure_reload(200)
                return
            # Для категорий/разделов: немедленная консолидация
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике _on_items_batch_deleted: %s", e, exc_info=True
            )

    @handle_exceptions()
    def select_section(self, section_id: int) -> None:
        """Выбирает раздел и загружает его категории."""
        categories = self.get_categories(section_id)
        self.section_selected.emit(section_id)
        self.logger.debug("Выбран раздел %s с %s категориями", section_id, len(categories))

    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        """Выбирает категорию."""
        self.category_selected.emit(category_id)
        self.logger.debug("Выбрана категория %s", category_id)

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
        return self.utility_service.get_links(
            self.structure_model, category_id, self.logger
        )

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
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            self.item_added.emit(
                "section", int(sphere_id) if sphere_id else 0, section_data
            )
        finally:
            # Инвалидируем кэш по разделам и структуре
            if sphere_id:
                self.cache_manager.invalidate(f"sections_{sphere_id}")
            self._invalidate_structure_cache()
        return section_data or None

    @handle_exceptions()
    def update_section(
        self, section_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Обновляет раздел через сервис, эмитит сигнал и инвалидирует кэш."""
        ok = self.structure_service.update_section(section_id, data)
        if not ok:
            return None
        section_data = self.structure_service.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            self.item_updated.emit("section", section_id, section_data)
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
        sphere_id = (
            section_before.get("sphere_id")
            if isinstance(section_before, dict)
            else None
        )
        categories_before = (
            self.structure_service.get_categories(section_before.get("id", section_id))
            if section_before
            else []
        )
        categories_count = len(categories_before or [])
        # Информации о ссылках на уровне раздела нет в сервисе — возвращаем 0 для совместимости
        success = self.structure_service.delete_section(section_id)
        if success:
            try:
                self.item_deleted.emit("section", section_id)
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
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            # parent_id для категории — это section_id
            self.item_added.emit(
                "category", int(section_id) if section_id else 0, category_data
            )
        finally:
            self._invalidate_categories_cache(section_id)
        return category_data or None

    @handle_exceptions(default_return=[])
    def move_categories_batch(
        self, category_ids: List[int], target_section_id: int, base_row: int = 0
    ) -> List[int]:
        """Пакетно переносит категории в целевой раздел одним батчем (одна транзакция).

        - Не эмитит per-item сигналы, чтобы избежать лавины обновлений.
        - Инвалидирует кэши затронутых разделов и выполняет одну коалесцированную перезагрузку.
        Возвращает список фактически перенесённых id (дубликаты имён пропускаются).
        """
        if not category_ids or not isinstance(target_section_id, int) or target_section_id <= 0:
            return []

        # Соберём исходные разделы (минимально необходимое для инвалидирования)
        source_sections: set[int] = set()
        try:
            for cid in category_ids:
                try:
                    cdata = self.structure_service.get_category_by_id(int(cid))
                except Exception:
                    cdata = None
                if isinstance(cdata, dict):
                    sid = cdata.get("section_id")
                    if isinstance(sid, int) and sid > 0 and sid != target_section_id:
                        source_sections.add(int(sid))
        except Exception:
            # В случае ошибки просто продолжим без источников
            source_sections = set()

        # Включаем батч-режим для консолидации последующих загрузок
        self.begin_batch()
        try:
            moved_ids = self.structure_service.move_categories_to_section_bulk(
                category_ids, target_section_id, base_row
            )

            # Инвалидируем кэш категорий: источники + целевой раздел
            try:
                for sid in source_sections:
                    self._invalidate_categories_cache(sid)
            except Exception:
                pass
            self._invalidate_categories_cache(target_section_id)

            return moved_ids or []
        finally:
            # Одна консолидация загрузок/перезагрузки структуры
            self.end_batch()

    @handle_exceptions(default_return=[])
    def create_categories_bulk(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Пакетно создаёт категории через сервис и эмитит сигналы для UI.

        Возвращает список фактических категорий после операции (как новые, так и
        существующие из набора имён), упорядоченных по position.
        """
        if not items:
            return []
        # Выполняем пакетное создание
        created_or_existing = self.structure_service.create_categories_bulk(items)
        # Инвалидируем кэш и планируем одну перезагрузку структуры.
        try:
            touched_sections = {c.get("section_id") for c in (created_or_existing or []) if isinstance(c, dict)}
            for sid in touched_sections:
                if sid:
                    self._invalidate_categories_cache(sid)
            self._schedule_structure_reload(0)
        except Exception:
            pass
        return created_or_existing or []

    @handle_exceptions()
    def update_category(
        self, category_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Обновляет категорию через сервис, эмитит сигнал и инвалидирует кэш."""
        ok = self.structure_service.update_category(category_id, data)
        if not ok:
            return None
        category_data = self.structure_service.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            self.item_updated.emit("category", category_id, category_data)
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
        section_id = (
            category_before.get("section_id")
            if isinstance(category_before, dict)
            else None
        )
        success = self.structure_service.delete_category(category_id)
        if success:
            try:
                self.item_deleted.emit("category", category_id)
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
        self.logger.error("%s: %s", title, error_msg, exc_info=True)
        self._emit_error(title, error_msg)

    def _emit_error(self, title: str, message: str) -> None:
        """Отправляет сигнал об ошибке."""
        self.error_occurred.emit(title, message)
        self.logger.error("%s: %s", title, message)

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
