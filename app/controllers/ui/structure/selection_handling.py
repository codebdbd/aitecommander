# app/controllers/structure/selection_handling.py

import logging

from PyQt6.QtWidgets import QTreeWidgetItem

from app.utils.db.synchronization import signal_guard
from app.utils.ui.qt.roles import get_tree_tuple

# Используем строковые литералы "section" и "category"

logger = logging.getLogger(__name__)


class SelectionHandling:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.main = controller.main
        self.business = controller.business
        # Запоминаем последний обработанный выбор, чтобы игнорировать дубликаты подряд
        # Формат: ("section"|"category", int id)
        self._last_handled = None
        # Счётчик подавления обработки выбора (реентерабельный)
        self._suppress_counter = 0

    # --- Централизованное подавление обработки выбора во время батч-операций ---
    def begin_suppress_selection(self) -> None:
        """Увеличить счётчик подавления обработки выбора.

        Пока счётчик > 0, методы обработки выбора будут игнорировать события.
        """
        try:
            self._suppress_counter += 1
            logger.debug(
                "Selection handling suppressed (level=%s)", self._suppress_counter
            )
        except Exception:
            # На всякий случай не ломаем поток
            self._suppress_counter = max(1, getattr(self, "_suppress_counter", 0))

    def end_suppress_selection(self) -> None:
        """Снизить счётчик подавления обработки выбора до минимума 0."""
        try:
            self._suppress_counter = max(0, self._suppress_counter - 1)
            logger.debug(
                "Selection handling resumed (level=%s)", self._suppress_counter
            )
        except Exception:
            self._suppress_counter = 0

    def is_suppressed(self) -> bool:
        return bool(self._suppress_counter > 0)

    def _on_section_selected(self, section_id: int, categories_data: list) -> None:
        if hasattr(self.main, "ui_state") and self.main.ui_state:
            # Используем централизованный UIStateManager
            self.main.ui_state.switch_to_category_tiles(categories_data)
        else:
            # Fallback на старую логику - используем централизованные методы UIStateManager
            if hasattr(self.main, "ui_state") and self.main.ui_state:
                self.main.ui_state.switch_to_category_tiles(categories_data)
            else:
                # Последний fallback - прямые вызовы
                self.main.tiles.set_categories(categories_data)
                self.main.stack.setCurrentIndex(0)

    def _on_category_selected(self, category_id: int) -> None:
        """ЦЕНТРАЛИЗОВАНО: Использует UIStateManager.load_category() вместо MainWindow.load_category()"""
        if hasattr(self.main, "ui_state") and self.main.ui_state:
            self.main.ui_state.load_category(
                category_id, source="SelectionHandling._on_category_selected"
            )
        else:
            logger.error(
                "UIStateManager not available in SelectionHandling._on_category_selected"
            )

    def _on_error_occurred(self, title: str, message: str) -> None:
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_warning(
            self.main,
            title or "Предупреждение",
            message,
            informative_text="Проверьте корректность действий и повторите попытку.",
        )

    def _select_first_item_if_needed(self) -> None:
        if not self.tree.selectedItems() and self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
            # Устанавливаем фокус на дерево для корректной работы клавиатурного управления
            self.tree.setFocus()

    @signal_guard()
    def _on_current_changed(
        self, current: QTreeWidgetItem, _prev: QTreeWidgetItem
    ) -> None:
        # Глобальное подавление во время пакетных операций
        if self.is_suppressed():
            logger.debug("Selection changed while suppressed - ignoring event")
            return
        if current is None:
            # Во время перезагрузки структуры (update_structure_tree/load_structure) текущее
            # выделение может кратковременно становиться None. Очищать плитки в этот момент
            # приводит к "промежуточному пустому окну" справа. Ничего не делаем и выходим.
            logger.debug(
                "Selection changed to None - skip clearing tiles during reload"
            )
            return

        # Получаем информацию об элементе для логирования
        try:
            t = get_tree_tuple(current, 0)
            if t:
                item_type, item_id = t
                logger.debug(f"Selection changed to {item_type} #{item_id}")
            else:
                logger.debug("Selection changed to item without data")
        except Exception as e:
            logger.warning(f"Could not get item data for logging: {e}")

        self._handle_item_selection(current)

    def _on_single_click(self, item: QTreeWidgetItem, _col: int) -> None:
        # Избегаем дублирующей обработки: если клик пришёл по уже текущему элементу,
        # то событие currentItemChanged уже покроет этот кейс или переключения нет вовсе.
        try:
            cur = self.tree.currentItem()
        except Exception:
            cur = None
        if item is cur:
            return
        self._handle_item_selection(item)

    @signal_guard()
    def _handle_item_selection(self, item: QTreeWidgetItem) -> None:
        # Глобальное подавление во время пакетных операций
        if self.is_suppressed():
            logger.debug("Handle selection while suppressed - skip")
            return
        # Эксклюзивность: любое выделение в дереве очищает выделение таблицы
        try:
            table = getattr(self.main, "table", None)
            if table and hasattr(table, "clearSelection"):
                table.clearSelection()
        except Exception:
            pass
        try:
            t = get_tree_tuple(item, 0)
            if not t:
                logger.warning("Invalid item data: None")
                return

            typ, id_ = t
            if typ not in ("section", "category") or not isinstance(id_, int):
                logger.warning("Invalid item data types for selection")
                return

            # Защита от повторной обработки того же элемента подряд
            if self._last_handled == (typ, id_):
                logger.debug(f"Skip duplicate selection handling for {typ} #{id_}")
                return
            logger.info(f"Handling selection: {typ} #{id_}")

            if typ == "section":
                self.business.select_section(id_)
                logger.debug(f"Section #{id_} selected - categories will be loaded")
            elif typ == "category":
                self.business.select_category(id_)
                logger.debug(f"Category #{id_} selected - links will be loaded")
            else:
                logger.warning(f"Unknown item type: {typ}")

            # Обновляем последний обработанный выбор только после успешной обработки
            self._last_handled = (typ, id_)

        except Exception as e:
            logger.error(f"Error handling item selection: {e}", exc_info=True)

    def _restore_selection_after_load(self, item_type: str, item_id: int) -> None:
        item = self.controller.tree_manager._find_item_by_id(item_type, item_id)
        if item:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)
            self.tree.blockSignals(False)
            # Явно обрабатываем выбор после перезагрузки, т.к. сигналы были заблокированы
            self._handle_item_selection(item)

    def _set_focus_on_new_item_by_id(self, item_type: str, item_id: int) -> None:
        item = self.controller.tree_manager._find_item_by_id(item_type, item_id)
        if item:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)
            if item_type == "category":
                # ЦЕНТРАЛИЗОВАНО: Для новой категории показываем таблицу ссылок
                if hasattr(self.main, "ui_state") and self.main.ui_state:
                    self.main.ui_state.load_category(
                        item_id, source="SelectionHandling._handle_item_selection"
                    )
                else:
                    logger.error(
                        "UIStateManager not available in _handle_item_selection"
                    )

    def _select_category_without_stack_switch(self, category_id: int) -> None:
        """ЦЕНТРАЛИЗОВАНО: Обновляем current_category_id без переключения стека"""
        if hasattr(self.main, "ui_state") and self.main.ui_state:
            self.main.ui_state.update_category_without_stack_switch(category_id)
        else:
            logger.error(
                "UIStateManager not available in _select_category_without_stack_switch"
            )

    def _restore_category_selection(self, category_id: int) -> None:
        item = self.controller.tree_manager._find_item_by_id("category", category_id)
        if item:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)
            self.tree.blockSignals(False)
            # Гарантируем полную обработку выбора и переключение UI
            self._handle_item_selection(item)
