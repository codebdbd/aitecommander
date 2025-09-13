# app/controllers/structure_modules/async_operations.py

"""Модуль для асинхронных операций структуры.

Переведён на новый фасад `run_db` вместо легаси-воркеров из
`app.utils.db.db_workers`. Для сохранения совместимости определён локальный
класс сигналов с тем же интерфейсом, что и `StructureWorkerSignals`.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services import StructureService
from app.utils.db.api import run_db

try:
    # Корректная точка доступа к метрикам старта
    from app.utils.metrics.startup_metrics import get_metrics  # type: ignore

    metrics = get_metrics()
except Exception:  # надёжный фолбэк: метрики отключены, логика не ломается

    class _NoOpMetrics:
        def start(self, _name: str) -> None:
            pass

        def stop(self, _name: str) -> None:
            pass

    metrics = _NoOpMetrics()

logger = logging.getLogger(__name__)


class StructureSignals(QObject):
    """Сигналы для асинхронных операций со структурой (совместимы с легаси).

    Повторяет интерфейс `StructureWorkerSignals` из app.utils.db.db_workers.
    """

    # Загрузка данных
    spheres_loaded: pyqtSignal = pyqtSignal(list)  # List[Dict]
    structure_loaded: pyqtSignal = pyqtSignal(list, int)  # List[Dict], sphere_id
    sections_loaded: pyqtSignal = pyqtSignal(list, int)  # List[Dict], sphere_id
    categories_loaded: pyqtSignal = pyqtSignal(list, int)  # List[Dict], section_id
    links_loaded: pyqtSignal = pyqtSignal(list, int, int)  # совместимость

    # Поиск
    search_results: pyqtSignal = pyqtSignal(list)

    # Подсчет
    count_finished: pyqtSignal = pyqtSignal(int, list, object)

    # CRUD
    item_created: pyqtSignal = pyqtSignal(str, int, dict)
    item_updated: pyqtSignal = pyqtSignal(str, int, dict)
    item_deleted: pyqtSignal = pyqtSignal(str, int, dict)

    # Состояние операций
    operation_started: pyqtSignal = pyqtSignal(str)
    operation_finished: pyqtSignal = pyqtSignal(str)
    loading_started: pyqtSignal = pyqtSignal()

    # Обновление UI
    update_ui: pyqtSignal = pyqtSignal(int)

    # Информация о ссылках
    link_info_finished: pyqtSignal = pyqtSignal(dict)

    # Ошибки
    error: pyqtSignal = pyqtSignal(str, str)
    simple_error: pyqtSignal = pyqtSignal(str)


class AsyncOperations:
    """Класс для управления асинхронными операциями структуры."""

    def __init__(
        self,
        db: Database,
        logger: Optional[logging.Logger] = None,
        top_panels_controller: Optional[Any] = None,
    ):
        self.db = db
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)
        # Единый глобальный планировщик задач вместо QThreadPool.globalInstance()
        self._scheduler = get_task_scheduler()
        self._worker_signals = StructureSignals()
        self._pending_tasks = {}
        # Прямая зависимость от TopPanelsController для обновления верхних панелей
        self.top_panels = top_panels_controller
        # Активные спаны метрик асинхронных операций (для защиты от дублей)
        self._active_metric_spans = set()

    def get_worker_signals(self) -> StructureSignals:
        """Возвращает объект сигналов воркеров для подключения."""
        return self._worker_signals

    def connect_signal_handlers(self, handlers: "AsyncSignalHandlers") -> None:
        """Подключает сигналы воркеров к обработчикам.

        Гарантирует согласованность подписок между `StructureWorkerSignals` и
        методами `AsyncSignalHandlers`.
        """
        # Инъекция TopPanelsController в обработчики (избегаем getattr в рантайме)
        try:
            handlers.top_panels = getattr(self, "top_panels", None)
        except Exception:
            # Не должен падать, просто оставим None
            handlers.top_panels = None

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
            except TypeError:
                # Обычно означает, что слот не был подключен
                self.logger.debug(
                    "disconnect_signal_handlers: handler не подключен к сигналу '%s'",
                    name,
                    exc_info=True,
                )
            except RuntimeError:
                # QObject удалён или недействителен
                self.logger.debug(
                    "disconnect_signal_handlers: недействительный объект для сигнала '%s'",
                    name,
                    exc_info=True,
                )
            except Exception as e:
                # Нежданные ошибки — предупредим, но продолжим отписку остальных
                self.logger.warning(
                    "disconnect_signal_handlers: сбой отписки от сигнала '%s': %s",
                    name,
                    e,
                    exc_info=True,
                )

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
        """Стартует метрику name и останавливает по первому срабатыванию stop_signal.

        Защищает от повторного старта: пока спан активен, повторные вызовы игнорируются.
        """
        try:
            if name in self._active_metric_spans:
                return
            metrics.start(name)
            self._active_metric_spans.add(name)

            def _on_stop(*_args):
                try:
                    metrics.stop(name)
                except Exception:
                    # Логируем только в debug, чтобы не засорять логи пользователя
                    self.logger.debug("Metrics: failed to stop span %s", name)
                try:
                    stop_signal.disconnect(_on_stop)
                except Exception:
                    pass
                self._active_metric_spans.discard(name)

            stop_signal.connect(_on_stop)
        except Exception:
            # Никогда не ломаем бизнес-логику из-за метрик
            self.logger.debug("Metrics: failed to start span %s", name)

    def load_spheres_async(self) -> None:
        """Асинхронная загрузка всех сфер через run_db."""
        # Метрика асинхронной загрузки сфер: старт здесь, стоп по сигналу spheres_loaded
        self._start_async_metric(
            "async:spheres_load", self._worker_signals.spheres_loaded
        )
        self._worker_signals.operation_started.emit("Загрузка сфер...")

        def _fetch():
            return self.db.spheres.get_spheres() or []

        run_db(
            _fetch,
            description="load_spheres",
            on_finished=lambda spheres: (
                self._worker_signals.spheres_loaded.emit(spheres),
                self._worker_signals.operation_finished.emit("Сферы загружены"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка загрузки", f"Ошибка загрузки сфер: {e}"
            ),
        )

    def load_structure_async(self, current_sphere_id: int) -> None:
        """Асинхронная загрузка структуры для сферы через run_db."""
        if not isinstance(current_sphere_id, int) or current_sphere_id <= 0:
            self.logger.error("Некорректный ID сферы: %s", current_sphere_id)
            return

        desc = f"Загрузка структуры для сферы {current_sphere_id}..."
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
            self._worker_signals.operation_finished.emit("Структура загружена")

        run_db(
            _fetch,
            description=f"load_structure(sphere_id={current_sphere_id})",
            on_finished=_on_finished,
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка загрузки", f"Ошибка загрузки структуры: {e}"
            ),
        )

    def load_sections_async(self, sphere_id: int) -> None:
        """Асинхронная загрузка разделов для сферы через run_db."""
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.error("Некорректный ID сферы: %s", sphere_id)
            return

        self._worker_signals.operation_started.emit(
            f"Загрузка разделов для сферы {sphere_id}..."
        )

        run_db(
            lambda: self.db.sections.get_sections(sphere_id) or [],
            description=f"load_sections(sphere_id={sphere_id})",
            on_finished=lambda sections: (
                self._worker_signals.sections_loaded.emit(sections, sphere_id),
                self._worker_signals.operation_finished.emit("Разделы загружены"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка загрузки", f"Ошибка загрузки разделов: {e}"
            ),
        )

    def load_categories_async(self, section_id: int) -> None:
        """Асинхронная загрузка категорий для раздела через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Некорректный ID раздела: %s", section_id)
            return

        self._worker_signals.operation_started.emit(
            f"Загрузка категорий для раздела {section_id}..."
        )

        run_db(
            lambda: self.db.categories.get_categories(section_id) or [],
            description=f"load_categories(section_id={section_id})",
            on_finished=lambda categories: (
                self._worker_signals.categories_loaded.emit(categories, section_id),
                self._worker_signals.operation_finished.emit("Категории загружены"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка загрузки", f"Ошибка загрузки категорий: {e}"
            ),
        )

    def create_section_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание раздела через run_db."""
        if not isinstance(data, dict):
            self.logger.error("Данные раздела должны быть словарём")
            return
        name = (data.get("name") or "").strip()
        sphere_id = data.get("sphere_id")
        if not name:
            self.logger.error("Имя раздела обязательно для создания")
            return
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.error(
                "ID сферы обязателен и должен быть > 0 для создания раздела"
            )
            return
        # Предчек дубликатов для улучшения UX: избегаем падения на ограничении уникальности
        try:
            existing = self.db.sections.get_sections(sphere_id) or []
            if any(
                str(row["name"]).strip().lower() == name.lower() for row in existing
            ):
                msg = f"Раздел с именем '{name}' уже существует в выбранной сфере"
                self.logger.info(msg)
                # Покажем пользователю понятное сообщение без запуска воркера
                self._worker_signals.simple_error.emit(msg)
                return
        except Exception as e:
            # Не блокируем создание при сбое проверки, только логируем
            self.logger.warning(
                "Не удалось выполнить предчек дубликатов раздела: %s", e
            )

        def _create():
            service = StructureService(self.db)
            item_id = service.create_section(dict(data))
            parent_id = sphere_id
            payload = dict(data)
            payload["id"] = item_id
            return ("section", parent_id, payload)

        self._worker_signals.operation_started.emit(
            f"Создание section: {name or 'Без названия'}..."
        )

        run_db(
            _create,
            description=f"create_section(name={name!r})",
            on_finished=lambda res: (
                self._worker_signals.item_created.emit(*res),
                self._worker_signals.operation_finished.emit("Section создан"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка создания", f"Ошибка создания section: {e}"
            ),
        )

    def create_category_async(self, data: Dict[str, Any]) -> None:
        """Асинхронное создание категории через run_db."""
        if not isinstance(data, dict):
            self.logger.error("Данные категории должны быть словарём")
            return
        name = (data.get("name") or "").strip()
        section_id = data.get("section_id")
        if not name:
            self.logger.error("Имя категории обязательно для создания")
            return
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(
                "ID раздела обязателен и должен быть > 0 для создания категории"
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
            f"Создание category: {name or 'Без названия'}..."
        )

        run_db(
            _create,
            description=f"create_category(name={name!r})",
            on_finished=lambda res: (
                self._worker_signals.item_created.emit(*res),
                self._worker_signals.operation_finished.emit("Category создана"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка создания", f"Ошибка создания category: {e}"
            ),
        )

    def update_section_async(self, section_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление раздела через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Некорректный ID раздела: %s", section_id)
            return
        if not isinstance(data, dict):
            self.logger.error("Данные раздела должны быть словарём")
            return
        name = data.get("name")
        if name is not None and not str(name).strip():
            self.logger.error("Имя раздела должно быть непустой строкой")
            return
        self._worker_signals.operation_started.emit(
            f"Обновление section: {data.get('name', f'ID {section_id}')}..."
        )

        def _update():
            StructureService(self.db).update_section(section_id, dict(data))
            return ("section", section_id, dict(data))

        run_db(
            _update,
            description=f"update_section(id={section_id})",
            on_finished=lambda res: (
                self._worker_signals.item_updated.emit(*res),
                self._worker_signals.operation_finished.emit("Section обновлён"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка обновления", f"Ошибка обновления section: {e}"
            ),
        )

    def update_category_async(self, category_id: int, data: Dict[str, Any]) -> None:
        """Асинхронное обновление категории через run_db."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.error("Некорректный ID категории: %s", category_id)
            return
        if not isinstance(data, dict):
            self.logger.error("Данные категории должны быть словарём")
            return
        name = data.get("name")
        if name is not None and not str(name).strip():
            self.logger.error("Имя категории должно быть непустой строкой")
            return
        self._worker_signals.operation_started.emit(
            f"Обновление category: {data.get('name', f'ID {category_id}')}..."
        )

        def _update():
            StructureService(self.db).update_category(category_id, dict(data))
            return ("category", category_id, dict(data))

        run_db(
            _update,
            description=f"update_category(id={category_id})",
            on_finished=lambda res: (
                self._worker_signals.item_updated.emit(*res),
                self._worker_signals.operation_finished.emit("Category обновлена"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка обновления", f"Ошибка обновления category: {e}"
            ),
        )

    def delete_section_async(self, section_id: int) -> None:
        """Асинхронное удаление раздела через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Некорректный ID раздела: %s", section_id)
            return
        self._worker_signals.operation_started.emit(
            f"Удаление section ID {section_id}..."
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
                self._worker_signals.operation_finished.emit("Section удалён"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка удаления", f"Ошибка удаления section: {e}"
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
                error_msg = f"Invalid category ID: {category_id}"
                self.logger.error(error_msg)
                self._worker_signals.error.emit("Ошибка удаления", error_msg)
                return None

            self.logger.info("Starting async deletion of category %s", category_id)
            self._worker_signals.operation_started.emit(
                f"delete_category_{category_id}"
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
            self._pending_tasks[task_id] = True

            run_db(
                _delete,
                description=f"delete_category(id={category_id})",
                on_finished=lambda res: (
                    self._worker_signals.item_deleted.emit(*res),
                    self._worker_signals.operation_finished.emit("Category удалена"),
                ),
                on_error=lambda e: self._worker_signals.error.emit(
                    "Ошибка удаления", f"Failed to delete category: {e}"
                ),
            )

            return task_id

        except Exception as e:
            error_msg = f"Failed to start deletion task: {str(e)}"
            self.logger.error("%s", error_msg, exc_info=True)
            self._worker_signals.error.emit("Ошибка удаления", error_msg)
            return None

    def count_nested_objects_async(self, section_id: int) -> None:
        """Асинхронный подсчет вложенных объектов (категорий и ссылок) через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error("Некорректный ID раздела: %s", section_id)
            return

        self._worker_signals.operation_started.emit(
            f"Подсчет объектов в разделе {section_id}..."
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
                self._worker_signals.operation_finished.emit("Подсчёт завершен"),
            ),
            on_error=lambda e: self._worker_signals.error.emit(
                "Ошибка подсчета", f"Ошибка подсчета объектов: {e}"
            ),
        )


class AsyncSignalHandlers:
    """Класс для обработки сигналов от асинхронных операций."""

    def __init__(self, controller_instance):
        self.controller = controller_instance
        self.logger = controller_instance.logger
        # Инжектится извне через AsyncOperations.connect_signal_handlers
        self.top_panels: Optional[Any] = None

    def on_spheres_loaded(self, spheres: List[Dict[str, Any]]) -> None:
        """Обработчик завершения загрузки сфер."""
        try:
            self.logger.info("Загружено %s сфер", len(spheres))
            if hasattr(self.controller, "spheres_loaded"):
                self.controller.spheres_loaded.emit(spheres)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_spheres_loaded: %s", e, exc_info=True
            )

    def on_structure_loaded(
        self, structure: List[Dict[str, Any]], sphere_id: int
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
                        setattr(self.controller, "_last_switch_started_ms", None)
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
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_structure_loaded: %s", e, exc_info=True
            )

    def on_sections_loaded(
        self, sections: List[Dict[str, Any]], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки разделов."""
        try:
            self.logger.info(
                "Загружено %s разделов для сферы %s", len(sections), sphere_id
            )
            if hasattr(self.controller, "sections_loaded"):
                self.controller.sections_loaded.emit(sections, sphere_id)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_sections_loaded: %s", e, exc_info=True
            )

    def on_categories_loaded(
        self, categories: List[Dict[str, Any]], section_id: int
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
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_categories_loaded: %s", e, exc_info=True
            )

    # ===== CRUD =====
    def on_item_created(
        self, item_type: str, parent_id: int, item_data: Dict[str, Any]
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

    def on_item_updated(
        self, item_type: str, item_id: int, item_data: Dict[str, Any]
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

    def on_item_deleted(
        self, item_type: str, item_id: int, old_data: Dict[str, Any]
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

    def on_error(self, title: str, message: str) -> None:
        try:
            self.logger.error("%s: %s", title, message)
            # Новый сигнал контроллера
            if hasattr(self.controller, "error_occurred"):
                self.controller.error_occurred.emit(title, message)
            # Совместимость со старым именем
            elif hasattr(self.controller, "error"):
                self.controller.error.emit(title, message)
        except Exception as e:
            self.logger.error("Ошибка в обработчике on_error: %s", e, exc_info=True)

    def on_simple_error(self, message: str) -> None:
        try:
            self.logger.error(message)
            if hasattr(self.controller, "simple_error"):
                self.controller.simple_error.emit(message)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_simple_error: %s", e, exc_info=True
            )

    def on_operation_started(self, description: str) -> None:
        try:
            # Сообщения о структуре чрезмерно частые — логируем их на DEBUG
            if "структур" in description.lower():
                self.logger.debug(description)
            else:
                self.logger.info(description)
            if hasattr(self.controller, "operation_started"):
                self.controller.operation_started.emit(description)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_operation_started: %s", e, exc_info=True
            )

    def on_operation_finished(self, description: str) -> None:
        try:
            # Сообщения о структуре чрезмерно частые — логируем их на DEBUG
            if "структур" in description.lower():
                self.logger.debug(description)
            else:
                self.logger.info(description)
            if hasattr(self.controller, "operation_finished"):
                self.controller.operation_finished.emit(description)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_operation_finished: %s", e, exc_info=True
            )

    def on_loading_started(self) -> None:
        try:
            self.logger.debug("Начата загрузка...")
            if hasattr(self.controller, "loading_started"):
                self.controller.loading_started.emit()
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_loading_started: %s", e, exc_info=True
            )

    # ===== Обновление UI =====
    def on_update_ui(self, category_id: int) -> None:
        try:
            self.logger.debug("Обновление UI для категории %s", category_id)
            if hasattr(self.controller, "update_ui"):
                self.controller.update_ui.emit(category_id)
        except Exception as e:
            self.logger.error("Ошибка в обработчике on_update_ui: %s", e, exc_info=True)

    def on_update_favorites(self) -> None:
        try:
            self.logger.debug("Обновление избранного (через TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels не инжектирован; пропускаем обновление избранного"
                )
                return
            self.top_panels.request_favorites_refresh()
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_update_favorites: %s", e, exc_info=True
            )

    def on_update_recent_links(self) -> None:
        try:
            self.logger.debug("Обновление недавних ссылок (через TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels не инжектирован; пропускаем обновление недавних ссылок"
                )
                return
            self.top_panels.request_recents_refresh()
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_update_recent_links: %s", e, exc_info=True
            )

    # ===== Поиск / Ссылки / Подсчёт =====
    def on_search_results(self, results: List[Dict[str, Any]]) -> None:
        try:
            self.logger.info("Результаты поиска: %s", len(results))
            if hasattr(self.controller, "search_results"):
                self.controller.search_results.emit(results)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_search_results: %s", e, exc_info=True
            )

    def on_links_loaded(
        self, links: List[Dict[str, Any]], category_id: int, task_id: int
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
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_links_loaded: %s", e, exc_info=True
            )

    def on_link_info_finished(self, info: Dict[str, Any]) -> None:
        try:
            self.logger.debug("Получена информация о ссылке")
            if hasattr(self.controller, "link_info_finished"):
                self.controller.link_info_finished.emit(info)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_link_info_finished: %s", e, exc_info=True
            )

    def on_count_finished(
        self, fav_count: int, links: List[Dict[str, Any]], link: object
    ) -> None:
        try:
            self.logger.info("Подсчёт избранных завершён: %s", fav_count)
            if hasattr(self.controller, "count_finished"):
                self.controller.count_finished.emit(fav_count, links, link)
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_count_finished: %s", e, exc_info=True
            )
