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
        # Перенесено в централизованный LinksTableController, чтобы избежать прямых populate и возможных циклов
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
        # Флаг реентрантности для защиты от зацикливания при переупорядочивании
        # (например, когда обновление порядка в БД приводит к перезагрузке UI)
        self._handling_reorder: bool = False
        self.table.links_reordered.connect(self._on_links_reordered)
        # Эксклюзивность выбора: любое выделение в таблице снимает выделение в дереве
        try:
            sel_model = self.table.selectionModel()
            if sel_model is not None:
                sel_model.selectionChanged.connect(self._on_table_selection_changed)
        except Exception:
            pass
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

        # Убираем прямое обновление таблицы: используем централизованный контроллер через сигнал
        try:
            link_ops = self.link_operations
            if link_ops and isinstance(category_id, int) and category_id > 0:
                link_ops.links_changed.emit(category_id)
            else:
                logger.debug("LinksUIHandlers: link_operations not available, cannot emit links_changed")
        except Exception as e:
            logger.warning(f"Failed to emit links_changed from _update_table: {e}")

    def _update_search_results(self, search_results: List[Dict]):
        """Обновить результаты поиска."""
        self.table.populate(search_results, mode="search")

    def _complete_toggle_fav(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Завершить переключение избранного."""
        # Эмитим сигналы вместо прямых обращений к контроллерам
        try:
            link_ops = self.link_operations
            if link_ops:
                # Сообщаем о возможном изменении таблицы ссылок (категория из ссылки или текущая)
                cat_id = None
                if link is not None:
                    cat_id = link.get("category_id")
                if not isinstance(cat_id, int) or cat_id <= 0:
                    try:
                        cat_id = getattr(self.main, "get_current_category_id", lambda: None)()
                    except Exception:
                        cat_id = None
                if isinstance(cat_id, int) and cat_id > 0:
                    link_ops.links_changed.emit(cat_id)
                # В любом случае сигнализируем об изменении избранного
                link_ops.favorites_changed.emit()
            else:
                logger.debug("LinksUIHandlers: link_operations not available to emit signals")
        except Exception as e:
            logger.warning(f"Failed to emit signals after toggle favorite: {e}")

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

        # Эмитим сигналы вместо прямых обновлений UI
        try:
            link_ops = self.link_operations
            if link_ops:
                cat_id = updated_link.get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    link_ops.links_changed.emit(cat_id)
                # Обновление ссылки (заметки, атрибутов) влияет на панель "Недавние"
                if hasattr(link_ops, "recents_changed"):
                    link_ops.recents_changed.emit()
            else:
                logger.debug("LinksUIHandlers: link_operations not available to emit signals on link update")
        except Exception as e:
            logger.warning(f"Failed to emit signals after link update: {e}")

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
        """Обработка изменения порядка ссылок с защитой от реентрантности."""
        try:
            # Предотвращаем повторные входы, если обработчик уже выполняется
            if getattr(self, "_handling_reorder", False):
                logger.debug("[Reorder] Suppressed recursive _on_links_reordered call")
                return

            self._handling_reorder = True

            # Пустые или тривиальные входные данные игнорируем
            if not link_ids or not isinstance(link_ids, list):
                return

            # Выполняем обновление порядка через бизнес-логику
            self.business.update_link_order(link_ids)

        except Exception as e:
            logger.error(f"[Reorder] Error while handling links_reordered: {e}")
        finally:
            self._handling_reorder = False

    def _on_table_selection_changed(self, _selected, _deselected):
        """Эксклюзивность: при выделении в таблице очищаем выделение в дереве."""
        try:
            structure = getattr(self.main, "structure", None)
            tree = getattr(structure, "tree", None) if structure else None
            if tree and hasattr(tree, "clearSelection"):
                tree.clearSelection()
        except Exception:
            pass
