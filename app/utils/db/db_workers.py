"""
Унифицированные асинхронные воркеры для операций с базой данных.

ВНИМАНИЕ: модуль устаревает. Используйте современный фасад
`app.utils.db.api.run_db`. Этот модуль остаётся как совместимый shim.
"""

import logging
import os
import warnings
from datetime import datetime
from typing import Any, Dict

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from app.services import LinksService, StructureService

# Современные реализации и фасад
from app.utils.db.api import run_db as run_db  # re-export
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.executors.pool import get_thread_pool
from app.utils.db.tasks.base import DatabaseTask as _NewDatabaseTask
from app.utils.db.tasks.base import TaskSignals as _NewTaskSignals

logger = logging.getLogger(__name__)

# Строгий режим для utils-db: отключает легаси-слой
_STRICT_DB = os.getenv("OSTEEN_STRICT_DB_UTILS", "0") == "1"
_WARNED = False

if _STRICT_DB:  # pragma: no cover
    raise ImportError(
        "Legacy module 'app.utils.db.db_workers' is disabled in strict mode. "
        "Use 'app.utils.db.api.run_db' and new modular API instead."
    )


def _warn_once():  # pragma: no cover
    global _WARNED
    if not _WARNED:
        warnings.warn(
            "Module 'app.utils.db.db_workers' is deprecated. Use 'app.utils.db.api.run_db' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        _WARNED = True


# Глобальный пул потоков для всех задач
_db_pool = QThreadPool.globalInstance()


class TaskSignals(_NewTaskSignals):  # type: ignore[misc]
    """Совместимый алиас для сигналов задач (устаревший).

    Используйте TaskSignals из app.utils.db.tasks.base.
    """

    pass


class DatabaseTask(_NewDatabaseTask):  # type: ignore[misc]
    """Совместимый воркер (устаревший), обёртка над новой реализацией.

    Принимает func и произвольные args/kwargs, как раньше.
    """

    def __init__(self, func, *args, **kwargs):
        _warn_once()
        # Заворачиваем в нулераргументный callable, как ожидает новая реализация
        super().__init__(
            lambda: func(*args, **kwargs), description=getattr(func, "__name__", None)
        )


class AsyncTaskMixin:
    """Помощник для запуска функции в пуле потоков."""

    def run_async(self, func, on_success=None, on_error=None, *args, **kwargs):
        _warn_once()
        task = DatabaseTask(func, *args, **kwargs)
        if on_success:
            task.signals.finished.connect(on_success)
        if on_error:
            task.signals.error.connect(on_error)
        else:
            task.signals.error.connect(
                lambda e: logger.error("Unhandled async error: %s", e, exc_info=True)
            )
        # Используем общий API для пула (подменяемый в тестах)
        get_thread_pool().start(task)
        return task


class StructureWorkerSignals(QObject):
    """Сигналы для асинхронных операций со структурой."""

    # Загрузка данных
    spheres_loaded: pyqtSignal = pyqtSignal(list)  # List[Dict] - список сфер
    structure_loaded: pyqtSignal = pyqtSignal(
        list, int
    )  # List[Dict], int - структура, ID сферы
    sections_loaded: pyqtSignal = pyqtSignal(
        list, int
    )  # List[Dict], int - разделы, ID сферы
    categories_loaded: pyqtSignal = pyqtSignal(
        list, int
    )  # List[Dict], int - категории, ID раздела
    links_loaded: pyqtSignal = pyqtSignal(
        list, int, int
    )  # List[Dict], int, int - ссылки, ID категории, ID задачи

    # Поиск
    search_results: pyqtSignal = pyqtSignal(list)  # List[Dict] - результаты поиска

    # Подсчет
    count_finished: pyqtSignal = pyqtSignal(
        int, list, object
    )  # int, List[Dict], Optional[Dict] - количество избранных

    # Операции CRUD
    item_created: pyqtSignal = pyqtSignal(
        str, int, dict
    )  # str, int, Dict - тип, ID родителя, данные
    item_updated: pyqtSignal = pyqtSignal(
        str, int, dict
    )  # str, int, Dict - тип, ID элемента, данные
    item_deleted: pyqtSignal = pyqtSignal(
        str, int, dict
    )  # str, int, Dict - тип, ID элемента, старые данные

    # Состояние операций
    operation_started: pyqtSignal = pyqtSignal(str)  # str - описание операции
    operation_finished: pyqtSignal = pyqtSignal(str)  # str - описание операции
    loading_started: pyqtSignal = pyqtSignal()  # начало загрузки

    # Обновление UI
    update_ui: pyqtSignal = pyqtSignal(int)  # int - ID категории для обновления
    update_favorites: pyqtSignal = pyqtSignal()  # обновление избранного
    update_recent_links: pyqtSignal = pyqtSignal()  # обновление недавних ссылок

    # Информация о ссылках
    link_info_finished: pyqtSignal = pyqtSignal(dict)  # Dict - информация о ссылке

    # Ошибки
    error: pyqtSignal = pyqtSignal(str, str)  # str, str - заголовок, сообщение
    simple_error: pyqtSignal = pyqtSignal(str)  # str - сообщение об ошибке


class BaseDbWorker(QRunnable):
    """Базовый воркер с общей инициализацией db/signals и автоудалением.

    Используется для устранения дублирования кода конструктора в воркерах.
    """

    def __init__(self, db, signals: StructureWorkerSignals):
        super().__init__()
        self.db = db
        self.signals = signals
        self.setAutoDelete(True)


class SectionIdWorker(BaseDbWorker):
    """Базовый воркер для задач, которым нужен section_id."""

    def __init__(self, db, section_id: int, signals: StructureWorkerSignals):
        super().__init__(db, signals)
        self.section_id = section_id


class SphereIdWorker(BaseDbWorker):
    """Базовый воркер для задач, которым нужен sphere_id."""

    def __init__(self, db, sphere_id: int, signals: StructureWorkerSignals):
        super().__init__(db, signals)
        self.sphere_id = sphere_id


class UpdateLinkWorker(BaseDbWorker):
    """Асинхронное обновление ссылки в базе данных."""

    def __init__(self, db, link, category_id, signals: StructureWorkerSignals):
        super().__init__(db, signals)
        self.link = dict(link)
        self.category_id = category_id

    def run(self):
        """Обновляет ссылку в базе данных и отправляет сигналы для обновления UI."""
        try:
            self.signals.loading_started.emit()
            self.link["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Выполняем upsert через сервисный слой с транзакцией
            LinksService(self.db).create_or_update_link(self.link)
            self.signals.update_ui.emit(self.category_id)
            self.signals.update_favorites.emit()
            self.signals.update_recent_links.emit()
        except Exception as e:
            if not handle_db_error(e, self):
                logger.error(f"Error in UpdateLinkWorker: {e}", exc_info=True)
                self.signals.simple_error.emit(str(e))


class LoadLinksWorker(BaseDbWorker):
    """Асинхронная загрузка ссылок из базы данных."""

    def __init__(self, db, category_id, signals: StructureWorkerSignals, task_id: int):
        super().__init__(db, signals)
        self.category_id = category_id
        self.task_id = task_id
        self.cancelled = False

    def cancel(self):
        """Отменяет выполнение задачи."""
        self.cancelled = True

    def run(self):
        """Загружает ссылки из базы данных для указанной категории."""
        try:
            if self.cancelled:
                return
            self.signals.loading_started.emit()
            raw_rows = self.db.links.get_links(self.category_id)
            if self.cancelled:
                return
            links = raw_rows or []
            self.signals.links_loaded.emit(links, self.category_id, self.task_id)
        except Exception as e:
            if not handle_db_error(e, self):
                logger.error(f"Error in LoadLinksWorker: {e}", exc_info=True)
                self.signals.simple_error.emit(str(e))


class SearchLinksWorker(BaseDbWorker):
    """Асинхронный поиск ссылок в базе данных."""

    def __init__(self, db, query: str, signals: StructureWorkerSignals):
        super().__init__(db, signals)
        self.query = query

    def run(self):
        """Выполняет поиск ссылок в базе данных по запросу."""
        try:
            self.signals.loading_started.emit()
            rows = self.db.links.search_links(self.query)
            results = rows or []
            self.signals.search_results.emit(results)
        except Exception as e:
            if not handle_db_error(e, self):
                logger.error(f"Error in SearchLinksWorker: {e}", exc_info=True)
                self.signals.simple_error.emit(str(e))


class CountFavoritesWorker(BaseDbWorker):
    """Асинхронный подсчет избранных ссылок."""

    def __init__(self, db, links: list, link: dict, signals: StructureWorkerSignals):
        super().__init__(db, signals)
        self.links = links
        self.link = link

    def run(self):
        """Подсчитывает количество избранных ссылок."""
        try:
            self.signals.loading_started.emit()
            fav_count = self.db.links.count_favorites()
            self.signals.count_finished.emit(fav_count, self.links, self.link)
        except Exception as e:
            if not handle_db_error(e, self):
                logger.error(f"Error in CountFavoritesWorker: {e}", exc_info=True)
                self.signals.simple_error.emit(str(e))


class LinkInfoWorker(QRunnable):
    """Асинхронный обработчик информации о ссылке."""

    def __init__(
        self,
        link_type: str,
        path: str,
        args: str,
        config_module,
        signals: StructureWorkerSignals,
    ):
        super().__init__()
        self.link_type = link_type
        self.path = path
        self.args = args
        self.config = config_module
        self.signals = signals
        self._is_cancelled = False
        self.setAutoDelete(True)

    def cancel(self):
        """Запрос на отмену выполнения задачи."""
        self._is_cancelled = True

    def run(self):
        """Обрабатывает информацию о ссылке."""
        try:
            if self._is_cancelled:
                return
            if self.link_type == "web":
                from app.utils.links.web_favicon import fetch_web_link_info

                # Простая прокидка флага принудительного обновления из args
                force = False
                try:
                    a = (self.args or "").lower()
                    if (
                        ("--force-refresh" in a)
                        or ("force_refresh=1" in a)
                        or ("force=true" in a)
                    ):
                        force = True
                except Exception:
                    force = False
                info = fetch_web_link_info(self.path, self.config, force_refresh=force)
            else:
                from app.utils.links.link_parser import parse_local_link

                info = parse_local_link(
                    self.link_type, self.path, self.config, self.args
                )
            if not self._is_cancelled:
                self.signals.link_info_finished.emit(info)
        except Exception as e:
            if not self._is_cancelled:
                error_msg = f"Error processing {self.link_type} link: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self.signals.simple_error.emit(error_msg)


class LoadSpheresWorker(BaseDbWorker):
    """Асинхронная загрузка всех сфер."""

    def __init__(self, db, signals: StructureWorkerSignals):
        super().__init__(db, signals)

    def run(self):
        """Загружает все сферы из базы данных."""
        try:
            self.signals.operation_started.emit("Загрузка сфер...")

            spheres = self.db.spheres.get_spheres() or []

            logger.debug(f"Загружено {len(spheres)} сфер")
            self.signals.spheres_loaded.emit(spheres)
            self.signals.operation_finished.emit("Сферы загружены")

        except Exception as e:
            error_msg = f"Ошибка загрузки сфер: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка загрузки", error_msg)


class LoadStructureWorker(SphereIdWorker):
    """Асинхронная загрузка полной структуры для сферы."""

    def run(self):
        """Загружает структуру (разделы + категории) для указанной сферы."""
        try:
            self.signals.operation_started.emit(
                f"Загрузка структуры для сферы {self.sphere_id}..."
            )

            # Загружаем разделы
            sections_raw = self.db.sections.get_sections(self.sphere_id)
            if not sections_raw:
                self.signals.structure_loaded.emit([], self.sphere_id)
                self.signals.operation_finished.emit("Структура загружена (пустая)")
                return

            sections_data = sections_raw
            section_ids = [section["id"] for section in sections_data]

            # Загружаем все категории для всех разделов одним оптимизированным запросом
            # Используем новый метод get_categories_for_sections для устранения N+1 проблемы
            categories_raw = self.db.categories.get_categories_for_sections(
                section_ids
            )
            all_categories = categories_raw or []

            # Группируем категории по разделам
            categories_by_section = {}
            for category in all_categories:
                section_id = category["section_id"]
                if section_id not in categories_by_section:
                    categories_by_section[section_id] = []
                categories_by_section[section_id].append(category)

            # Добавляем категории к разделам
            for section in sections_data:
                section["categories"] = categories_by_section.get(section["id"], [])

            logger.debug(
                f"Загружена структура для сферы {self.sphere_id}: {len(sections_data)} разделов"
            )
            self.signals.structure_loaded.emit(sections_data, self.sphere_id)
            self.signals.operation_finished.emit("Структура загружена")

        except Exception as e:
            error_msg = f"Ошибка загрузки структуры: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка загрузки", error_msg)


