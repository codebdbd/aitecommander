import logging
from typing import Optional, Dict, Protocol, runtime_checkable

from PyQt6.QtCore import QObject


logger = logging.getLogger(__name__)


@runtime_checkable
class LinksTableLike(Protocol):
    """Структурный протокол таблицы ссылок для ранней валидации зависимостей."""

    def update_link_by_id(self, link: Dict) -> None: ...

    def populate(self, links: list[Dict], mode: str = "default") -> None: ...


class LinksTableController(QObject):
    """Централизованный контроллер обновления таблицы ссылок.

    Задачи:
    - Безопасная перезагрузка данных по категории: reload(category_id)
    - Точечное обновление строки таблицы по link_dict: update_row(link_dict)
    - Централизованное логирование и защита от параллельных обновлений
    """

    def __init__(self, main_window, *, table, links_business, category_provider):
        """Инициализация контроллера с явными зависимостями.

        :param main_window: главное окно (родитель по QObject)
        :param table: виджет таблицы ссылок, должен иметь метод update_link_by_id(dict)
        :param links_business: бизнес-логика ссылок с методом load_links(category_id)
        """
        # В тестах main_window может быть SimpleNamespace — не передаём его как QObject-родителя
        try:
            from PyQt6.QtCore import QObject as _QtQObject  # локальный импорт для безопасности
            parent = main_window if isinstance(main_window, _QtQObject) else None
        except Exception:
            parent = None
        super().__init__(parent=parent)
        self.main = main_window
        self.table = table
        self.business = links_business
        self.category_provider = category_provider
        if self.table is None or self.business is None:
            raise ValueError("LinksTableController: table и links_business должны быть переданы явно")
        # Явная валидация провайдера категории
        if not hasattr(self.category_provider, "current_category_id"):
            raise ValueError(
                "LinksTableController: category_provider must expose 'current_category_id' attribute"
            )
        # Проверка интерфейса таблицы на старте, чтобы не игнорировать ошибки в рантайме
        if not isinstance(self.table, LinksTableLike):
            raise TypeError(
                "LinksTableController: 'table' must implement LinksTableLike (update_link_by_id, populate)"
            )
        self._reloading: bool = False
        self._queued_category_id: Optional[int] = None
        self._current_category_id: Optional[int] = None

    # --- Public API ---
    def reload(self, category_id: Optional[int]) -> None:
        """Перезагрузить таблицу ссылок для указанной категории.

        - Делегируем загрузку бизнес-логике (links_ui.business или main.links_business)
        - Защита от параллельных перезагрузок: очередь из одного значения
        """
        try:
            if not isinstance(category_id, int) or category_id <= 0:
                logger.debug("LinksTableController.reload: invalid category_id=%s", category_id)
                return

            if self._reloading:
                # Если уже выполняется reload, поставим в очередь, но избегаем дубликатов
                if category_id == self._current_category_id or category_id == self._queued_category_id:
                    logger.debug(
                        "LinksTableController.reload: already processing or queued category_id=%s",
                        category_id,
                    )
                    return
                self._queued_category_id = category_id
                logger.debug(
                    "LinksTableController.reload: busy, queued category_id=%s", category_id
                )
                return

            self._reloading = True
            logger.debug("LinksTableController.reload: start (category_id=%s)", category_id)
            self._current_category_id = category_id

            # Централизовано: загружаем данные через бизнес-логику; UI подписан на изменения
            # Исключения ловим здесь, чтобы вести единообразное логирование и не падать UI
            self.business.load_links(category_id)
        except Exception as e:
            logger.error("LinksTableController.reload: unexpected error: %s", e, exc_info=True)
        finally:
            self._reloading = False
            # Если за время выполнения прилетела ещё одна категория — перезапустим для последней
            if (
                isinstance(self._queued_category_id, int)
                and self._queued_category_id > 0
                and self._queued_category_id != self._current_category_id
            ):
                queued = self._queued_category_id
                self._queued_category_id = None
                logger.debug(
                    "LinksTableController.reload: processing queued category_id=%s", queued
                )
                # Вызовем повторно синхронно; защита _reloading уже снята
                try:
                    self.reload(queued)
                except Exception:
                    logger.exception("LinksTableController.reload: queued call failed")

    def update_row(self, link_dict: Optional[Dict]) -> None:
        """Точечное обновление строки таблицы по link_dict.

        Безопасно вызывает table.update_link_by_id, если доступно.
        """
        if not link_dict:
            return
        table = self.table
        if table is None:
            logger.debug("LinksTableController.update_row: no table available")
            return
        try:
            table.update_link_by_id(link_dict)
        except (TypeError, ValueError) as e:
            # Некорректный link_dict — не падаем, но явно логируем
            logger.warning("LinksTableController.update_row: invalid link_dict: %s", e)
        except AttributeError as e:
            # Таблица не реализует требуемый метод — это программная ошибка, пробрасываем
            logger.error("LinksTableController.update_row: table missing update_link_by_id: %s", e)
            raise

    # --- Slots for business signals ---
    def on_links_loaded(self, links: list[Dict], category_id: int, task_id: int) -> None:
        """Централизованная реакция на загрузку ссылок из бизнес-логики.

        Выполняет populate только если это текущая категория, чтобы избежать рассинхронизации UI.
        """
        try:
            # Явно используем переданный провайдер категории
            current_category_id = self.category_provider.current_category_id
            if current_category_id is not None and category_id != current_category_id:
                logger.info(
                    "Пропуск обновления таблицы: загружены ссылки для категории %s (task_id=%s), но текущая категория = %s",
                    category_id,
                    task_id,
                    current_category_id,
                )
                return
            self.table.populate(links)
        except Exception as e:
            logger.error("LinksTableController.on_links_loaded: failed: %s", e, exc_info=True)

    def on_search_results(self, search_results: list[Dict]) -> None:
        """Обновить таблицу результатами поиска централизованно."""
        try:
            self.table.populate(search_results, mode="search")
        except Exception as e:
            logger.error("LinksTableController.on_search_results: failed: %s", e, exc_info=True)

    # --- Slots for link_operations signals ---
    def on_links_changed(self, category_id: Optional[int]) -> None:
        """Слот для сигнала link_operations.links_changed(int)."""
        self.reload(category_id)

    def on_link_saved(self, payload: Optional[Dict] = None) -> None:
        """Слот для сигнала link_operations.link_saved(dict)."""
        try:
            cat_id = None
            if isinstance(payload, dict):
                cat_id = payload.get("category_id")
            self.reload(cat_id)
        except Exception:
            logger.exception("LinksTableController.on_link_saved: failed")

    def on_link_deleted(self, payload: Optional[Dict] = None) -> None:
        """Слот для сигнала link_operations.link_deleted(dict)."""
        try:
            cat_id = None
            if isinstance(payload, dict):
                cat_id = payload.get("category_id")
            self.reload(cat_id)
        except Exception:
            logger.exception("LinksTableController.on_link_deleted: failed")

    # --- Internals ---
