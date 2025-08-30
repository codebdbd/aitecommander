import logging
from typing import Optional, Dict

from PyQt6.QtCore import QObject


logger = logging.getLogger(__name__)


class LinksTableController(QObject):
    """Централизованный контроллер обновления таблицы ссылок.

    Задачи:
    - Безопасная перезагрузка данных по категории: reload(category_id)
    - Точечное обновление строки таблицы по link_dict: update_row(link_dict)
    - Централизованное логирование и защита от параллельных обновлений
    """

    def __init__(self, main_window, *, table, links_business):
        """Инициализация контроллера с явными зависимостями.

        :param main_window: главное окно (родитель по QObject)
        :param table: виджет таблицы ссылок, должен иметь метод update_link_by_id(dict)
        :param links_business: бизнес-логика ссылок с методом load_links(category_id)
        """
        super().__init__(parent=main_window)
        self.main = main_window
        self.table = table
        self.business = links_business
        if self.table is None or self.business is None:
            raise ValueError("LinksTableController: table и links_business должны быть переданы явно")
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
            self._fallback_load(category_id)
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
        try:
            table = self.table
            if table is None:
                logger.debug("LinksTableController.update_row: no table available")
                return
            if hasattr(table, "update_link_by_id"):
                table.update_link_by_id(link_dict)
            else:
                logger.debug("LinksTableController.update_row: table has no update_link_by_id")
        except Exception as e:
            logger.warning("LinksTableController.update_row: failed: %s", e)

    # --- Internals ---
    def _fallback_load(self, category_id: int) -> None:
        business = self.business
        if business is not None:
            # Пусть исключения поднимутся в reload(), где будет единообразное логирование
            business.load_links(category_id)
            return
        logger.warning(
            "LinksTableController._fallback_load: no business available to load links"
        )