class LoadSectionsWorker(SphereIdWorker):
    """Асинхронная загрузка разделов для сферы."""

    def run(self):
        """Загружает разделы для указанной сферы."""
        try:
            self.signals.operation_started.emit(
                f"Загрузка разделов для сферы {self.sphere_id}..."
            )

            sections = self.db.sections.get_sections(self.sphere_id) or []

            logger.debug(
                f"Загружено {len(sections)} разделов для сферы {self.sphere_id}"
            )
            self.signals.sections_loaded.emit(sections, self.sphere_id)
            self.signals.operation_finished.emit("Разделы загружены")

        except Exception as e:
            error_msg = f"Ошибка загрузки разделов: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка загрузки", error_msg)


class LoadCategoriesWorker(SectionIdWorker):
    """Асинхронная загрузка категорий для раздела."""

    def run(self):
        """Загружает категории для указанного раздела."""
        try:
            self.signals.operation_started.emit(
                f"Загрузка категорий для раздела {self.section_id}..."
            )

            categories = self.db.categories.get_categories(self.section_id) or []

            logger.debug(
                f"Загружено {len(categories)} категорий для раздела {self.section_id}"
            )
            self.signals.categories_loaded.emit(categories, self.section_id)
            self.signals.operation_finished.emit("Категории загружены")

        except Exception as e:
            error_msg = f"Ошибка загрузки категорий: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка загрузки", error_msg)


