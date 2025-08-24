import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject

from app.controllers.business.links_business import LinksBusinessLogic
from app.views.link import LinksTableView

from .clipboard import LinksUIClipboard
from .handlers import LinksUIHandlers
from .link_operations import LinksUILinkOperations

logger = logging.getLogger(__name__)


class LinksUIController(QObject):
    """UI-контроллер для управления таблицей ссылок."""

    def __init__(
        self,
        table_widget: LinksTableView,
        business_logic: LinksBusinessLogic,
        main_window,
    ):
        super().__init__()
        self.table = table_widget
        self.business = business_logic
        self.main = main_window
        self._row_by_link_id: dict[int, int] = {}

        # Инициализация подмодулей
        self.handlers = LinksUIHandlers(self)
        self.clipboard = LinksUIClipboard(self)
        self.link_ops = LinksUILinkOperations(self)

        # Подключение сигналов
        self.handlers._connect_signals()
        self.handlers._connect_table_signals()
        # Индексация строк после любого массового обновления таблицы
        try:
            if hasattr(self.table, "table_populated"):
                self.table.table_populated.connect(self.rebuild_row_index)
        except Exception as e:
            logger.debug(f"Failed to connect table_populated: {e}")

        # ЦЕНТРАЛИЗОВАНО: начальная загрузка категории
        self._reload_current_category()

        # Подключение виджетов topbar (если уже существуют к моменту создания контроллера)
        # Безопасные ленивые подключения
        try:
            if (
                hasattr(self.main, "recent_links_widget")
                and self.main.recent_links_widget
            ):
                self._connect_recent_widget_signals()
            if hasattr(self.main, "fav_widget") and self.main.fav_widget:
                self._connect_favorites_widget_signals()
        except Exception as e:
            logger.debug(f"Topbar widgets not ready yet: {e}")

    def shutdown(self, timeout: int = 2000):
        """Корректное завершение работы."""
        self.business.shutdown(timeout)

    def load_category(self, category_id: int):
        """Загрузить ссылки для категории - ТОЛЬКО бизнес-логика.

        ЦЕНТРАЛИЗОВАНО: UI координация перенесена в UIStateManager.load_category().
        Этот метод теперь содержит только бизнес-логику загрузки данных.
        """
        self.business.load_links(category_id)

    def on_search(self, text: str):
        """Обработка поискового запроса."""
        if not text.strip():
            # Если поиск пустой, загружаем текущую категорию
            self._reload_current_category()
        else:
            self.business.search_links(text)

    def get_link_at(self, row: int) -> Optional[Dict]:
        """Получить ссылку по номеру строки."""
        if 0 <= row < self.table.rowCount():
            link = self.table.get_link_at(row)

            # ДИАГНОСТИЧЕСКОЕ ЛОГИРОВАНИЕ ДЛЯ ARGS

            return link
        return None

    def get_row_count(self) -> int:
        """Получить количество строк в таблице."""
        return self.table.rowCount()

    def has_selection(self) -> bool:
        """Проверить, есть ли выделение в таблице."""
        return bool(self.table.selectedItems())

    def current_row(self) -> int:
        """Получить номер текущей строки."""
        return self.table.currentRow()

    def select_row(self, row: int) -> None:
        """Выделить строку по номеру."""
        self.table.selectRow(row)

    def set_current_cell(self, row: int, column: int) -> None:
        """Установить текущую ячейку."""
        self.table.setCurrentCell(row, column)

    def scroll_to_row(self, row: int) -> None:
        """Прокрутить таблицу к строке."""
        item = self.table.item(row, 0)
        if item:
            self.table.scrollToItem(item)

    # get_link_by_row удалён как дублирующий get_link_at

    def get_selected_rows(self) -> List[int]:
        """Получить номера выделенных строк."""
        return sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})

    def quick_add_link(self, link_type: str, category_id: int = None):
        """Быстрое добавление ссылки."""
        self.link_ops.quick_add_link(link_type, category_id)

    def show_note_dialog(self, link: Dict):
        """Показать диалог заметки для ссылки."""
        self.link_ops.show_note_dialog(link)

    def get_selected_links(self) -> List[Dict]:
        """Получить выбранные ссылки."""
        return self.clipboard.get_selected_links()

    def open_link(self, link: Dict):
        """Открыть ссылку."""
        logger.info(f"open_link called with link: {link}")
        self.link_ops._open_link(link)

    def toggle_favorite(self, link: Dict = None):
        """Переключить статус избранного."""
        self.link_ops._toggle_fav(link)

    def cut_selected_links(self):
        """Вырезать выбранные ссылки."""
        self.clipboard.cut_link()

    def copy_selected_links(self):
        """Копировать выбранные ссылки."""
        self.clipboard.copy_link()

    def paste_links(self):
        """Вставить ссылки из буфера обмена."""
        self.clipboard.paste_link()

    def delete_selected_links(self):
        """Удалить выбранные ссылки."""
        links = self.clipboard.get_selected_links()
        self.clipboard.delete_links(links)

    def focus_on_link(self, link_id: int) -> None:
        """Сфокусироваться на ссылке с указанным ID.

        Перенос логики из MainWindow._restore_table_selection для устранения дублирования
        и чтобы внешние вызовы (см. link_operations_controller) работали через UI-контроллер.
        """
        try:
            # Быстрый путь: используем индекс, если он есть
            row = self._row_by_link_id.get(link_id)
            if row is None:
                # Ленивая перестройка индекса
                self.rebuild_row_index()
                row = self._row_by_link_id.get(link_id)
            if row is not None:
                self.select_row(row)
                self.set_current_cell(row, 0)
                self.scroll_to_row(row)
                try:
                    if hasattr(self.table, "setFocus"):
                        self.table.setFocus()
                except Exception:
                    pass
            else:
                logger.debug(
                    f"focus_on_link: link_id {link_id} not found in current table"
                )
        except Exception as e:
            logger.error(f"Failed to focus on link {link_id}: {e}")

    def rebuild_row_index(self) -> None:
        """Переcтроить индекс link_id -> row по текущему содержимому таблицы."""
        try:
            self._row_by_link_id.clear()
            rows = self.get_row_count()
            for row in range(rows):
                link = self.get_link_at(row)
                if link and "id" in link:
                    self._row_by_link_id[link["id"]] = row
        except Exception as e:
            logger.debug(f"rebuild_row_index failed: {e}")

    def _reload_current_category(self) -> None:
        """Централизованная перезагрузка текущей категории через UIStateManager или бизнес-логику."""
        category_id = self.main.get_current_category_id()
        if not category_id:
            return
        try:
            if hasattr(self.main, "ui_state") and self.main.ui_state:
                self.main.ui_state.update_category_without_stack_switch(category_id)
            else:
                # Fallback: только бизнес-логика без UI координации
                self.business.load_links(category_id)
        except Exception as e:
            logger.error(f"Failed to reload category (id={category_id}): {e}")

    # --- Handlers for Recent/Favorites widgets ---
    def _connect_recent_widget_signals(self):
        try:
            rlw = self.main.recent_links_widget
            rlw.refresh_requested.connect(self.on_recent_refresh_requested)
            # linkClicked уже подключен к window.open_link на уровне инициализатора
        except Exception as e:
            logger.error(f"Failed to connect RecentLinksWidget signals: {e}")

    def _connect_favorites_widget_signals(self):
        try:
            fw = self.main.fav_widget
            fw.refresh_requested.connect(self.on_favorites_refresh_requested)
            fw.clear_requested.connect(self.on_favorites_clear_requested)
            # linkClicked уже подключен к window.open_link на уровне инициализатора
        except Exception as e:
            logger.error(f"Failed to connect FavoritesWidget signals: {e}")

    def on_recent_refresh_requested(self, limit: int):
        """Получить последние ссылки и передать в виджет."""
        try:
            links = self.business.get_recent_links(limit)
            if (
                hasattr(self.main, "recent_links_widget")
                and self.main.recent_links_widget
            ):
                self.main.recent_links_widget.set_recent_links(links)
        except Exception as e:
            logger.error(f"Failed to refresh recent links: {e}")

    def on_favorites_refresh_requested(self):
        """Получить избранные ссылки и передать в виджет."""
        try:
            favs = self.business.get_favorite_links()
            if hasattr(self.main, "fav_widget") and self.main.fav_widget:
                self.main.fav_widget.set_favorites(favs)
        except Exception as e:
            logger.error(f"Failed to refresh favorites: {e}")

    def on_favorites_clear_requested(self):
        """Очистить избранное и инициировать обновление."""
        try:
            self.business.clear_favorites()
            # Обновляем панель избранного
            self.on_favorites_refresh_requested()
            # Также можно обновить таблицу текущей категории, если нужно
            category_id = self.main.get_current_category_id()
            if category_id and hasattr(self.main, "ui_state") and self.main.ui_state:
                self.main.ui_state.update_category_without_stack_switch(category_id)
        except Exception as e:
            logger.error(f"Failed to clear favorites: {e}")
