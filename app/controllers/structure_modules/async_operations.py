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
    update_favorites: pyqtSignal = pyqtSignal()
    update_recent_links: pyqtSignal = pyqtSignal()

    # Информация о ссылках
    link_info_finished: pyqtSignal = pyqtSignal(dict)

    # Ошибки
    error: pyqtSignal = pyqtSignal(str, str)
    simple_error: pyqtSignal = pyqtSignal(str)


class AsyncOperations:
    """Класс для управления асинхронными операциями структуры."""

    def __init__(self, db: Database, logger: Optional[logging.Logger] = None):
        self.db = db
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)
        # Единый глобальный планировщик задач вместо QThreadPool.globalInstance()
        self._scheduler = get_task_scheduler()
        self._worker_signals = StructureSignals()
        self._pending_tasks = {}

    def get_worker_signals(self) -> StructureSignals:
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
        self._worker_signals.update_recent_links.connect(
            handlers.on_update_recent_links
        )
        # Ошибки
        self._worker_signals.error.connect(handlers.on_error)
        self._worker_signals.simple_error.connect(handlers.on_simple_error)

    def disconnect_signal_handlers(self, handlers: "AsyncSignalHandlers") -> None:
        """Отписывает обработчики от сигналов воркеров.

        Безопасно игнорирует уже отсоединённые связи.
        """
        try:
            self._worker_signals.spheres_loaded.disconnect(handlers.on_spheres_loaded)
            self._worker_signals.structure_loaded.disconnect(
                handlers.on_structure_loaded
            )
            self._worker_signals.sections_loaded.disconnect(handlers.on_sections_loaded)
            self._worker_signals.categories_loaded.disconnect(
                handlers.on_categories_loaded
            )
            self._worker_signals.search_results.disconnect(handlers.on_search_results)
            self._worker_signals.links_loaded.disconnect(handlers.on_links_loaded)
            self._worker_signals.link_info_finished.disconnect(
                handlers.on_link_info_finished
            )
            self._worker_signals.count_finished.disconnect(handlers.on_count_finished)
            self._worker_signals.item_created.disconnect(handlers.on_item_created)
            self._worker_signals.item_updated.disconnect(handlers.on_item_updated)
            self._worker_signals.item_deleted.disconnect(handlers.on_item_deleted)
            self._worker_signals.operation_started.disconnect(
                handlers.on_operation_started
            )
            self._worker_signals.operation_finished.disconnect(
                handlers.on_operation_finished
            )
            self._worker_signals.loading_started.disconnect(handlers.on_loading_started)
            self._worker_signals.update_ui.disconnect(handlers.on_update_ui)
            self._worker_signals.update_favorites.disconnect(
                handlers.on_update_favorites
            )
            self._worker_signals.update_recent_links.disconnect(
                handlers.on_update_recent_links
            )
            self._worker_signals.error.disconnect(handlers.on_error)
            self._worker_signals.simple_error.disconnect(handlers.on_simple_error)
        except Exception:
            # Тихое игнорирование частичных отписок
            pass

    def load_spheres_async(self) -> None:
        """Асинхронная загрузка всех сфер через run_db."""
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
            self.logger.error(f"Некорректный ID сферы: {current_sphere_id}")
            return

        desc = f"Загрузка структуры для сферы {current_sphere_id}..."
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
            self.logger.error(f"Некорректный ID сферы: {sphere_id}")
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
            self.logger.error(f"Некорректный ID раздела: {section_id}")
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
            self.logger.warning(f"Не удалось выполнить предчек дубликатов раздела: {e}")
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
            self.logger.error(f"Некорректный ID раздела: {section_id}")
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
            self.logger.error(f"Некорректный ID категории: {category_id}")
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
            self.logger.error(f"Некорректный ID раздела: {section_id}")
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

            self.logger.info(f"Starting async deletion of category {category_id}")
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
            self.logger.error(error_msg, exc_info=True)
            self._worker_signals.error.emit("Ошибка удаления", error_msg)
            return None

    def count_nested_objects_async(self, section_id: int) -> None:
        """Асинхронный подсчет вложенных объектов (категорий и ссылок) через run_db."""
        if not isinstance(section_id, int) or section_id <= 0:
            self.logger.error(f"Некорректный ID раздела: {section_id}")
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

    def on_spheres_loaded(self, spheres: List[Dict[str, Any]]) -> None:
        """Обработчик завершения загрузки сфер."""
        try:
            self.logger.info(f"Загружено {len(spheres)} сфер")
            if hasattr(self.controller, "spheres_loaded"):
                self.controller.spheres_loaded.emit(spheres)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_spheres_loaded: {e}", exc_info=True
            )

    def on_structure_loaded(
        self, structure: List[Dict[str, Any]], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки структуры."""
        try:
            self.logger.debug(
                f"Загружена структура для сферы {sphere_id}: {len(structure)} разделов"
            )
            if hasattr(self.controller, "structure_loaded"):
                self.controller.structure_loaded.emit(structure)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_structure_loaded: {e}", exc_info=True
            )

    def on_sections_loaded(
        self, sections: List[Dict[str, Any]], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки разделов."""
        try:
            self.logger.info(
                f"Загружено {len(sections)} разделов для сферы {sphere_id}"
            )
            if hasattr(self.controller, "sections_loaded"):
                self.controller.sections_loaded.emit(sections, sphere_id)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_sections_loaded: {e}", exc_info=True
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
                f"Загружено {len(categories)} категорий для раздела {section_id}"
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
                f"Ошибка в обработчике on_categories_loaded: {e}", exc_info=True
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
            self.logger.info(f"Создан {item_type} (parent_id={parent_id}): {name}")
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
                    f"Не удалось инициировать обновление UI после создания {item_type}: {e2}"
                )
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_item_created: {e}", exc_info=True
            )

    def on_item_updated(
        self, item_type: str, item_id: int, item_data: Dict[str, Any]
    ) -> None:
        """Обновлён элемент структуры."""
        try:
            self.logger.info(f"Обновлён {item_type} id={item_id}")
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
                    f"Не удалось инициировать обновление UI после обновления {item_type}: {e2}"
                )
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_item_updated: {e}", exc_info=True
            )

    def on_item_deleted(
        self, item_type: str, item_id: int, old_data: Dict[str, Any]
    ) -> None:
        """Удалён элемент структуры.

        Примечание: контроллер ожидает сигнатуру (str, int), поэтому `old_data`
        используется только для логирования и не передается далее.
        """
        try:
            self.logger.info(f"Удалён {item_type} id={item_id}")
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
                    f"Не удалось инициировать обновление UI после удаления {item_type}: {e2}"
                )
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_item_deleted: {e}", exc_info=True
            )

    def on_error(self, title: str, message: str) -> None:
        try:
            self.logger.error(f"{title}: {message}")
            # Новый сигнал контроллера
            if hasattr(self.controller, "error_occurred"):
                self.controller.error_occurred.emit(title, message)
            # Совместимость со старым именем
            elif hasattr(self.controller, "error"):
                self.controller.error.emit(title, message)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_error: {e}", exc_info=True)

    def on_simple_error(self, message: str) -> None:
        try:
            self.logger.error(message)
            if hasattr(self.controller, "simple_error"):
                self.controller.simple_error.emit(message)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_simple_error: {e}", exc_info=True
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
                f"Ошибка в обработчике on_operation_started: {e}", exc_info=True
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
                f"Ошибка в обработчике on_operation_finished: {e}", exc_info=True
            )

    def on_loading_started(self) -> None:
        try:
            self.logger.debug("Начата загрузка...")
            if hasattr(self.controller, "loading_started"):
                self.controller.loading_started.emit()
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_loading_started: {e}", exc_info=True
            )

    # ===== Обновление UI =====
    def on_update_ui(self, category_id: int) -> None:
        try:
            self.logger.debug(f"Обновление UI для категории {category_id}")
            if hasattr(self.controller, "update_ui"):
                self.controller.update_ui.emit(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка в обработчике on_update_ui: {e}", exc_info=True)

    def on_update_favorites(self) -> None:
        try:
            self.logger.debug("Обновление избранного (через TopPanelsController, если доступен)")
            # Предпочитаем централизованный контроллер верхних панелей
            try:
                top_ctrl = getattr(self.controller, "top_panels_controller", None)
                if top_ctrl and hasattr(top_ctrl, "request_favorites_refresh"):
                    top_ctrl.request_favorites_refresh()
                    return
            except Exception as inner_exc:
                self.logger.warning(
                    f"TopPanelsController недоступен для обновления избранного: {inner_exc}"
                )
            # Совместимость: если у контроллера всё же есть старый сигнал, эмитим его
            if hasattr(self.controller, "update_favorites"):
                try:
                    self.controller.update_favorites.emit()
                except Exception:
                    # Не валим поток, логгируем и продолжаем
                    self.logger.debug("Legacy update_favorites.emit() недоступен")
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_update_favorites: {e}", exc_info=True
            )

    def on_update_recent_links(self) -> None:
        try:
            self.logger.debug("Обновление недавних ссылок (через TopPanelsController, если доступен)")
            # Предпочитаем централизованный контроллер верхних панелей
            try:
                top_ctrl = getattr(self.controller, "top_panels_controller", None)
                if top_ctrl and hasattr(top_ctrl, "request_recents_refresh"):
                    top_ctrl.request_recents_refresh()
                    return
            except Exception as inner_exc:
                self.logger.warning(
                    f"TopPanelsController недоступен для обновления недавних ссылок: {inner_exc}"
                )
            # Совместимость: если у контроллера всё же есть старый сигнал, эмитим его
            if hasattr(self.controller, "update_recent_links"):
                try:
                    self.controller.update_recent_links.emit()
                except Exception:
                    self.logger.debug("Legacy update_recent_links.emit() недоступен")
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_update_recent_links: {e}", exc_info=True
            )

    # ===== Поиск / Ссылки / Подсчёт =====
    def on_search_results(self, results: List[Dict[str, Any]]) -> None:
        try:
            self.logger.info(f"Результаты поиска: {len(results)}")
            if hasattr(self.controller, "search_results"):
                self.controller.search_results.emit(results)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_search_results: {e}", exc_info=True
            )

    def on_links_loaded(
        self, links: List[Dict[str, Any]], category_id: int, task_id: int
    ) -> None:
        try:
            self.logger.info(
                f"Загружено ссылок: {len(links)} (category_id={category_id}, task_id={task_id})"
            )
            if hasattr(self.controller, "links_loaded"):
                self.controller.links_loaded.emit(links, category_id, task_id)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_links_loaded: {e}", exc_info=True
            )

    def on_link_info_finished(self, info: Dict[str, Any]) -> None:
        try:
            self.logger.debug("Получена информация о ссылке")
            if hasattr(self.controller, "link_info_finished"):
                self.controller.link_info_finished.emit(info)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_link_info_finished: {e}", exc_info=True
            )

    def on_count_finished(
        self, fav_count: int, links: List[Dict[str, Any]], link: object
    ) -> None:
        try:
            self.logger.info(f"Подсчёт избранных завершён: {fav_count}")
            if hasattr(self.controller, "count_finished"):
                self.controller.count_finished.emit(fav_count, links, link)
        except Exception as e:
            self.logger.error(
                f"Ошибка в обработчике on_count_finished: {e}", exc_info=True
            )