class CreateItemWorker(BaseDbWorker):
    """Асинхронное создание элемента структуры."""

    def __init__(
        self, db, item_type: str, data: Dict[str, Any], signals: StructureWorkerSignals
    ):
        super().__init__(db, signals)
        self.item_type = item_type  # "section" или "category"
        self.data = dict(data)  # Копируем данные

    def run(self):
        """Создает новый элемент структуры."""
        try:
            item_name = self.data.get("name", "Без названия")
            self.signals.operation_started.emit(
                f"Создание {self.item_type}: {item_name}..."
            )

            service = StructureService(self.db)
            if self.item_type == "section":
                item_id = service.create_section(self.data)
                parent_id = self.data.get("sphere_id", 0)
            elif self.item_type == "category":
                item_id = service.create_category(self.data)
                parent_id = self.data.get("section_id", 0)
            else:
                raise ValueError(f"Неизвестный тип элемента: {self.item_type}")

            # Обновляем данные с полученным ID
            self.data["id"] = item_id

            logger.info(f"Создан {self.item_type} с ID {item_id}: {item_name}")
            self.signals.item_created.emit(self.item_type, parent_id, self.data)
            self.signals.operation_finished.emit(
                f"{self.item_type.capitalize()} создан"
            )

        except Exception as e:
            error_msg = f"Ошибка создания {self.item_type}: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка создания", error_msg)


