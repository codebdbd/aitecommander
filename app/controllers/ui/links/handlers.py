import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt

from .base_component import BaseLinksUIComponent

logger = logging.getLogger(__name__)


class SetupError(Exception):
    """Ошибка проводки критичных сигналов LinksUIHandlers."""


class LinksUIHandlers(BaseLinksUIComponent):
    """Обработчики событий для LinksUIController."""

    def __init__(
        self,
        controller,
        *,
        link_operations,
        links_table_controller,
        ui_state=None,
        category_provider=None,
        structure_tree=None,
    ):
        # Явные требования зависимостей для лучшей диагностируемости
        if links_table_controller is None:
            raise ValueError(
                "LinksUIHandlers requires explicit 'links_table_controller' dependency"
            )
        provider = ui_state or category_provider
        if provider is None:
            raise ValueError(
                "LinksUIHandlers requires 'ui_state' or 'category_provider' dependency"
            )
        # Обязательный контракт: требуется метод get_current_category_id()
        getter = getattr(provider, "get_current_category_id", None)
        if getter is None or not callable(getter):
            raise TypeError(
                "'ui_state'/'category_provider' must provide callable get_current_category_id()"
            )
        self._category_provider = provider

        # Зависимость дерева структуры для очистки выбора (инжектируется контроллером окна)
        # Для unit-тестов wiring может отсутствовать, тогда поведение будет только логировать ошибку
        self._structure_tree = structure_tree

        super().__init__(
            controller, link_operations, links_table_controller=links_table_controller
        )

    def _connect_signals(self):
        """Подключение сигналов от бизнес-логики."""
        if getattr(self, "_signals_connected", False):
            return
        # Перенесено в централизованный LinksTableController, чтобы избежать прямых populate и возможных циклов
        try:
            if hasattr(self.business, "favorites_counted"):
                self.business.favorites_counted.connect(self._complete_toggle_fav)
            if hasattr(self.business, "link_updated"):
                self.business.link_updated.connect(self._on_link_updated)
            if hasattr(self.business, "error_occurred"):
                self.business.error_occurred.connect(self._handle_error)
        except Exception:
            # Безопасность: в тестах бизнес может быть простым мок-объектом
            pass
        self._signals_connected = True

    def _connect_table_signals(self):
        """Подключение сигналов от таблицы."""
        if getattr(self, "_table_signals_connected", False):
            return
        # Некритичные настройки контекстного меню — только логируем ошибки
        try:
            if hasattr(self.table, "setContextMenuPolicy"):
                self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        except (AttributeError, TypeError):
            logger.exception("Failed to set context menu policy on links table")
        try:
            if hasattr(self.table, "customContextMenuRequested"):
                self.table.customContextMenuRequested.connect(self._on_context_menu)
        except (AttributeError, TypeError):
            logger.exception("Failed to connect customContextMenuRequested for links table")

        # QTableView: используем index-based сигналы и адаптируем к существующим обработчикам
        try:
            self.table.doubleClicked.connect(
                lambda idx: self._on_double_click(idx.row(), idx.column())
            )
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect doubleClicked: {e}") from e
        try:
            self.table.clicked.connect(
                lambda idx: self._on_cell_clicked(idx.row(), idx.column())
            )
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect clicked: {e}") from e
        # Флаг реентрантности для защиты от зацикливания при переупорядочивании
        # (например, когда обновление порядка в БД приводит к перезагрузке UI)
        self._handling_reorder: bool = False
        try:
            if hasattr(self.table, "links_reordered"):
                self.table.links_reordered.connect(self._on_links_reordered)
            else:
                raise AttributeError("links_reordered signal is missing")
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect links_reordered: {e}") from e
        # Эксклюзивность выбора: любое выделение в таблице снимает выделение в дереве
        try:
            if hasattr(self.table, "selectionModel"):
                sel_model = self.table.selectionModel()
                if sel_model is None:
                    raise AttributeError("selectionModel() returned None")
                sel_model.selectionChanged.connect(self._on_table_selection_changed)
            else:
                raise AttributeError("selectionModel() is missing on table")
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect selectionChanged: {e}") from e
        self._table_signals_connected = True

        # Обработка клавиш теперь централизована в KeyboardManager

    def _update_table(self, links: List[Dict], category_id: int, task_id: int):
        """Обновляет таблицу ссылок новыми данными."""
        # Защита от рассинхронизации: принимаем только ссылки для текущей категории
        current_category_id = self._category_provider.get_current_category_id()
        if category_id != current_category_id:
            # Например, пользователь успел переключить категорию, пока грузились ссылки
            logger.debug(
                "Игнорируем результаты task_id=%s: категория результатов = %s, "
                "но текущая категория = %s",
                task_id,
                category_id,
                current_category_id,
            )
            return

        # Напрямую обновляем таблицу, не полагаясь на асинхронную обработку сигнала
        try:
            self.links_table_controller.on_links_loaded(links, category_id, task_id)
        except Exception:
            logger.exception(
                "LinksUIHandlers._update_table: links_table_controller.on_links_loaded failed"
            )

        # Сигнал оставляем для внешних подписчиков
        try:
            if isinstance(category_id, int) and category_id > 0:
                self.link_operations.emit_links_changed(category_id)
        except Exception as e:
            logger.warning(f"Failed to emit links_changed from _update_table: {e}")

    def _update_search_results(self, search_results: List[Dict]):
        """Обновить результаты поиска."""
        try:
            self.links_table_controller.on_search_results(search_results)
        except Exception:
            logger.exception(
                "LinksUIHandlers._update_search_results: links_table_controller.on_search_results failed"
            )

    def _complete_toggle_fav(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Завершить переключение избранного."""
        # Централизуем эмиссию сигналов в LinkOperationsController
        try:
            cat_id = None
            if link is not None:
                cat_id = link.get("category_id")
            if not isinstance(cat_id, int) or cat_id <= 0:
                # Используем явный провайдер вместо getattr(self.main, ...)
                cat_id = self._category_provider.get_current_category_id()
            self.link_operations.on_favorite_toggled(cat_id)
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

        # Централизуем эмиссию сигналов в LinkOperationsController
        try:
            self.link_operations.on_link_updated(updated_link)
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
            tree = self._structure_tree
            if hasattr(tree, "clearSelection"):
                tree.clearSelection()
            else:
                raise AttributeError("structure_tree lacks clearSelection()")
        except Exception:
            logger.exception("Failed to clear selection on structure_tree from table selection change")
