import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt

from .base_component import BaseLinksUIComponent

logger = logging.getLogger(__name__)


class LinksUIHandlers(BaseLinksUIComponent):
    """Обработчики событий для LinksUIController."""

    def _connect_signals(self):
        """Подключение сигналов от бизнес-логики."""
        if getattr(self, "_signals_connected", False):
            return
        self.business.links_loaded.connect(self._update_table)
        self.business.search_results_ready.connect(self._update_search_results)
        self.business.favorites_counted.connect(self._complete_toggle_fav)
        self.business.link_updated.connect(self._on_link_updated)
        self.business.error_occurred.connect(self._handle_error)
        self._signals_connected = True

    def _connect_table_signals(self):
        """Подключение сигналов от таблицы."""
        if getattr(self, "_table_signals_connected", False):
            return
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        # QTableView: используем index-based сигналы и адаптируем к существующим обработчикам
        try:
            self.table.doubleClicked.connect(
                lambda idx: self._on_double_click(idx.row(), idx.column())
            )
        except Exception:
            pass
        try:
            self.table.clicked.connect(
                lambda idx: self._on_cell_clicked(idx.row(), idx.column())
            )
        except Exception:
            pass
        self.table.links_reordered.connect(self._on_links_reordered)
        self._table_signals_connected = True

        # Обработка клавиш теперь централизована в KeyboardManager

    def _update_table(self, links: List[Dict], category_id: int, task_id: int):
        """Обновляет таблицу ссылок новыми данными."""
        # Защита от рассинхронизации: принимаем только ссылки для текущей категории
        current_category_id = getattr(self.main, "current_category_id", None)
        if current_category_id is not None and category_id != current_category_id:
            # Например, пользователь успел переключить категорию, пока грузились ссылки
            logger.info(
                "Пропуск обновления таблицы: загружены ссылки для категории %s (task_id=%s), "
                "но текущая категория = %s",
                category_id,
                task_id,
                current_category_id,
            )
            return

        self.table.populate(links)

    def _update_search_results(self, search_results: List[Dict]):
        """Обновить результаты поиска."""
        self.table.populate(search_results, mode="search")

    def _complete_toggle_fav(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Завершить переключение избранного."""
        # 1) Если нам передали конкретную ссылку — обновляем строку таблицы
        if link is not None:
            try:
                # Обновить отображение строки, если таблица поддерживает точечное обновление
                if hasattr(self.table, "update_link_by_id"):
                    self.table.update_link_by_id(link)
            except Exception as e:
                logger.warning(f"Failed to update table row for toggled favorite: {e}")
        else:
            # Бывают случаи вызова без конкретной ссылки — не выходим молча
            logger.warning(
                "_complete_toggle_fav called without specific link; proceeding with favorites refresh only"
            )

        # 2) В любом случае обновляем панель избранного, чтобы пересчитать список/счетчик
        try:
            if hasattr(self.main, "fav_widget") and self.main.fav_widget:
                self.main.fav_widget.update_favorites()
        except Exception as e:
            logger.warning(f"Failed to refresh favorites widget after toggle: {e}")

    def _handle_error(self, error_msg: str):
        """Обработать ошибку."""
        logger.error(f"LinksUIController error: {error_msg}")
        self._show_error(f"An error occurred: {error_msg}")

    def _on_link_updated(self, updated_link: Dict):
        """Обработка обновления ссылки."""
        # Диагностическое логирование вместо неиспользуемых локальных переменных
        try:
            logger.debug(
                "Link updated: id=%s, name=%s, favorite=%s",
                updated_link.get("id"),
                updated_link.get("name", "Untitled"),
                updated_link.get("is_favorite", False),
            )
        except Exception:
            pass

        if hasattr(self.table, "update_link_by_id"):
            self.table.update_link_by_id(updated_link)
        if hasattr(self.main, "fav_widget"):
            self.main.fav_widget.update_favorites()

    def _on_double_click(self, row: int, column: int):
        """Обработка двойного клика по строке."""
        link = self.controller.get_link_at(row)
        if not link:
            logger.warning(f"No link found at row {row}")
            return

        # Не открываем ссылку при двойном клике по колонке избранного (звезда)
        if column == self.COLUMNS["favorite"]:
            return

        if column == self.COLUMNS["notes"]:
            self.controller.show_note_dialog(link)
        else:
            self.controller.open_link(link)

    def _on_cell_clicked(self, row: int, column: int):
        """Обработка клика по ячейке."""
        link = self.controller.get_link_at(row)
        if not link:
            logger.warning(f"No link found at row {row}")
            return

        if column == self.COLUMNS["favorite"]:
            link_name = link.get("name", "Untitled")

            # Получаем видимое имя через модель (DisplayRole)
            try:
                model = self.table.model()
                idx = (
                    model.index(row, self.COLUMNS["name"]) if model is not None else None
                )
                if idx and idx.isValid():
                    val = model.data(idx, Qt.ItemDataRole.DisplayRole)
                    visible_name = str(val) if val is not None else "Unknown"
                else:
                    visible_name = "Unknown"
            except Exception:
                visible_name = "Unknown"

            if link_name != visible_name:
                logger.warning(
                    f"MISMATCH! Link data does not match visible content! Expected: '{visible_name}', Received: '{link_name}'"
                )

            # Логируем переключение избранного с кратким контекстом
            logger.debug(
                "Toggling favorite: id=%s, name=%s, current=%s",
                link.get("id"),
                link_name,
                link.get("is_favorite", False),
            )

            self.controller.toggle_favorite(link)

    def _on_context_menu(self, pos):
        """Обработка контекстного меню."""
        idx = self.table.indexAt(pos)

        menu = self.main.menu_controller.create_links_context_menu(
            self.table, idx, self.controller.clipboard.paste_link
        )
        if menu:
            menu.exec(self.table.mapToGlobal(pos))

    # Метод _handle_key_press удален - обработка клавиш централизована в KeyboardManager

    def _on_links_reordered(self, link_ids: list):
        """Обработка изменения порядка ссылок."""
        self.business.update_link_order(link_ids)