class UpdateItemWorker(BaseDbWorker):
    """Асинхронное обновление элемента структуры."""

    def __init__(
        self,
        db,
        item_type: str,
        item_id: int,
        data: Dict[str, Any],
        signals: StructureWorkerSignals,
    ):
        super().__init__(db, signals)
        self.item_type = item_type  # "section" или "category"
        self.item_id = item_id
        self.data = dict(data)  # Копируем данные

    def run(self):
        """Обновляет существующий элемент структуры."""
        try:
            item_name = self.data.get("name", f"ID {self.item_id}")
            self.signals.operation_started.emit(
                f"Обновление {self.item_type}: {item_name}..."
            )

            service = StructureService(self.db)
            if self.item_type == "section":
                service.update_section(self.item_id, self.data)
            elif self.item_type == "category":
                service.update_category(self.item_id, self.data)
            else:
                raise ValueError(f"Неизвестный тип элемента: {self.item_type}")

            logger.info(f"Обновлен {self.item_type} с ID {self.item_id}: {item_name}")
            self.signals.item_updated.emit(self.item_type, self.item_id, self.data)
            self.signals.operation_finished.emit(
                f"{self.item_type.capitalize()} обновлен"
            )

        except Exception as e:
            error_msg = f"Ошибка обновления {self.item_type}: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка обновления", error_msg)


