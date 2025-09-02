# app/controllers/structure/selection_handling.py

import logging

from PyQt6.QtCore import QModelIndex

from app.utils.db.synchronization import signal_guard
from app.utils.ui.qt.roles import get_tree_tuple
from app.controllers.ui.state.task_scheduler import schedule_focus

# Используем строковые литералы "section" и "category"

logger = logging.getLogger(__name__)


class SelectionHandling:
    def __init__(self, controller, category_tiles_controller=None):
        self.controller = controller
        self.tree = controller.tree
        self.main = controller.main
        self.business = controller.business
        # Явная зависимость: контроллер плиток категорий
        if category_tiles_controller is None:
            raise ValueError(
                "SelectionHandling requires a category_tiles_controller dependency"
            )
        self.tiles_controller = category_tiles_controller
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

    def _on_section_selected(self, section_id: int) -> None:
        """Обработка выбора раздела: делегируем обновление плиток контроллеру.

        Новый формат сигнала: передаётся только section_id без categories_data.
        """
        try:
            self.tiles_controller.refresh(int(section_id))
        except Exception:
            logger.exception("SelectionHandling._on_section_selected: controller refresh failed")

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
        try:
            sel_model = self.tree.selectionModel()
            model = self.tree.model()
            if not model:
                return
            has_selection = bool(sel_model and sel_model.hasSelection())
            if not has_selection and model.rowCount() > 0:
                first = model.index(0, 0)
                if first.isValid():
                    sel_model.setCurrentIndex(first, sel_model.SelectionFlag.ClearAndSelect)
                    # Восстанавливаем фокус на дереве через планировщик, без жёстких задержек
                    try:
                        schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
                    except Exception:
                        # Фолбэк на случай проблем с планировщиком
                        try:
                            self.tree.setFocus()
                        except Exception:
                            pass
        except Exception:
            pass

    @signal_guard()
    def _on_current_changed(self, current: QModelIndex, _prev: QModelIndex) -> None:
        # Глобальное подавление во время пакетных операций
        if self.is_suppressed():
            logger.debug("Selection changed while suppressed - ignoring event")
            return
        if not current or not current.isValid():
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

    def _on_single_click(self, index: QModelIndex, _col: int = 0) -> None:
        # Избегаем дублирующей обработки: если клик пришёл по уже текущему элементу,
        # то событие currentChanged уже покроет этот кейс или переключения нет вовсе.
        try:
            cur = self.tree.currentIndex()
        except Exception:
            cur = QModelIndex()
        if index == cur:
            return
        self._handle_item_selection(index)

    @signal_guard()
    def _handle_item_selection(self, index: QModelIndex) -> None:
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
            t = get_tree_tuple(index, 0)
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
                # Используем контроллер плиток категорий из конструктора (обязательная зависимость)
                try:
                    self.tiles_controller.refresh(int(id_))
                except Exception:
                    logger.exception(
                        "SelectionHandling._handle_item_selection: controller refresh failed"
                    )
                logger.debug(f"Section #{id_} selected - tiles refresh requested")
            elif typ == "category":
                # Переход на UIState: не трогаем бизнес-логику здесь
                ui_state = getattr(self.main, "ui_state", None)
                if ui_state is not None and hasattr(ui_state, "load_category"):
                    try:
                        ui_state.load_category(id_, source="SelectionHandling._handle_item_selection")
                        logger.debug(f"Category #{id_} selected - UI state will load links")
                    except Exception:
                        logger.exception("SelectionHandling._handle_item_selection: ui_state.load_category failed")
                        return
                else:
                    logger.error("UIStateManager not available in _handle_item_selection")
                    return
            else:
                logger.warning(f"Unknown item type: {typ}")

            # Обновляем последний обработанный выбор только после успешной обработки
            self._last_handled = (typ, id_)

        except Exception as e:
            logger.error(f"Error handling item selection: {e}", exc_info=True)

    def _restore_selection_after_load(self, item_type: str, item_id: int) -> None:
        model = self.tree.model()
        if not model or not hasattr(model, "index_for"):
            return
        index = model.index_for(item_type, item_id)
        if index and index.isValid():
            sel = self.tree.selectionModel()
            self.tree.blockSignals(True)
            sel.setCurrentIndex(index, sel.SelectionFlag.ClearAndSelect)
            self.tree.scrollTo(index)
            self.tree.blockSignals(False)
            # Явно обрабатываем выбор после перезагрузки, т.к. сигналы были заблокированы
            self._handle_item_selection(index)

    def _set_focus_on_new_item_by_id(self, item_type: str, item_id: int) -> None:
        model = self.tree.model()
        if not model or not hasattr(model, "index_for"):
            return
        index = model.index_for(item_type, item_id)
        if index and index.isValid():
            sel = self.tree.selectionModel()
            sel.setCurrentIndex(index, sel.SelectionFlag.ClearAndSelect)
            self.tree.scrollTo(index)
            # Восстанавливаем фокус на дереве после выбора
            try:
                schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
            except Exception:
                # На случай проблем с планировщиком — прямой вызов как запасной вариант
                try:
                    self.tree.setFocus()
                except Exception:
                    pass
            if item_type == "category":
                # ЦЕНТРАЛИЗОВАНО: Для новой категории показываем таблицу ссылок
                if hasattr(self.main, "ui_state") and self.main.ui_state:
                    self.main.ui_state.load_category(item_id, source="SelectionHandling._handle_item_selection")
                else:
                    logger.error(
                        "UIStateManager not available in _handle_item_selection"
                    )

    def _select_category_without_stack_switch(self, category_id: int) -> None:
        """ЦЕНТРАЛИЗОВАНО: Обновляем current_category_id без переключения стека"""
        try:
            ctrl = getattr(self.main, "links_table_controller", None)
            if ctrl:
                ctrl.reload(category_id)
            else:
                logger.warning(
                    "LinksTableController not available; skip links reload for category #%s",
                    category_id,
                )
        except Exception as e:
            logger.debug(
                "SelectionHandling._select_category_without_stack_switch: reload failed: %s",
                e,
            )

    def _restore_category_selection(self, category_id: int) -> None:
        model = self.tree.model()
        if not model or not hasattr(model, "index_for"):
            return
        index = model.index_for("category", category_id)
        if index and index.isValid():
            sel = self.tree.selectionModel()
            self.tree.blockSignals(True)
            sel.setCurrentIndex(index, sel.SelectionFlag.ClearAndSelect)
            self.tree.scrollTo(index)
            self.tree.blockSignals(False)
            # Гарантируем полную обработку выбора и переключение UI
            self._handle_item_selection(index)
            # И явное восстановление фокуса на дереве (после обновления модели/выделения)
            try:
                schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
            except Exception:
                try:
                    self.tree.setFocus()
                except Exception:
                    pass
