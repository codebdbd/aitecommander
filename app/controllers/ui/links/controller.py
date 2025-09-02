import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject

from app.controllers.business.links_business import LinksBusinessLogic
from app.utils.ui.qt.roles import get_selected_rows as get_selected_rows_util
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
        *,
        link_operations=None,
        links_table_controller=None,
    ):
        super().__init__()
        if table_widget is None:
            logger.error("LinksUIController: table_widget is required")
            raise ValueError("LinksUIController: table_widget is required")
        if business_logic is None:
            logger.error("LinksUIController: business_logic is required")
            raise ValueError("LinksUIController: business_logic is required")
        if links_table_controller is None:
            logger.error("LinksUIController: links_table_controller is required")
            raise ValueError("LinksUIController: links_table_controller is required")
        if link_operations is None:
            logger.error("LinksUIController: link_operations is required")
            raise ValueError("LinksUIController: link_operations is required")
        self.table = table_widget
        self.business = business_logic
        self.main = main_window
        self._row_by_link_id: dict[int, int] = {}
        self.table_controller = links_table_controller

        # Инициализация подмодулей с явными зависимостями
        # Передача провайдера категории: сначала ui_state, иначе сам main_window,
        # если он предоставляет get_current_category_id (важно для тестов/заглушек)
        _ui_state = getattr(main_window, "ui_state", None)
        _kwargs = {}
        if _ui_state is not None:
            _kwargs["ui_state"] = _ui_state
        elif hasattr(main_window, "get_current_category_id"):
            _kwargs["category_provider"] = main_window

        # Явная проводка зависимости structure_tree для LinksUIHandlers (если доступна)
        structure = getattr(main_window, "structure", None)
        tree = getattr(structure, "tree", None) if structure is not None else None
        if tree is not None:
            _kwargs["structure_tree"] = tree

        self.handlers = LinksUIHandlers(
            self,
            link_operations=link_operations,
            links_table_controller=self.table_controller,
            **_kwargs,
        )
        self.clipboard = LinksUIClipboard(self, link_operations=link_operations)
        self.link_ops = LinksUILinkOperations(self, link_operations=link_operations)

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
        """Получить ссылку по номеру строки, делегируя вызов таблице.

        Проверки границ и обработка ошибок инкапсулированы в методе представления.
        """
        try:
            return self.table.get_link_at(row)
        except Exception as e:
            logger.error(f"Ошибка при вызове table.get_link_at: {e}")
            return None

    def get_row_count(self) -> int:
        """Получить количество строк в таблице."""
        try:
            model = self.table.model()
            return model.rowCount() if model is not None else 0
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Ошибка при получении количества строк: {e}")
            return 0

    def has_selection(self) -> bool:
        """Проверить, есть ли выделение в таблице."""
        try:
            sel = self.table.selectionModel()
            return bool(sel and sel.hasSelection())
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Ошибка при проверке выделения: {e}")
            return False

    def current_row(self) -> int:
        """Получить номер текущей строки."""
        try:
            idx = self.table.currentIndex()
            return idx.row() if idx and idx.isValid() else -1
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Ошибка при получении текущей строки: {e}")
            return -1

    def select_row(self, row: int) -> None:
        """Выделить строку по номеру."""
        self.table.selectRow(row)

    def set_current_cell(self, row: int, column: int) -> None:
        """Установить текущую ячейку."""
        try:
            model = self.table.model()
            if model is None:
                return
            index = model.index(row, column)
            if index and index.isValid():
                self.table.setCurrentIndex(index)
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Ошибка при установке текущей ячейки: {e}")

    def scroll_to_row(self, row: int) -> None:
        """Прокрутить таблицу к строке."""
        try:
            model = self.table.model()
            if model is None:
                return
            index = model.index(row, 0)
            if index and index.isValid():
                self.table.scrollTo(index)
        except (AttributeError, RuntimeError) as e:
            logger.error(f"Ошибка при прокрутке к строке: {e}")


    def get_selected_rows(self) -> List[int]:
        """Получить номера выделенных строк через общую утилиту."""
        return get_selected_rows_util(self.table)

    def quick_add_link(self, link_type: str, category_id: int = None):
        """Быстрое добавление ссылки."""
        self.link_ops.quick_add_link(link_type, category_id)

    def on_quick_add_requested(self, payload: Dict | None):
        """Слот для quickAddRequested(payload) из TopPanelWidget."""
        if not isinstance(payload, dict):
            return
        self.quick_add_link(payload.get("link_type"), payload.get("category_id"))

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
        """Централизованная перезагрузка текущей категории через LinksTableController."""
        category_id = self.main.get_current_category_id()
        if not category_id:
            return
        try:
            self.table_controller.reload(category_id)
        except Exception as e:
            logger.error(f"Failed to reload category (id={category_id}): {e}")