class DeleteItemWorker(BaseDbWorker):
    """Асинхронное удаление элемента структуры."""

    def __init__(
        self, db, item_type: str, item_id: int, signals: StructureWorkerSignals
    ):
        super().__init__(db, signals)
        self.item_type = item_type  # "section" или "category"
        self.item_id = item_id

    def run(self):
        """Удаляет элемент структуры."""
        try:
            self.signals.operation_started.emit(
                f"Удаление {self.item_type} ID {self.item_id}..."
            )

            # Сначала получаем данные элемента для передачи в сигнале
            old_data = {}

            service = StructureService(self.db)
            if self.item_type == "section":
                # Получаем данные раздела перед удалением (чтение напрямую допустимо)
                section_data = self.db.sections.get_section_by_id(self.item_id)
                if section_data:
                    old_data = dict(section_data)
                service.delete_section(self.item_id)
            elif self.item_type == "category":
                # Получаем данные категории перед удалением (чтение напрямую допустимо)
                category_data = self.db.categories.get_category_by_id(self.item_id)
                if category_data:
                    old_data = dict(category_data)
                service.delete_category(self.item_id)
            else:
                raise ValueError(f"Неизвестный тип элемента: {self.item_type}")

            logger.info(f"Удален {self.item_type} с ID {self.item_id}")
            self.signals.item_deleted.emit(self.item_type, self.item_id, old_data)
            self.signals.operation_finished.emit(
                f"{self.item_type.capitalize()} удален"
            )

        except Exception as e:
            error_msg = f"Ошибка удаления {self.item_type}: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка удаления", error_msg)


class CountNestedObjectsWorker(SectionIdWorker):
    """Асинхронный подсчет вложенных объектов (категорий и ссылок в разделе)."""

    def run(self):
        """Подсчитывает категории и ссылки в разделе."""
        try:
            self.signals.operation_started.emit(
                f"Подсчет объектов в разделе {self.section_id}..."
            )

            categories_data = self.db.categories.get_categories(self.section_id)
            categories_count = len(categories_data) if categories_data else 0

            links_count = 0
            if categories_data:
                for category_dict in categories_data:
                    links_data = self.db.links.get_links(category_dict["id"])
                    if links_data:
                        links_count += len(links_data)

            # Отправляем результат через специальный сигнал
            count_data = {
                "section_id": self.section_id,
                "categories_count": categories_count,
                "links_count": links_count,
            }

            logger.debug(
                f"Раздел {self.section_id}: {categories_count} категорий, {links_count} ссылок"
            )
            # Используем item_updated для передачи результатов подсчета
            self.signals.item_updated.emit("section_count", self.section_id, count_data)
            self.signals.operation_finished.emit("Подсчет завершен")

        except Exception as e:
            error_msg = f"Ошибка подсчета объектов: {e}"
            logger.error(error_msg, exc_info=True)
            if not handle_db_error(e, self):
                self.signals.error.emit("Ошибка подсчета", error_msg)
