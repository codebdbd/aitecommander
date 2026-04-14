# app/controllers/structure_modules/async_operations.py

"""Module for asynchronous structure operations.

Migrated to the new `run_db` facade instead of the legacy workers from
`app.utils.db.db_workers`. A local signal class with the same interface as
`StructureWorkerSignals` is defined to maintain compatibility.
"""

import logging
import time
from threading import Lock
from typing import TYPE_CHECKING, Any, Optional, Protocol

from PyQt6.QtCore import QObject, QThreadPool

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services import StructureService
from app.utils.db.api import run_db
from app.utils.metrics import get_metrics

from ..signals.signals import StructureSignals

if TYPE_CHECKING:
    from ..signals.handlers import AsyncSignalHandlers


class _MetricsProtocol(Protocol):
    def start(self, name: str) -> None: ...

    def stop(self, name: str) -> None: ...


class _SignalLike(Protocol):
    def connect(self, *args: Any, **kwargs: Any) -> object: ...

    def disconnect(self, *args: Any, **kwargs: Any) -> None: ...


class _NoOpMetrics:
    def start(self, _name: str) -> None:
        pass

    def stop(self, _name: str) -> None:
        pass


def _create_metrics() -> _MetricsProtocol:
    try:
        from app.utils.metrics.startup_metrics import get_metrics  # type: ignore

        return get_metrics()
    except Exception:  # надёжный фоллбэк: метрики отключены, логика не ломается
        return _NoOpMetrics()


