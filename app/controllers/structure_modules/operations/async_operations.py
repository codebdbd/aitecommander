# app/controllers/structure_modules/async_operations.py

"""Module for asynchronous structure operations.

Migrated to the new `run_db` facade instead of the legacy workers from
`app.utils.db.db_workers`. A local signal class with the same interface as
`StructureWorkerSignals` is defined to maintain compatibility.
"""

import logging
import time
from threading import Lock
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services import StructureService
from app.utils.db.api import run_db

from ..models.types import (
    AnyItemData,
    CategoryData,
    LinkData,
    SearchResultItem,
    SectionData,
    SphereData,
)
from ..signals.handlers import AsyncSignalHandlers
from ..signals.signals import StructureSignals

try:
    # Корректная точка доступа к метрикам старта
    from app.utils.metrics.startup_metrics import get_metrics  # type: ignore

    metrics = get_metrics()
except Exception:  # надёжный фоллбэк: метрики отключены, логика не ломается

    class _NoOpMetrics:
        def start(self, _name: str) -> None:
            pass

        def stop(self, _name: str) -> None:
            pass

    metrics = _NoOpMetrics()

logger = logging.getLogger(__name__)

# FIX: Limit the number of pending tasks
MAX_PENDING_TASKS = 100


class AsyncOperations(QObject):
    """Manage asynchronous structure operations.

    Inherits from QObject to ensure proper PyQt6 memory management.
    """

    def __init__(
        self,
        db: Database,
        logger: Optional[logging.Logger] = None,
        top_panels_controller: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.db = db
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)
        # Unified global task scheduler instead of QThreadPool.globalInstance()
        self._scheduler = get_task_scheduler()
        # Pass parent to ensure correct memory ownership
        self._worker_signals = StructureSignals(self)
        # Thread-safe protection for shared state
        self._pending_tasks_lock = Lock()
        self._pending_tasks = {}
        self._metrics_lock = Lock()
        self._active_metric_spans = set()
        # Direct dependency on TopPanelsController to update top panels
        self.top_panels = top_panels_controller

    def cleanup(self) -> None:
        """Proper cleanup for Qt objects.

        FIX: Disconnects all signals before deletion.
        Invoked on destruction to prevent memory leaks.
        """
        try:
            if self._worker_signals:
                # Disconnect all signals
                signals_to_disconnect = [
                    'spheres_loaded', 'structure_loaded', 'sections_loaded',
                    'categories_loaded', 'search_results', 'links_loaded',
                    'link_info_finished', 'count_finished', 'item_created',
                    'item_updated', 'item_deleted', 'operation_started',
                    'operation_finished', 'loading_started', 'update_ui',
                    'error', 'simple_error'
                ]
                
                for signal_name in signals_to_disconnect:
                    try:
                        signal = getattr(self._worker_signals, signal_name, None)
                        if signal and hasattr(signal, 'disconnect'):
                            signal.disconnect()
                    except TypeError:  # Already disconnected
                        pass

                self._worker_signals.deleteLater()
                self._worker_signals = None
                self.logger.debug("AsyncOperations: all signals disconnected")
        except Exception as e:
            self.logger.debug("Error during AsyncOperations cleanup: %s", e)

        # Clear pending tasks
        with self._pending_tasks_lock:
            if self._pending_tasks:
                self.logger.debug("AsyncOperations: clearing %d pending tasks", len(self._pending_tasks))
                self._pending_tasks.clear()

        # Clear metrics
        with self._metrics_lock:
            if self._active_metric_spans:
                self.logger.debug("AsyncOperations: clearing %d active metric spans", len(self._active_metric_spans))
                self._active_metric_spans.clear()

    def _add_pending_task(self, task_id: str, task_data: Any = True) -> bool:
        """Добавляет pending task с проверкой лимита.
        
        ИСПРАВЛЕНИЕ: Ограничивает количество pending tasks для предотвращения
        неконтролируемого роста памяти.
        
        Args:
            task_id: Уникальный идентификатор задачи
            task_data: Данные задачи (по умолчанию True)
            
        Returns:
            bool: True если задача добавлена, False если достигнут лимит
        """
        with self._pending_tasks_lock:
            if len(self._pending_tasks) >= MAX_PENDING_TASKS:
                self.logger.warning(
                    "Pending tasks limit (%d) reached, dropping oldest task",
                    MAX_PENDING_TASKS
                )
                # Удаляем самую старую задачу (FIFO)
                if self._pending_tasks:
                    oldest_key = next(iter(self._pending_tasks))
                    del self._pending_tasks[oldest_key]
            
            self._pending_tasks[task_id] = task_data
            return True
    
    def _remove_pending_task(self, task_id: str) -> None:
        """Удаляет pending task по ID."""
        with self._pending_tasks_lock:
            self._pending_tasks.pop(task_id, None)
    
    def get_worker_signals(self) -> StructureSignals:
        """Возвращает объект сигналов воркеров для подключения."""
        return self._worker_signals

    def connect_signal_handlers(self, handlers: "AsyncSignalHandlers") -> None:
        """Подключает сигналы воркеров к обработчикам.

        Гарантирует согласованность подписок между `StructureWorkerSignals` и
        методами `AsyncSignalHandlers`.
        """
        # ✅ Явная передача зависимостей вместо getattr
        handlers.top_panels = self.top_panels

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
        # Ошибки
        self._worker_signals.error.connect(handlers.on_error)
        self._worker_signals.simple_error.connect(handlers.on_simple_error)

    def disconnect_signal_handlers(self, handlers: "AsyncSignalHandlers") -> None:
        """Отписывает обработчики от сигналов воркеров.

        Безопасно игнорирует уже отсоединённые связи.
        """

        def _disc(signal, handler, name: str) -> None:
            try:
                signal.disconnect(handler)
            except (TypeError, RuntimeError) as e:
                # ✅ Ожидаемые ошибки отключения - логируем в debug
                self.logger.debug(
                    "Expected disconnection issue for signal '%s': %s", name, e
                )
            except Exception as e:
                # ✅ Неожиданные ошибки - логируем с полным traceback
                self.logger.exception(
                    "Unexpected disconnection error for signal '%s': %s", name, e
                )
                # ✅ Не маскируем критические проблемы
                raise

        _disc(
            self._worker_signals.spheres_loaded,
            handlers.on_spheres_loaded,
            "spheres_loaded",
        )
        _disc(
            self._worker_signals.structure_loaded,
            handlers.on_structure_loaded,
            "structure_loaded",
        )
        _disc(
            self._worker_signals.sections_loaded,
            handlers.on_sections_loaded,
            "sections_loaded",
        )
        _disc(
            self._worker_signals.categories_loaded,
            handlers.on_categories_loaded,
            "categories_loaded",
        )
        _disc(
            self._worker_signals.search_results,
            handlers.on_search_results,
            "search_results",
        )
        _disc(
            self._worker_signals.links_loaded, handlers.on_links_loaded, "links_loaded"
        )
        _disc(
            self._worker_signals.link_info_finished,
            handlers.on_link_info_finished,
            "link_info_finished",
        )
        _disc(
            self._worker_signals.count_finished,
            handlers.on_count_finished,
            "count_finished",
        )
        _disc(
            self._worker_signals.item_created, handlers.on_item_created, "item_created"
        )
        _disc(
            self._worker_signals.item_updated, handlers.on_item_updated, "item_updated"
        )
        _disc(
            self._worker_signals.item_deleted, handlers.on_item_deleted, "item_deleted"
        )
        _disc(
            self._worker_signals.operation_started,
            handlers.on_operation_started,
            "operation_started",
        )
        _disc(
            self._worker_signals.operation_finished,
            handlers.on_operation_finished,
            "operation_finished",
        )
        _disc(
            self._worker_signals.loading_started,
            handlers.on_loading_started,
            "loading_started",
        )
        _disc(self._worker_signals.update_ui, handlers.on_update_ui, "update_ui")
        _disc(self._worker_signals.error, handlers.on_error, "error")
        _disc(
            self._worker_signals.simple_error, handlers.on_simple_error, "simple_error"
        )

    # ===== Метрики асинхронных операций =====
    def _start_async_metric(self, name: str, stop_signal: pyqtSignal) -> None:
        """Start a metrics span and stop it on the first `stop_signal` emission.

        Prevents duplicated spans: subsequent calls are ignored while the span is active.
        """
        try:
            # ✅ Thread-safe check and update
            with self._metrics_lock:
                if name in self._active_metric_spans:
                    return
                metrics.start(name)
                self._active_metric_spans.add(name)

            # ✅ Use a local closure to avoid memory leaks
            def _on_stop(*_args):
                try:
                    metrics.stop(name)
                except Exception:
                    # Log at debug level only to avoid noisy user logs
                    self.logger.debug("Metrics: failed to stop span %s", name)
                try:
                    stop_signal.disconnect(_on_stop)
                except Exception:
                    pass
                # ✅ Thread-safe removal
                with self._metrics_lock:
                    self._active_metric_spans.discard(name)

            stop_signal.connect(_on_stop)
        except Exception:
            # Never break business logic because of metrics failures
            self.logger.debug("Metrics: failed to start span %s", name)

    def load_spheres_async(self) -> None:
        """Асинхронная загрузка всех сфер через run_db."""
        # Метрика асинхронной загрузки сфер: старт здесь, стоп по сигналу spheres_loaded
        self._start_async_metric(
            "async:spheres_load", self._worker_signals.spheres_loaded
        )
        self._worker_signals.operation_started.emit(self.tr("Loading spheres…"))

        def _fetch():
            return self.db.spheres.get_spheres() or []

        run_db(
            _fetch,
            description="load_spheres",
            on_finished=lambda spheres: (
                self._worker_signals.spheres_loaded.emit(spheres),
                self._worker_signals.operation_finished.emit(self.tr("Spheres loaded")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Load error"),
                self.tr("Failed to load spheres: {error}").format(error=e),
            ),
        )

    def load_structure_async(self, current_sphere_id: int) -> None:
        """Асинхронная загрузка структуры для сферы через run_db."""
        if not isinstance(current_sphere_id, int) or current_sphere_id <= 0:
            self.logger.error("Invalid sphere ID: %s", current_sphere_id)
            return

        desc = self.tr("Loading structure for sphere {sphere_id}…").format(
            sphere_id=current_sphere_id,
        )
        # Метрика асинхронной загрузки структуры: старт здесь, стоп по сигналу structure_loaded
        self._start_async_metric(
            "async:structure_load", self._worker_signals.structure_loaded
        )
        self._worker_signals.operation_started.emit(desc)

        def _fetch():
            sections_raw = self.db.sections.get_sections(current_sphere_id)
            if not sections_raw:
                return [], current_sphere_id
            sections_data = sections_raw
            section_ids = [s["id"] for s in sections_data]
            categories_raw = self.db.categories.get_categories_for_sections(section_ids)
            all_categories = categories_raw or []
            categories_by_section = {}
            for category in all_categories:
                sid = category["section_id"]
                categories_by_section.setdefault(sid, []).append(category)
            for section in sections_data:
                section["categories"] = categories_by_section.get(section["id"], [])
            return sections_data, current_sphere_id

        def _on_finished(payload):
            sections_data, sphere_id = payload
            self._worker_signals.structure_loaded.emit(sections_data, sphere_id)
            self._worker_signals.operation_finished.emit(self.tr("Structure loaded"))

        run_db(
            _fetch,
            description=f"load_structure(sphere_id={current_sphere_id})",
            on_finished=_on_finished,
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Load error"),
                self.tr("Failed to load structure: {error}").format(error=e),
            ),
        )

    def load_sections_async(self, sphere_id: int) -> None:
        """Асинхронная загрузка разделов для сферы через run_db."""
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.error("Invalid sphere ID: %s", sphere_id)
            return

        self._worker_signals.operation_started.emit(
            self.tr("Loading sections for sphere {sphere_id}…").format(
                sphere_id=sphere_id,
            )
        )

        run_db(
            lambda: self.db.sections.get_sections(sphere_id) or [],
            description=f"load_sections(sphere_id={sphere_id})",
            on_finished=lambda sections: (
                self._worker_signals.sections_loaded.emit(sections, sphere_id),
                self._worker_signals.operation_finished.emit(self.tr("Sections loaded")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Load error"),
                self.tr("Failed to load sections: {error}").format(error=e),
            ),
        )

    def load_categories_async(self, section_id: int) -> None:
        """Асинхронная загрузка категорий для раздела через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Invalid section ID: %s", section_id)
            return

        self._worker_signals.operation_started.emit(
            self.tr("Loading categories for section {section_id}…").format(
                section_id=section_id,
            )
        )

        run_db(
            lambda: self.db.categories.get_categories(section_id) or [],
            description=f"load_categories(section_id={section_id})",
            on_finished=lambda categories: (
                self._worker_signals.categories_loaded.emit(categories, section_id),
                self._worker_signals.operation_finished.emit(self.tr("Categories loaded")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Load error"),
                self.tr("Failed to load categories: {error}").format(error=e),
            ),
        )

    def create_section_async(self, data: dict[str, Any]) -> None:
        """Асинхронное создание раздела через run_db."""
        if not isinstance(data, dict):
            self.logger.error("Section data must be a dict")
            return
        name = (data.get("name") or "").strip()
        sphere_id = data.get("sphere_id")
        if not name:
            self.logger.error("Section name is required")
            return
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.error(
                "Sphere ID must be greater than 0 to create a section"
            )
            return
        # Предчек дубликатов для улучшения UX: избегаем падения на ограничении уникальности
        try:
            existing = self.db.sections.get_sections(sphere_id) or []
            if any(
                str(row["name"]).strip().lower() == name.lower() for row in existing
            ):
                msg = self.tr(
                    "Section named \"{name}\" already exists in the selected sphere"
                ).format(name=name)
                self.logger.info(msg)
                # Покажем пользователю понятное сообщение без запуска воркера
                self._worker_signals.simple_error.emit(msg)
                return
        except Exception as e:
            # Не блокируем создание при сбое проверки, только логируем
            self.logger.warning(
                "Failed to perform section duplicate pre-check: %s", e
            )

        def _create():
            service = StructureService(self.db)
            item_id = service.create_section(dict(data))
            parent_id = sphere_id
            payload = dict(data)
            payload["id"] = item_id
            return ("section", parent_id, payload)

        self._worker_signals.operation_started.emit(
            self.tr("Creating section: {name}…").format(
                name=name or self.tr("Untitled"),
            )
        )

        run_db(
            _create,
            description=f"create_section(name={name!r})",
            on_finished=lambda res: (
                self._worker_signals.item_created.emit(*res),
                self._worker_signals.operation_finished.emit(self.tr("Section created")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Create error"),
                self.tr("Failed to create section: {error}").format(error=e),
            ),
        )

    def create_category_async(self, data: dict[str, Any]) -> None:
        """Асинхронное создание категории через run_db."""
        if not isinstance(data, dict):
            self.logger.error("Category data must be a dict")
            return
        name = (data.get("name") or "").strip()
        section_id = data.get("section_id")
        if not name:
            self.logger.error("Category name is required")
            return
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(
                "Section ID must be greater than 0 to create a category"
            )
            return

        def _create():
            service = StructureService(self.db)
            item_id = service.create_category(dict(data))
            parent_id = section_id
            payload = dict(data)
            payload["id"] = item_id
            return ("category", parent_id, payload)

        self._worker_signals.operation_started.emit(
            self.tr("Creating category: {name}…").format(
                name=name or self.tr("Untitled"),
            )
        )

        run_db(
            _create,
            description=f"create_category(name={name!r})",
            on_finished=lambda res: (
                self._worker_signals.item_created.emit(*res),
                self._worker_signals.operation_finished.emit(self.tr("Category created")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Create error"),
                self.tr("Failed to create category: {error}").format(error=e),
            ),
        )

    def update_section_async(self, section_id: int, data: dict[str, Any]) -> None:
        """Асинхронное обновление раздела через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Invalid section ID: %s", section_id)
            return
        if not isinstance(data, dict):
            self.logger.error("Section data must be a dict")
            return
        name = data.get("name")
        if name is not None and not str(name).strip():
            self.logger.error("Section name must be a non-empty string")
            return
        self._worker_signals.operation_started.emit(
            self.tr("Updating section: {name}…").format(
                name=data.get("name", self.tr("ID {id}").format(id=section_id)),
            )
        )

        def _update():
            StructureService(self.db).update_section(section_id, dict(data))
            return ("section", section_id, dict(data))

        run_db(
            _update,
            description=f"update_section(id={section_id})",
            on_finished=lambda res: (
                self._worker_signals.item_updated.emit(*res),
                self._worker_signals.operation_finished.emit(self.tr("Section updated")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Update error"),
                self.tr("Failed to update section: {error}").format(error=e),
            ),
        )

    def update_category_async(self, category_id: int, data: dict[str, Any]) -> None:
        """Асинхронное обновление категории через run_db."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.error("Invalid category ID: %s", category_id)
            return
        if not isinstance(data, dict):
            self.logger.error("Category data must be a dict")
            return
        name = data.get("name")
        if name is not None and not str(name).strip():
            self.logger.error("Category name must be a non-empty string")
            return
        self._worker_signals.operation_started.emit(
            self.tr("Updating category: {name}…").format(
                name=data.get("name", self.tr("ID {id}").format(id=category_id)),
            )
        )

        def _update():
            StructureService(self.db).update_category(category_id, dict(data))
            return ("category", category_id, dict(data))

        run_db(
            _update,
            description=f"update_category(id={category_id})",
            on_finished=lambda res: (
                self._worker_signals.item_updated.emit(*res),
                self._worker_signals.operation_finished.emit(self.tr("Category updated")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Update error"),
                self.tr("Failed to update category: {error}").format(error=e),
            ),
        )

    def delete_section_async(self, section_id: int) -> None:
        """Асинхронное удаление раздела через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Invalid section ID: %s", section_id)
            return
        self._worker_signals.operation_started.emit(
            self.tr("Deleting section ID {section_id}…").format(section_id=section_id)
        )

        def _delete():
            old_data = {}
            try:
                row = self.db.sections.get_section_by_id(section_id)
                if row:
                    old_data = dict(row)
            except Exception:
                old_data = {}
            StructureService(self.db).delete_section(section_id)
            return ("section", section_id, old_data)

        run_db(
            _delete,
            description=f"delete_section(id={section_id})",
            on_finished=lambda res: (
                self._worker_signals.item_deleted.emit(*res),
                self._worker_signals.operation_finished.emit(self.tr("Section deleted")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Delete error"),
                self.tr("Failed to delete section: {error}").format(error=e),
            ),
        )

    def delete_category_async(self, category_id: int) -> Optional[str]:
        """Асинхронное удаление категории с улучшенной обработкой ошибок

        Args:
            category_id: ID категории для удаления

        Returns:
            str: ID задачи или None при ошибке
        """
        try:
            if not isinstance(category_id, int) or category_id <= 0:
                error_msg = self.tr("Invalid category ID: {category_id}").format(
                    category_id=category_id
                )
                self.logger.error(error_msg)
                self._worker_signals.error.emit(self.tr("Delete error"), error_msg)
                return None

            self.logger.info("Starting async deletion of category %s", category_id)
            self._worker_signals.operation_started.emit(
                self.tr("Deleting category…")
            )

            def _delete():
                old_data = {}
                try:
                    row = self.db.categories.get_category_by_id(category_id)
                    if row:
                        old_data = dict(row)
                except Exception:
                    old_data = {}
                StructureService(self.db).delete_category(category_id)
                return ("category", category_id, old_data)

            task_id = f"del_cat_{category_id}_{time.time()}"
            # ИСПРАВЛЕНИЕ: Используем helper метод с проверкой лимита
            self._add_pending_task(task_id, True)

            run_db(
                _delete,
                description=f"delete_category(id={category_id})",
                on_finished=lambda res: (
                    self._worker_signals.item_deleted.emit(*res),
                    self._worker_signals.operation_finished.emit(self.tr("Category deleted")),
                ),
                on_error=lambda e: self._worker_signals.error.emit(
                    self.tr("Delete error"),
                    self.tr("Failed to delete category: {error}").format(error=e),
                ),
            )

            return task_id

        except Exception as e:
            error_msg = self.tr("Failed to start deletion task: {error}").format(
                error=str(e)
            )
            self.logger.error("%s", error_msg, exc_info=True)
            self._worker_signals.error.emit(self.tr("Delete error"), error_msg)
            return None

    def count_nested_objects_async(self, section_id: int) -> None:
        """Асинхронный подсчет вложенных объектов (категорий и ссылок) через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Invalid section ID: %s", section_id)
            return

        self._worker_signals.operation_started.emit(
            self.tr("Counting objects for section {section_id}…").format(
                section_id=section_id,
            )
        )

        def _count():
            categories_data = self.db.categories.get_categories(section_id)
            categories_count = len(categories_data) if categories_data else 0
            links_count = 0
            if categories_data:
                for category_dict in categories_data:
                    links_data = self.db.links.get_links(category_dict["id"])
                    if links_data:
                        links_count += len(links_data)
            return {
                "section_id": section_id,
                "categories_count": categories_count,
                "links_count": links_count,
            }

        run_db(
            _count,
            description=f"count_nested(section_id={section_id})",
            on_finished=lambda count_data: (
                self._worker_signals.item_updated.emit(
                    "section_count", section_id, count_data
                ),
                self._worker_signals.operation_finished.emit(self.tr("Count completed")),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Count error"),
                self.tr("Failed to count items: {error}").format(error=e),
            ),
        )


class AsyncSignalHandlers(QObject):
    """Класс для обработки сигналов от асинхронных операций.
    
    Наследуется от QObject для правильного использования слотов PyQt6.
    """

    def __init__(self, controller_instance, top_panels_controller: Optional[Any] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.controller = controller_instance
        self.logger = controller_instance.logger
        # ✅ Явная передача зависимости вместо инъекции
        self.top_panels: Optional[Any] = top_panels_controller

    @pyqtSlot(list)
    def on_spheres_loaded(self, spheres: list[SphereData]) -> None:
        """Обработчик завершения загрузки сфер."""
        try:
            self.logger.info("Загружено %s сфер", len(spheres))
            if hasattr(self.controller, "spheres_loaded"):
                self.controller.spheres_loaded.emit(spheres)
        except (AttributeError, TypeError) as e:
            # ✅ Ожидаемые ошибки - логируем warning
            self.logger.warning("Expected error in on_spheres_loaded: %s", e)
        except Exception as e:
            # ✅ Неожиданные ошибки - полный traceback
            self.logger.exception("Critical error in on_spheres_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_structure_loaded(
        self, structure: list[SectionData], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки структуры."""
        try:
            self.logger.debug(
                "Загружена структура для сферы %s: %s разделов",
                sphere_id,
                len(structure),
            )
            # Перф-метрика: время от начала переключения сферы до готовности структуры
            try:
                start = getattr(self.controller, "_last_switch_started_ms", None)
                if isinstance(start, (int, float)) and start > 0:
                    import time as _time

                    elapsed_ms = int((_time.monotonic() - float(start)) * 1000)
                    self.logger.info(
                        "[Perf] Переключение сферы %s: структура загружена за %d мс",
                        sphere_id,
                        elapsed_ms,
                    )
                    # Сбрасываем маркер, чтобы не мешал последующим измерениям
                    try:
                        self.controller._last_switch_started_ms = None
                    except Exception:
                        pass
            except Exception:
                # Никогда не ломаем UI из-за метрик
                pass
            # Опционально отбрасываем устаревшие снапшоты, если включен флаг в конфиге
            try:
                from app.config_data import app_config
                drop_stale = bool(app_config.ui.get_drop_stale_structure_snapshots())
            except Exception:
                drop_stale = False
            if drop_stale:
                try:
                    current = getattr(self.controller, "current_sphere_id", None)
                    if (
                        isinstance(current, int)
                        and current > 0
                        and current != sphere_id
                    ):
                        self.logger.info(
                            "Пропуск structure_loaded: загружена сфера %s, текущая = %s (drop_stale enabled)",
                            sphere_id,
                            current,
                        )
                        return
                except Exception:
                    # Никогда не ломаем UI из-за диагностики
                    pass

            # Кэшируем результат в бизнес-логике, если доступен cache_manager
            try:
                cache = getattr(self.controller, "cache_manager", None)
                if cache and hasattr(cache, "set"):
                    cache.set(f"structure_{int(sphere_id)}", structure or [])
            except Exception:
                # Кэш — вспомогательная оптимизация; ошибки кэширования не критичны
                pass
            if hasattr(self.controller, "structure_loaded"):
                self.controller.structure_loaded.emit(structure)
        except (AttributeError, TypeError) as e:
            # ✅ Ожидаемые ошибки - логируем warning
            self.logger.warning("Expected error in on_structure_loaded: %s", e)
        except Exception as e:
            # ✅ Неожиданные ошибки - полный traceback
            self.logger.exception("Critical error in on_structure_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_sections_loaded(
        self, sections: list[SectionData], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки разделов."""
        try:
            self.logger.info(
                "Загружено %s разделов для сферы %s", len(sections), sphere_id
            )
            if hasattr(self.controller, "sections_loaded"):
                self.controller.sections_loaded.emit(sections, sphere_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_sections_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_sections_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_categories_loaded(
        self, categories: list[CategoryData], section_id: int
    ) -> None:
        """Обработчик завершения загрузки категорий.

        ВАЖНО: ретранслируем корректный сигнал `categories_loaded(categories, section_id)`,
        а не `section_selected`, чтобы UI получил именно событие загрузки категорий.
        """
        try:
            self.logger.info(
                "Загружено %s категорий для раздела %s", len(categories), section_id
            )
            if hasattr(self.controller, "categories_loaded"):
                self.controller.categories_loaded.emit(categories, section_id)
            else:
                # Fallback: если у контроллера нет нового сигнала categories_loaded,
                # ретранслируем уведомление о выборе раздела без передачи категорий
                if hasattr(self.controller, "section_selected"):
                    self.controller.section_selected.emit(section_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_categories_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_categories_loaded: %s", e)
            raise

    # ===== CRUD =====
    @pyqtSlot(str, int, dict)
    def on_item_created(
        self, item_type: str, parent_id: int, item_data: AnyItemData
    ) -> None:
        """Создан элемент структуры."""
        try:
            name = (
                item_data.get("name", "Unknown")
                if isinstance(item_data, dict)
                else "Unknown"
            )
            self.logger.info("Создан %s (parent_id=%s): %s", item_type, parent_id, name)
            # Контроллер (StructureBusinessLogic) использует сигнал item_added
            if hasattr(self.controller, "item_added"):
                self.controller.item_added.emit(item_type, parent_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == "category":
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, "_invalidate_categories_cache"):
                        self.controller._invalidate_categories_cache(parent_id)
                    if hasattr(self.controller, "async_operations"):
                        self.controller.async_operations.load_categories_async(
                            parent_id
                        )
                elif item_type == "section":
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    if isinstance(sphere_id, int) and sphere_id > 0:
                        # Централизуем перезагрузку структуры в бизнес-логике с дебаунсом
                        if hasattr(self.controller, "_schedule_structure_reload"):
                            self.controller._schedule_structure_reload(delay_ms=150)
            except Exception as e2:
                self.logger.warning(
                    "Не удалось инициировать обновление UI после создания %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_item_created: %s", e, exc_info=True
            )

    @pyqtSlot(str, int, dict)
    def on_item_updated(
        self, item_type: str, item_id: int, item_data: AnyItemData
    ) -> None:
        """Обновлён элемент структуры."""
        try:
            self.logger.info("Обновлён %s id=%s", item_type, item_id)
            if hasattr(self.controller, "item_updated"):
                self.controller.item_updated.emit(item_type, item_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == "category":
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, "_invalidate_categories_cache"):
                        self.controller._invalidate_categories_cache(
                            item_data.get("section_id")
                        )
                    if hasattr(self.controller, "async_operations"):
                        self.controller.async_operations.load_categories_async(
                            item_data.get("section_id")
                        )
                elif item_type == "section":
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    if isinstance(sphere_id, int) and sphere_id > 0:
                        # Централизуем перезагрузку структуры в бизнес-логике с дебаунсом
                        if hasattr(self.controller, "_schedule_structure_reload"):
                            self.controller._schedule_structure_reload(delay_ms=150)
            except Exception as e2:
                self.logger.warning(
                    "Не удалось инициировать обновление UI после обновления %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_item_updated: %s", e, exc_info=True
            )

    @pyqtSlot(str, int, dict)
    def on_item_deleted(
        self, item_type: str, item_id: int, old_data: AnyItemData
    ) -> None:
        """Удалён элемент структуры.

        Примечание: контроллер ожидает сигнатуру (str, int), поэтому `old_data`
        используется только для логирования и не передается далее.
        """
        try:
            self.logger.info("Удалён %s id=%s", item_type, item_id)
            if hasattr(self.controller, "item_deleted"):
                self.controller.item_deleted.emit(item_type, item_id)
            # Обновление после удаления
            try:
                if item_type == "category":
                    section_id = (
                        (old_data or {}).get("section_id")
                        if isinstance(old_data, dict)
                        else None
                    )
                    if section_id and hasattr(
                        self.controller, "_invalidate_categories_cache"
                    ):
                        self.controller._invalidate_categories_cache(section_id)
                    if section_id and hasattr(self.controller, "async_operations"):
                        self.controller.async_operations.load_categories_async(
                            section_id
                        )
                elif item_type == "section":
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if isinstance(sphere_id, int) and sphere_id > 0:
                        # Централизуем перезагрузку структуры в бизнес-логике с дебаунсом
                        if hasattr(self.controller, "_schedule_structure_reload"):
                            self.controller._schedule_structure_reload(delay_ms=150)
            except Exception as e2:
                self.logger.warning(
                    "Не удалось инициировать обновление UI после удаления %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_item_deleted: %s", e, exc_info=True
            )

    @pyqtSlot(str, str)
    def on_error(self, title: str, message: str) -> None:
        try:
            self.logger.error("%s: %s", title, message)
            # Новый сигнал контроллера
            if hasattr(self.controller, "error_occurred"):
                self.controller.error_occurred.emit(title, message)
            # Совместимость со старым именем
            elif hasattr(self.controller, "error"):
                self.controller.error.emit(title, message)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_error: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_error: %s", e)
            raise

    @pyqtSlot(str)
    def on_simple_error(self, message: str) -> None:
        try:
            self.logger.error(message)
            if hasattr(self.controller, "simple_error"):
                self.controller.simple_error.emit(message)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_simple_error: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_simple_error: %s", e)
            raise

    @pyqtSlot(str)
    def on_operation_started(self, description: str) -> None:
        try:
            # Сообщения о структуре чрезмерно частые — логируем их на DEBUG
            if "структур" in description.lower():
                self.logger.debug(description)
            else:
                self.logger.info(description)
            if hasattr(self.controller, "operation_started"):
                self.controller.operation_started.emit(description)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_operation_started: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_operation_started: %s", e)
            raise

    @pyqtSlot(str)
    def on_operation_finished(self, description: str) -> None:
        try:
            # Сообщения о структуре чрезмерно частые — логируем их на DEBUG
            if "структур" in description.lower():
                self.logger.debug(description)
            else:
                self.logger.info(description)
            if hasattr(self.controller, "operation_finished"):
                self.controller.operation_finished.emit(description)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_operation_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_operation_finished: %s", e)
            raise

    @pyqtSlot()
    def on_loading_started(self) -> None:
        try:
            self.logger.debug("Начата загрузка...")
            if hasattr(self.controller, "loading_started"):
                self.controller.loading_started.emit()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_loading_started: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_loading_started: %s", e)
            raise

    # ===== Обновление UI =====
    @pyqtSlot(int)
    def on_update_ui(self, category_id: int) -> None:
        try:
            self.logger.debug("Обновление UI для категории %s", category_id)
            if hasattr(self.controller, "update_ui"):
                self.controller.update_ui.emit(category_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_ui: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_ui: %s", e)
            raise

    @pyqtSlot()
    def on_update_favorites(self) -> None:
        try:
            self.logger.debug("Обновление избранного (через TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels не инжектирован; пропускаем обновление избранного"
                )
                return
            self.top_panels.request_favorites_refresh()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_favorites: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_favorites: %s", e)
            raise

    @pyqtSlot()
    def on_update_recent_links(self) -> None:
        try:
            self.logger.debug("Обновление недавних ссылок (через TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels не инжектирован; пропускаем обновление недавних ссылок"
                )
                return
            self.top_panels.request_recents_refresh()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_recent_links: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_recent_links: %s", e)
            raise

    # ===== Поиск / Ссылки / Подсчёт =====
    @pyqtSlot(list)
    def on_search_results(self, results: list[SearchResultItem]) -> None:
        try:
            self.logger.info("Результаты поиска: %s", len(results))
            if hasattr(self.controller, "search_results"):
                self.controller.search_results.emit(results)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_search_results: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_search_results: %s", e)
            raise

    @pyqtSlot(list, int, int)
    def on_links_loaded(
        self, links: list[LinkData], category_id: int, task_id: int
    ) -> None:
        try:
            self.logger.info(
                "Загружено ссылок: %s (category_id=%s, task_id=%s)",
                len(links),
                category_id,
                task_id,
            )
            if hasattr(self.controller, "links_loaded"):
                self.controller.links_loaded.emit(links, category_id, task_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_links_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_links_loaded: %s", e)
            raise

    @pyqtSlot(dict)
    def on_link_info_finished(self, info: LinkData) -> None:
        try:
            self.logger.debug("Получена информация о ссылке")
            if hasattr(self.controller, "link_info_finished"):
                self.controller.link_info_finished.emit(info)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_link_info_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_link_info_finished: %s", e)
            raise

    @pyqtSlot(int, list, object)
    def on_count_finished(
        self, fav_count: int, links: list[LinkData], link: object
    ) -> None:
        try:
            self.logger.info("Подсчёт избранных завершён: %s", fav_count)
            if hasattr(self.controller, "count_finished"):
                self.controller.count_finished.emit(fav_count, links, link)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_count_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_count_finished: %s", e)
            raise


# Экспорт классов для обратной совместимости
__all__ = ["AsyncOperations", "StructureSignals", "AsyncSignalHandlers"]
