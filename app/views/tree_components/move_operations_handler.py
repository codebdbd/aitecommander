# app/views/tree_components/move_operations_handler.py

"""Обработчик операций перемещения для StructureTreeWidget."""

import logging
from typing import Any, Dict, List

from PyQt6.QtWidgets import QMessageBox

from app.utils.ui.dnd.base import TreeHandlerBase
from app.utils.ui.dnd.commands import MoveCategoryCommand, MoveLinksCommand
from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)


class MoveOperationsHandler(TreeHandlerBase):
    """Обработчик операций перемещения элементов в дереве структуры."""

    def _show_message(
        self,
        kind: str,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        msg = QMessageBox(self.tree_widget)
        if kind == "info":
            msg.setIcon(QMessageBox.Icon.Information)
        elif kind == "warning":
            msg.setIcon(QMessageBox.Icon.Warning)
        else:
            msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(title)
        msg.setText(text)
        if informative_text:
            msg.setInformativeText(informative_text)
        if details:
            msg.setDetailedText(details)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        # silent зарезервирован для единообразия с BaseDialog; здесь поведение одинаковое
        msg.exec()

    def _show_info(
        self,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        self._show_message("info", text, title, informative_text, details, silent)

    def _show_warning(
        self,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        self._show_message("warning", text, title, informative_text, details, silent)

    def _show_error(
        self,
        text: str,
        title: str,
        informative_text: str | None = None,
        details: str | None = None,
        silent: bool = False,
    ) -> None:
        self._show_message("error", text, title, informative_text, details, silent)

    def execute_move_category_command(self, category_id: int, target_id: int) -> None:
        """Выполняет команду перемещения категории."""
        main_win = self.tree_widget.window()

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveCategoryCommand(category_id, target_id, main_win)
            )
            logger.info(
                f"Выполнена команда перемещения категории {category_id} в {target_id}"
            )
        else:
            self._show_warning(
                "История действий недоступна. Перемещение отменено.",
                "Недоступна история действий",
                informative_text="Включите поддержку undo/redo или инициализируйте undo_stack в главном окне.",
            )
            logger.warning("Undo stack не найден для перемещения категории")

    def execute_move_links_command(
        self, link_ids: List[int], new_category_id: int
    ) -> None:
        """Выполняет команду перемещения ссылок."""
        main_win = self.tree_widget.window()

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveLinksCommand(link_ids, new_category_id, main_win)
            )
            logger.info(
                f"Выполнена команда перемещения ссылок {link_ids} в категорию {new_category_id}"
            )
        else:
            logger.warning("Undo stack не найден для перемещения ссылок")

    def handle_internal_move(self, source_item) -> None:
        """Обработка внутреннего перемещения элементов."""
        if not source_item:
            return

        stuple = get_tree_tuple(source_item, 0)
        if not stuple:
            return
        source_type, source_id = stuple
        if source_type not in ("section", "category") or not isinstance(source_id, int):
            return
        parent = source_item.parent()
        main_win = self.tree_widget.window()

        # Если это категория между разделами — используем команду
        if source_type == "category" and parent:
            self._handle_category_section_move(source_id, parent, main_win)
            return

        # Для сортировки внутри раздела или для разделов
        self._handle_position_update(source_type, source_id, parent)

    def handle_category_section_move(self, source_id: int, parent, main_win) -> None:
        """Обработка перемещения категории между разделами."""
        pdata = get_tree_tuple(parent, 0)
        if not (isinstance(source_id, int)):
            logger.warning("Некорректный тип source_id для перемещения категории")
            return
        if not pdata:
            logger.warning(
                "Некорректные данные целевого родителя для перемещения категории"
            )
            return
        parent_type, parent_id = pdata
        if parent_type != "section" or not isinstance(parent_id, int):
            logger.warning(
                "Некорректные данные целевого родителя для перемещения категории"
            )
            return
        new_section_id = parent_id

        if hasattr(main_win, "undo_stack"):
            main_win.undo_stack.push(
                MoveCategoryCommand(source_id, new_section_id, main_win)
            )
            logger.info(f"Перемещена категория {source_id} в раздел {new_section_id}")
        else:
            self._show_warning(
                "История действий недоступна. Перемещение между разделами отменено.",
                "Недоступна история действий",
                informative_text="Включите поддержку undo/redo или инициализируйте undo_stack в главном окне.",
            )
            logger.warning(
                "Undo stack не найден для перемещения категории между разделами"
            )

    def _handle_category_section_move(self, source_id: int, parent, main_win) -> None:
        """Внутренний метод для обработки перемещения категории между разделами."""
        self.handle_category_section_move(source_id, parent, main_win)

    def _handle_position_update(self, source_type: str, source_id: int, parent) -> None:
        """Обработка обновления позиций элементов."""
        params = self._prepare_position_params(source_type, source_id, parent)
        if not params:
            return

        def internal_move_task():
            main_window = self.tree_widget.window()
            if not (
                hasattr(main_window, "structure_business")
                and main_window.structure_business
            ):
                raise Exception("Бизнес-логика структуры недоступна")

            success = main_window.structure_business.update_item_positions(
                params["table_name"], params["ids_in_order"]
            )
            if not success:
                raise Exception("Ошибка обновления позиций через бизнес-логику")

        self.tree_widget.run_async(
            internal_move_task,
            on_success=self._on_internal_move_finished,
            on_error=self._on_db_error,
        )

    def _prepare_position_params(
        self, source_type: str, source_id: int, parent
    ) -> Dict[str, Any]:
        """Подготавливает параметры для обновления позиций."""
        if source_type == "section":
            ids_in_order: list[int] = []
            for i in range(self.tree_widget.topLevelItemCount()):
                item = self.tree_widget.topLevelItem(i)
                t = get_tree_tuple(item, 0)
                if t:
                    typ, id_ = t
                    if typ == "section" and isinstance(id_, int):
                        ids_in_order.append(id_)
            if not ids_in_order:
                return {}
            return {"table_name": "section", "ids_in_order": ids_in_order}
        elif source_type == "category" and parent:
            ids_in_order: list[int] = []
            for i in range(parent.childCount()):
                item = parent.child(i)
                t = get_tree_tuple(item, 0)
                if t:
                    typ, id_ = t
                    if typ == "category" and isinstance(id_, int):
                        ids_in_order.append(id_)
            if not ids_in_order:
                return {}
            return {"table_name": "category", "ids_in_order": ids_in_order}
        return {}

    def _on_internal_move_finished(self, result=None) -> None:
        """Обработчик успешного завершения внутреннего перемещения."""
        logger.info("Async internal move finished successfully.")

        if result == "duplicate":
            self._show_info(
                "Такая категория уже существует в выбранном разделе.",
                "Дубликат категории",
                informative_text="Переименуйте категорию или выберите другой раздел.",
            )
            return

        self._refresh_ui_after_move()

    def _on_db_error(self, error) -> None:
        """Обработчик ошибок базы данных."""
        logger.error(f"Database operation failed in MoveOperationsHandler: {error}")
        self._show_error(
            "Не удалось обновить позиции элементов.",
            "Ошибка базы данных при перемещении",
            informative_text="Изменения позиций не были сохранены.",
            details=str(error),
        )

        # Обновляем интерфейс после ошибки
        self._refresh_ui_after_move()

    def _refresh_ui_after_move(self) -> None:
        """Обновляет интерфейс после перемещения."""
        main_win = self.tree_widget.window()

        # Переключаемся на текущую сферу для обновления
        if (
            hasattr(main_win, "structure_business")
            and main_win.structure_business.current_sphere_id
        ):
            main_win._switch_sphere(main_win.structure_business.current_sphere_id)

        # Обновляем дерево структуры
        if hasattr(main_win, "structure"):
            main_win.structure.load()

        # Дополнительно: принудительно обновим плитки категорий, переустановив текущий раздел
        try:
            tw = self.tree_widget
            current = tw.currentItem() if hasattr(tw, "currentItem") else None
            section_id = None
            if current:
                t = get_tree_tuple(current, 0)
                if t:
                    typ, id_ = t
                    if typ == "section" and isinstance(id_, int):
                        section_id = id_
                    elif typ == "category":
                        parent = current.parent()
                        if parent:
                            pt = get_tree_tuple(parent, 0)
                            if pt and pt[0] == "section" and isinstance(pt[1], int):
                                section_id = pt[1]
            if (
                section_id
                and hasattr(main_win, "structure_business")
                and main_win.structure_business
            ):
                # Это приведет к загрузке актуальных категорий и вызову switch_to_category_tiles()
                main_win.structure_business.select_section(section_id)
        except Exception:
            # Не прерываем UI-поток из-за вспомогательного обновления плиток
            pass
