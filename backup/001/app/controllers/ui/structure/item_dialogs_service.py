from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject

from app.controllers.ui.dialogs import DialogManager
from app.controllers.ui.undo.commands_structure import SaveCategoryCmd, SaveSectionCmd
from app.utils.ui.qt.roles import get_tree_tuple
from app.views.windows.dialogs.entity_dialogs import CategoryDialog, SectionDialog

logger = logging.getLogger(__name__)


class ItemDialogService(QObject):
    """Инкапсулирует логику создания и редактирования разделов и категорий."""

    def __init__(self, *, controller, tree, business, main_window, undo_stack):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self._controller = controller
        self._tree = tree
        self._business = business
        self._main = main_window
        self._undo_stack = undo_stack

    def add_new_section(self) -> None:
        try:
            dlg = SectionDialog(
                self._business,
                default_sphere_id=self._business.current_sphere_id,
                parent=self._main,
            )
            if dlg.exec() == dlg.DialogCode.Accepted:
                data = dlg.get_result()
                cmd = SaveSectionCmd(new_data=data, old_data=None, main_window=self._main)
                if cmd:
                    self._undo_stack.push(cmd)
        except Exception as exc:  # pragma: no cover - UI protection
            logger.exception("Ошибка добавления раздела")
            DialogManager.show_error(
                self._main,
                "Ошибка добавления раздела",
                "Не удалось добавить раздел.",
                informative_text="Проверьте корректность введённых данных и повторите попытку.",
                details=str(exc),
            )

    def add_new_category(self, target_section_id: Optional[int]) -> None:
        if target_section_id is None:
            return
        try:
            dlg = CategoryDialog(self._business, parent=self._main)
            dlg.set_result({"section_id": target_section_id})
            if dlg.exec() == dlg.DialogCode.Accepted:
                data = dlg.get_result()
                cmd = SaveCategoryCmd(new_data=data, old_data=None, main_window=self._main)
                if cmd:
                    self._undo_stack.push(cmd)
        except Exception as exc:  # pragma: no cover - UI protection
            logger.exception("Ошибка добавления категории")
            DialogManager.show_error(
                self._main,
                "Ошибка добавления категории",
                "Не удалось добавить категорию.",
                informative_text="Проверьте корректность введённых данных и повторите попытку.",
                details=str(exc),
            )

    def edit_item(self, item) -> None:
        if not item:
            return
        meta = get_tree_tuple(item, 0)
        if not meta:
            return
        item_type, item_id = meta
        if item_type == "section":
            self._edit_section(item_id)
        elif item_type == "category":
            self._edit_category(item_id)

    def edit_selected_item(self) -> None:
        try:
            current = self._tree.currentIndex() if hasattr(self._tree, "currentIndex") else None
            if current and current.isValid():
                self.edit_item(current)
        except (AttributeError, RuntimeError) as exc:
            logger.debug("[ItemDialogService.edit_selected_item] currentIndex failed: %s", exc)

    def handle_edit_category(self, category_id: int) -> None:
        item = self._controller.tree_manager._find_item_by_id("category", category_id)
        if item:
            self.edit_item(item)

    def _offer_create_section(self) -> bool:
        return DialogManager.ask_confirmation(
            self._main,
            "В текущей сфере нет разделов. Создать новый раздел?",
            "Нет разделов",
            informative_text="Будет открыт диалог создания раздела.",
        )

    def ensure_section_for_category(self) -> Optional[int]:
        section_id = self._get_selected_section_id()
        if section_id is None:
            section_id = self._business.get_target_section_id()
            if section_id is None and self._offer_create_section():
                self.add_new_section()
                section_id = self._business.get_target_section_id()
        return section_id

    def get_selected_section_id(self) -> Optional[int]:
        return self._get_selected_section_id()

    def _edit_section(self, section_id: int) -> None:
        try:
            old_data = self._business.get_section_data(section_id)
            if not old_data:
                return
            dlg = SectionDialog(self._business, section_id=section_id, parent=self._main)
            if dlg.exec() == dlg.DialogCode.Accepted:
                new_data = dlg.get_result()
                new_data["id"] = section_id
                cmd = SaveSectionCmd(new_data=new_data, old_data=old_data, main_window=self._main)
                if cmd:
                    self._undo_stack.push(cmd)
        except Exception as exc:  # pragma: no cover - UI protection
            logger.exception("Ошибка редактирования раздела")
            DialogManager.show_error(
                self._main,
                "Ошибка редактирования раздела",
                "Не удалось редактировать раздел.",
                informative_text="Попробуйте ещё раз или обратитесь в поддержку.",
                details=str(exc),
            )

    def _edit_category(self, category_id: int) -> None:
        try:
            old_data = self._business.get_category_data(category_id)
            if not old_data:
                return
            dlg = CategoryDialog(self._business, category_id=category_id, parent=self._main)
            if dlg.exec() == dlg.DialogCode.Accepted:
                new_data = dlg.get_result()
                new_data["id"] = category_id
                if "position" not in new_data and "position" in old_data:
                    new_data["position"] = old_data["position"]
                cmd = SaveCategoryCmd(
                    new_data=new_data,
                    old_data=old_data,
                    main_window=self._main,
                    skip_reload=False,
                )
                if cmd:
                    self._undo_stack.push(cmd)
        except Exception as exc:  # pragma: no cover - UI protection
            logger.exception("Ошибка редактирования категории")
            DialogManager.show_error(
                self._main,
                "Ошибка редактирования категории",
                "Не удалось редактировать категорию.",
                informative_text="Попробуйте ещё раз или обратитесь в поддержку.",
                details=str(exc),
            )

    def _get_selected_section_id(self) -> Optional[int]:
        try:
            current = self._tree.currentIndex() if hasattr(self._tree, "currentIndex") else None
            if current and current.isValid():
                meta = get_tree_tuple(current, 0)
                if not meta:
                    return None
                item_type, item_id = meta
                if item_type == "section":
                    return item_id
                if item_type == "category":
                    parent = current.parent()
                    if parent and parent.isValid():
                        parent_meta = get_tree_tuple(parent, 0)
                        if parent_meta and parent_meta[0] == "section":
                            return parent_meta[1]
        except (AttributeError, RuntimeError) as exc:
            logger.debug("[ItemDialogService.get_selected_section_id] failed: %s", exc)
        return None
