# app/controllers/structure/item_operations.py

import logging
from typing import Optional, Sequence

from PyQt6.QtCore import QObject, pyqtSlot

# Используем строковые литералы "section" и "category"
from app.controllers.ui.types import CategoryTilesControllerProtocol
from app.controllers.ui.structure.item_dialogs_service import ItemDialogService
from app.controllers.ui.structure.item_deletion_service import ItemDeletionService
from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)


class ItemOperations(QObject):
    def __init__(self, controller):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
        self.main = controller.main
        self.undo_stack = controller.undo_stack
        self._dialogs = ItemDialogService(
            controller=controller,
            tree=self.tree,
            business=self.business,
            main_window=self.main,
            undo_stack=self.undo_stack,
        )
        self._deleter = ItemDeletionService(
            controller=controller,
            tree=self.tree,
            business=self.business,
            main_window=self.main,
            undo_stack=self.undo_stack,
        )

    @pyqtSlot(object)
    def load(self, item_to_select=None) -> None:
        # При загрузке структуры tree_management автоматически сохранит и восстановит выделение
        # если item_to_select не указан, иначе будет восстановлено указанное выделение
        self.business.load_structure()
        if item_to_select:
            from app.controllers.ui.state.task_scheduler import (
                schedule_focus,
                schedule_selection_restore,
            )

            item_type, item_id = item_to_select
            # Восстанавливаем выделение после загрузки с небольшой задержкой
            schedule_selection_restore(
                lambda: self.controller.selection_handler._restore_selection_after_load(
                    item_type, item_id
                ),
                f"{item_type}_{item_id}",
            )
            # И дополнительно восстановим фокус на дереве
            try:
                schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
            except Exception as e:
                logger.debug("[ItemOperations.load] schedule_focus failed: %s", e)

    @pyqtSlot(int)
    def switch_sphere(self, sphere_id: int) -> None:
        """Переключает сферу и перезагружает структуру.

        Лучшие практики: только асинхронная загрузка через обработчик
        business.active_sphere_changed, без дублей и синхронных фолбэков.
        """
        # Не делаем ничего, если сфера не меняется (например, двойной клик по той же сфере)
        try:
            current = getattr(self.business, "current_sphere_id", None)
            if isinstance(current, int) and current == int(sphere_id):
                logger.debug(
                    "switch_sphere: same sphere %s selected again; skip clearing and reload",
                    sphere_id,
                )
                return
        except Exception:
            pass

        self.business.set_current_sphere(sphere_id)
        # Не очищаем модель сразу: ждём structure_loaded, чтобы избежать пустого дерева
        # и артефактов при двукратных кликах/быстром переключении.
        # Дальнейшая загрузка инициируется обработчиком business.on_active_sphere_changed,
        # который вызовет load_structure_async(). Здесь ничего дополнительно не делаем.
        return

    @pyqtSlot()
    def add_new_section(self) -> None:
        self._dialogs.add_new_section()

    @pyqtSlot()
    def add_new_category(self) -> None:
        target_section_id = self._dialogs.ensure_section_for_category()
        if target_section_id is None:
            return
        self._dialogs.add_new_category(target_section_id)

    def edit_item(self, item) -> None:
        self._dialogs.edit_item(item)

    @pyqtSlot()
    def edit_selected_item(self) -> None:
        self._dialogs.edit_selected_item()

    def delete_item(self, item) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.delete_item(item)

    @pyqtSlot()
    def delete_selected_item(self) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.delete_selected_item()

    def _is_delete_suppressed(self) -> bool:
        try:
            if hasattr(self.main, "_suppress_deletes") and getattr(
                self.main, "_suppress_deletes"
            ):
                logger.debug(
                    "[DeleteGuard] deletion suppressed by _suppress_deletes flag"
                )
                return True
        except Exception as exc:
            logger.debug(
                "[ItemOperations._is_delete_suppressed] flag check failed: %s", exc
            )
        return False

    def _confirm_section_deletion(
        self, section_data: dict, cats_count: int, links_count: int
    ) -> bool:
        section_name = section_data.get("name", "неизвестный раздел")
        msg = f"Раздел '{section_name}' содержит {cats_count} категори{'ю' if cats_count == 1 else 'и'} и {links_count} ссыл{'ку' if links_count == 1 else 'ок'}.\n\n"
        msg += "Все вложенные категории и ссылки будут удалены безвозвратно!\n\nВы уверены, что хотите продолжить?"
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            "Удалить раздел",
            informative_text="Действие необратимо. Будут удалены все вложенные категории и ссылки.",
            details=f"section_id={section_data.get('id')}, cats={cats_count}, links={links_count}",
        )

    def _confirm_category_deletion(self, category_data: dict, links_count: int) -> bool:
        category_name = category_data.get("name", "неизвестная категория")
        msg = f"Категория '{category_name}' содержит {links_count} ссыл{'ку' if links_count == 1 else 'ок'}.\n\n"
        msg += "Все вложенные ссылки будут удалены безвозвратно!\n\nВы уверены, что хотите продолжить?"
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            "Подтвердите удаление",
            informative_text="Действие необратимо. Все ссылки в категории будут удалены.",
            details=f"category_id={category_data.get('id')}, links={links_count}",
        )

    def handle_edit_category(self, category_id: int) -> None:
        self._dialogs.handle_edit_category(category_id)

    def handle_delete_category(self, category_id: int) -> None:
        if self._is_delete_suppressed():
            return
        self._deleter.handle_delete_category(category_id)

    def _has_any_items_in_tree(self) -> bool:
        """Возвращает True, если в дереве (QTreeView) есть хотя бы один элемент."""
        try:
            if hasattr(self.tree, "model"):
                model = self.tree.model()
                if model is not None and hasattr(model, "rowCount"):
                    return (model.rowCount() or 0) > 0
        except (AttributeError, RuntimeError) as e:
            logger.debug(
                "[ItemOperations._has_any_items_in_tree] model access failed: %s", e
            )
        return False