metrics: _MetricsProtocol = _create_metrics()

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
        # Dedicated serialized DB pool for structure operations to reduce lock contention.
        self._structure_db_pool = QThreadPool(self)
        self._structure_db_pool.setMaxThreadCount(1)
        # Pass parent to ensure correct memory ownership
        self._worker_signals: StructureSignals = StructureSignals(self)
        # Thread-safe protection for shared state
        self._pending_tasks_lock = Lock()
        self._pending_tasks: dict[str, Any] = {}
        self._metrics_lock = Lock()
        self._active_metric_spans: set[str] = set()
        # Direct dependency on TopPanelsController to update top panels
        self.top_panels = top_panels_controller
        self._structure_pool_prewarm_started = False
        self._prewarm_structure_db_pool()

    def _prewarm_structure_db_pool(self) -> None:
        """Warm the dedicated structure DB worker thread before first real query."""
        if self._structure_pool_prewarm_started:
            return
        self._structure_pool_prewarm_started = True

        def _warm() -> int:
            row = self.db.connection.execute("SELECT 1").fetchone()
            return int(row[0]) if row else 0

        try:
            run_db(
                _warm,
                description="structure_db_prewarm",
                pool=self._structure_db_pool,
                on_error=lambda e: self.logger.debug(
                    "structure_db_prewarm failed: %s", e, exc_info=True
                ),
            )
        except Exception:
            self.logger.debug("Failed to schedule structure_db_prewarm", exc_info=True)

    def cleanup(self) -> None:
        """Proper cleanup for Qt objects.

        FIX: Disconnects all signals before deletion.
        Invoked on destruction to prevent memory leaks.
        """
        try:
            try:
                worker_signals = self._worker_signals
            except AttributeError:
                worker_signals = None
            if worker_signals is not None:
                # Disconnect all signals
                signals_to_disconnect = [
                    "spheres_loaded",
                    "structure_loaded",
                    "sections_loaded",
                    "categories_loaded",
                    "search_results",
                    "links_loaded",
                    "link_info_finished",
                    "count_finished",
                    "item_created",
                    "item_updated",
                    "item_deleted",
                    "operation_started",
                    "operation_finished",
                    "loading_started",
                    "update_ui",
                    "error",
                    "simple_error",
                ]

                for signal_name in signals_to_disconnect:
                    try:
                        signal = getattr(worker_signals, signal_name, None)
                        if signal and hasattr(signal, "disconnect"):
                            signal.disconnect()
                    except TypeError:  # Already disconnected
                        pass

                worker_signals.deleteLater()
                self.logger.debug("AsyncOperations: all signals disconnected")
        except Exception as e:
            self.logger.debug("Error during AsyncOperations cleanup: %s", e)

        # Clear pending tasks
        with self._pending_tasks_lock:
            if self._pending_tasks:
                self.logger.debug(
                    "AsyncOperations: clearing %d pending tasks",
                    len(self._pending_tasks),
                )
                self._pending_tasks.clear()

        # Clear metrics
        with self._metrics_lock:
            if self._active_metric_spans:
                self.logger.debug(
                    "AsyncOperations: clearing %d active metric spans",
                    len(self._active_metric_spans),
                )
                self._active_metric_spans.clear()

        # Cancel queued structure DB tasks; running task will complete naturally.
        try:
            self._structure_db_pool.clear()
        except Exception as e:
            self.logger.debug("Error during structure DB pool cleanup: %s", e)

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
                    MAX_PENDING_TASKS,
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
    def _start_async_metric(self, name: str, stop_signal: _SignalLike) -> None:
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

        def _on_spheres_loaded(spheres: list) -> None:
            self._worker_signals.spheres_loaded.emit(spheres)
            self._worker_signals.operation_finished.emit(self.tr("Spheres loaded"))

        run_db(
            _fetch,
            description="load_spheres",
            pool=self._structure_db_pool,
            on_finished=_on_spheres_loaded,
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
        started_ts = time.perf_counter()
        self.logger.info(
            "[Trace] AsyncOperations.load_structure_async enter sphere=%s",
            current_sphere_id,
        )

        def _fetch():
            worker_started_ts = time.perf_counter()
            worker_queue_ms = (worker_started_ts - started_ts) * 1000
            sections_started_ts = time.perf_counter()
            sections_raw = self.db.sections.get_sections(current_sphere_id)
            sections_query_ms = (time.perf_counter() - sections_started_ts) * 1000
            if not sections_raw:
                return [], current_sphere_id, worker_queue_ms, sections_query_ms, 0.0, 0.0
            sections_data = sections_raw
            section_ids = [s["id"] for s in sections_data]
            categories_started_ts = time.perf_counter()
            categories_raw = self.db.categories.get_categories_for_sections(section_ids)
            categories_query_ms = (time.perf_counter() - categories_started_ts) * 1000
            all_categories = categories_raw or []
            build_started_ts = time.perf_counter()
            categories_by_section: dict[int, list[dict[str, Any]]] = {}
            for category in all_categories:
                sid = category["section_id"]
                categories_by_section.setdefault(sid, []).append(category)
            for section in sections_data:
                section["categories"] = categories_by_section.get(section["id"], [])
            build_ms = (time.perf_counter() - build_started_ts) * 1000
            return (
                sections_data,
                current_sphere_id,
                worker_queue_ms,
                sections_query_ms,
                categories_query_ms,
                build_ms,
            )

        def _on_finished(payload):
            (
                sections_data,
                sphere_id,
                worker_queue_ms,
                sections_query_ms,
                categories_query_ms,
                build_ms,
            ) = payload
            finished_started_ts = time.perf_counter()
            main_thread_handoff_ms = (finished_started_ts - started_ts) * 1000 - (
                worker_queue_ms + sections_query_ms + categories_query_ms + build_ms
            )
            emit_started_ts = time.perf_counter()
            self._worker_signals.structure_loaded.emit(sections_data, sphere_id)
            emit_ms = (time.perf_counter() - emit_started_ts) * 1000
            total_ms = (time.perf_counter() - started_ts) * 1000
            self.logger.info(
                "[Perf] Structure load sphere=%s: total=%.2f ms worker_queue=%.2f ms main_thread_handoff=%.2f ms sections_query=%.2f ms categories_query=%.2f ms build=%.2f ms emit=%.2f ms sections=%s",
                sphere_id,
                total_ms,
                worker_queue_ms,
                max(0.0, main_thread_handoff_ms),
                sections_query_ms,
                categories_query_ms,
                build_ms,
                emit_ms,
                len(sections_data),
            )
            self._worker_signals.operation_finished.emit(self.tr("Structure loaded"))

        self.logger.info(
            "[Trace] AsyncOperations.load_structure_async scheduling run_db sphere=%s",
            current_sphere_id,
        )
        run_db(
            _fetch,
            description=f"load_structure(sphere_id={current_sphere_id})",
            pool=self._structure_db_pool,
            on_finished=_on_finished,
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Load error"),
                self.tr("Failed to load structure: {error}").format(error=e),
            ),
        )
        self.logger.info(
            "[Trace] AsyncOperations.load_structure_async run_db submitted sphere=%s submit_elapsed=%.2f ms",
            current_sphere_id,
            (time.perf_counter() - started_ts) * 1000.0,
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

        def _on_sections_loaded(sections: list) -> None:
            self._worker_signals.sections_loaded.emit(sections, sphere_id)
            self._worker_signals.operation_finished.emit(self.tr("Sections loaded"))

        run_db(
            lambda: self.db.sections.get_sections(sphere_id) or [],
            description=f"load_sections(sphere_id={sphere_id})",
            pool=self._structure_db_pool,
            on_finished=_on_sections_loaded,
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

        started_ts = time.perf_counter()
        self._worker_signals.operation_started.emit(
            self.tr("Loading categories for section {section_id}…").format(
                section_id=section_id,
            )
        )

        def _fetch_categories():
            db_started_ts = time.perf_counter()
            categories = self.db.categories.get_categories(section_id) or []
            db_ms = (time.perf_counter() - db_started_ts) * 1000
            return categories, db_ms

        def _on_categories_loaded(payload: tuple[list, float]) -> None:
            categories, db_ms = payload
            emit_started_ts = time.perf_counter()
            self._worker_signals.categories_loaded.emit(categories, section_id)
            emit_ms = (time.perf_counter() - emit_started_ts) * 1000
            total_ms = (time.perf_counter() - started_ts) * 1000
            metrics = get_metrics()
            metrics.record_timing("categories.load.total_ms", total_ms)
            stats = metrics.get_stats("categories.load.total_ms")
            self.logger.info(
                "[Perf] Categories load section=%s: total=%.2f ms db=%.2f ms emit=%.2f ms count=%s",
                section_id,
                total_ms,
                db_ms,
                emit_ms,
                len(categories),
            )
            if stats.get("count", 0) % 20 == 0 and stats.get("count", 0) > 0:
                self.logger.info(
                    "[PerfAgg] categories.load.total_ms: n=%s p50=%.2f ms p95=%.2f ms avg=%.2f ms",
                    stats.get("count", 0),
                    float(stats.get("p50", 0.0)),
                    float(stats.get("p95", 0.0)),
                    float(stats.get("avg", 0.0)),
                )
            self._worker_signals.operation_finished.emit(self.tr("Categories loaded"))

        run_db(
            _fetch_categories,
            description=f"load_categories(section_id={section_id})",
            pool=self._structure_db_pool,
            on_finished=_on_categories_loaded,
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
            self.logger.error("Sphere ID must be greater than 0 to create a section")
            return
        # Предчек дубликатов для улучшения UX: избегаем падения на ограничении уникальности
        try:
            existing = self.db.sections.get_sections(sphere_id) or []
            if any(
                str(row["name"]).strip().lower() == name.lower() for row in existing
            ):
                msg = self.tr(
                    'Section named "{name}" already exists in the selected sphere'
                ).format(name=name)
                self.logger.info(msg)
                # Покажем пользователю понятное сообщение без запуска воркера
                self._worker_signals.simple_error.emit(msg)
                return
        except Exception as e:
            # Не блокируем создание при сбое проверки, только логируем
            self.logger.warning("Failed to perform section duplicate pre-check: %s", e)

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

        def _on_section_created(res: tuple) -> None:
            self._worker_signals.item_created.emit(*res)
            self._worker_signals.operation_finished.emit(self.tr("Section created"))

        run_db(
            _create,
            description=f"create_section(name={name!r})",
            pool=self._structure_db_pool,
            on_finished=_on_section_created,
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
            self.logger.error("Section ID must be greater than 0 to create a category")
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

        def _on_category_created(res: tuple) -> None:
            self._worker_signals.item_created.emit(*res)
            self._worker_signals.operation_finished.emit(self.tr("Category created"))

        run_db(
            _create,
            description=f"create_category(name={name!r})",
            pool=self._structure_db_pool,
            on_finished=_on_category_created,
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

        def _on_section_updated(res: tuple) -> None:
            self._worker_signals.item_updated.emit(*res)
            self._worker_signals.operation_finished.emit(self.tr("Section updated"))

        run_db(
            _update,
            description=f"update_section(id={section_id})",
            pool=self._structure_db_pool,
            on_finished=_on_section_updated,
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

        def _on_category_updated(res: tuple) -> None:
            self._worker_signals.item_updated.emit(*res)
            self._worker_signals.operation_finished.emit(self.tr("Category updated"))

        run_db(
            _update,
            description=f"update_category(id={category_id})",
            pool=self._structure_db_pool,
            on_finished=_on_category_updated,
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

        def _on_section_deleted(res: tuple) -> None:
            self._worker_signals.item_deleted.emit(*res)
            self._worker_signals.operation_finished.emit(self.tr("Section deleted"))

        run_db(
            _delete,
            description=f"delete_section(id={section_id})",
            pool=self._structure_db_pool,
            on_finished=_on_section_deleted,
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
            self._worker_signals.operation_started.emit(self.tr("Deleting category…"))

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

            def _on_category_deleted(res: tuple) -> None:
                self._worker_signals.item_deleted.emit(*res)
                self._worker_signals.operation_finished.emit(
                    self.tr("Category deleted")
                )

            run_db(
                _delete,
                description=f"delete_category(id={category_id})",
                pool=self._structure_db_pool,
                on_finished=_on_category_deleted,
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

        def _on_count_completed(count_data: dict) -> None:
            self._worker_signals.item_updated.emit(
                "section_count", section_id, count_data
            )
            self._worker_signals.operation_finished.emit(self.tr("Count completed"))

        run_db(
            _count,
            description=f"count_nested(section_id={section_id})",
            pool=self._structure_db_pool,
            on_finished=_on_count_completed,
            on_error=lambda e: self._worker_signals.error.emit(
                self.tr("Count error"),
                self.tr("Failed to count items: {error}").format(error=e),
            ),
        )


# Экспорт классов для обратной совместимости
__all__ = ["AsyncOperations", "StructureSignals"]
