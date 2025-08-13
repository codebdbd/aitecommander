# app/controllers/structure/item_operations.py

from PyQt6.QtCore import Qt  # Импорт Qt из QtCore

from app.controllers.domain.structure.commands import (
    DeleteCategoryCommand,
    DeleteSectionCommand,
    SaveCategoryCommand,
    SaveSectionCommand,
)

# Используем строковые литералы "section" и "category"
from app.utils.ui.dialog_manager import DialogManager
from app.utils.ui.qt.roles import get_tree_tuple
from app.views.dialogs.entity_dialogs import CategoryDialog, SectionDialog


class ItemOperations:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
        self.main = controller.main
        self.undo_stack = controller.undo_stack
    
    def load(self, item_to_select=None) -> None:
        # При загрузке структуры tree_management автоматически сохранит и восстановит выделение
        # если item_to_select не указан, иначе будет восстановлено указанное выделение
        self.business.load_structure()
        if item_to_select:
            from app.utils.system.task_scheduler import schedule_selection_restore
            item_type, item_id = item_to_select
            # Восстанавливаем выделение после загрузки с небольшой задержкой
            schedule_selection_restore(
                lambda: self.controller.selection_handler._restore_selection_after_load(item_type, item_id),
                f"{item_type}_{item_id}"
            )
    
    def switch_sphere(self, sphere_id: int) -> None:
        """Переключает сферу с использованием асинхронной загрузки структуры."""
        self.business.set_current_sphere(sphere_id)
        # Используем асинхронную версию для предотвращения блокировки UI
        self.business.load_structure_async()
    
    def add_new_section(self) -> None:
        try:
            dlg = SectionDialog(self.business, default_sphere_id=self.business.current_sphere_id, parent=self.main)
            if dlg.exec() == dlg.DialogCode.Accepted:
                data = dlg.get_result()
                cmd = SaveSectionCommand(data, self.main)
                if cmd:
                    self.undo_stack.push(cmd)
        except Exception as e:
            DialogManager.show_error(
                self.main,
                "Ошибка добавления раздела",
                "Не удалось добавить раздел.",
                informative_text="Проверьте корректность введённых данных и повторите попытку.",
                details=str(e),
            )
    
    def add_new_category(self) -> None:
        target_section_id = self._get_selected_section_id()
        if target_section_id is None:
            target_section_id = self.business.get_target_section_id()
            if target_section_id is None:
                if self._offer_create_section():
                    self.add_new_section()
                return
        try:
            dlg = CategoryDialog(self.business, parent=self.main)
            dlg.set_result({"section_id": target_section_id})
            if dlg.exec() == dlg.DialogCode.Accepted:
                data = dlg.get_result()
                cmd = SaveCategoryCommand(data, self.main)
                if cmd:
                    self.undo_stack.push(cmd)
        except Exception as e:
            DialogManager.show_error(
                self.main,
                "Ошибка добавления категории",
                "Не удалось добавить категорию.",
                informative_text="Проверьте корректность введённых данных и повторите попытку.",
                details=str(e),
            )
    
    def _offer_create_section(self) -> bool:
        return DialogManager.ask_confirmation(
            self.main,
            "В текущей сфере нет разделов. Создать новый раздел?",
            "Нет разделов",
            informative_text="Будет открыт диалог создания раздела.",
        )
    
    def edit_item(self, item) -> None:
        if not item:
            return
        t = get_tree_tuple(item, 0)
        if not t:
            return
        typ, id_ = t
        if typ == "section":
            self._edit_section(id_)
        elif typ == "category":
            self._edit_category(id_)
    
    def edit_selected_item(self) -> None:
        current_item = self.tree.currentItem()
        if current_item:
            self.edit_item(current_item)
    
    def delete_item(self, item) -> None:
        if not item:
            return
        t = get_tree_tuple(item, 0)
        if not t:
            return
        typ, id_ = t
        if typ == "section":
            self._delete_section(id_)
        elif typ == "category":
            self._delete_category(id_)
    
    def delete_selected_item(self) -> None:
        current_item = self.tree.currentItem()
        if current_item:
            self.delete_item(current_item)
    
    def _edit_section(self, section_id: int) -> None:
        try:
            old_data = self.business.get_section_data(section_id)
            if not old_data:
                return
            dlg = SectionDialog(self.business, section_id=section_id, parent=self.main)
            if dlg.exec() == dlg.DialogCode.Accepted:
                new_data = dlg.get_result()
                new_data['id'] = section_id
                cmd = SaveSectionCommand(new_data, self.main, old_data=old_data)
                if cmd:
                    self.undo_stack.push(cmd)
        except Exception as e:
            DialogManager.show_error(
                self.main,
                "Ошибка редактирования раздела",
                "Не удалось редактировать раздел.",
                informative_text="Попробуйте ещё раз или обратитесь в поддержку.",
                details=str(e),
            )
    
    def _edit_category(self, category_id: int) -> None:
        try:
            old_data = self.business.get_category_data(category_id)
            if not old_data:
                return
            dlg = CategoryDialog(self.business, category_id=category_id, parent=self.main)
            if dlg.exec() == dlg.DialogCode.Accepted:
                new_data = dlg.get_result()
                new_data['id'] = category_id
                if 'position' not in new_data and 'position' in old_data:
                    new_data['position'] = old_data['position']
                if self.business.update_category(category_id, new_data):
                    self.controller.tree_manager._update_category_display(category_id, new_data)
                    cmd = SaveCategoryCommand(new_data, self.main, old_data=old_data, skip_reload=True)
                    if cmd:
                        self.undo_stack.push(cmd)
        except Exception as e:
            DialogManager.show_error(
                self.main,
                "Ошибка редактирования категории",
                "Не удалось редактировать категорию.",
                informative_text="Попробуйте ещё раз или обратитесь в поддержку.",
                details=str(e),
            )
    
    def _delete_section(self, section_id: int) -> None:
        success, section_data, cats_count, links_count = self.business.delete_section(section_id)
        if not success:
            return
        if self._confirm_section_deletion(section_data, cats_count, links_count):
            cmd = DeleteSectionCommand(section_data, self.main)
            if cmd:
                self.undo_stack.push(cmd)
    
    def _delete_category(self, category_id: int) -> None:
        success, category_data, links_count = self.business.delete_category(category_id)
        if not success:
            return
        if self._confirm_category_deletion(category_data, links_count):
            cmd = DeleteCategoryCommand(category_data, self.main)
            if cmd:
                self.undo_stack.push(cmd)
    
    def _confirm_section_deletion(self, section_data: dict, cats_count: int, links_count: int) -> bool:
        section_name = section_data.get('name', 'неизвестный раздел')
        msg = f"Раздел '{section_name}' содержит {cats_count} категори{'ю' if cats_count==1 else 'и'} и {links_count} ссыл{'ку' if links_count==1 else 'ок'}.\n\n"
        msg += "Все вложенные категории и ссылки будут удалены безвозвратно!\n\nВы уверены, что хотите продолжить?"
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            "Удалить раздел",
            informative_text="Действие необратимо. Будут удалены все вложенные категории и ссылки.",
            details=f"section_id={section_data.get('id')}, cats={cats_count}, links={links_count}",
        )
    
    def _confirm_category_deletion(self, category_data: dict, links_count: int) -> bool:
        category_name = category_data.get('name', 'неизвестная категория')
        msg = f"Категория '{category_name}' содержит {links_count} ссыл{'ку' if links_count==1 else 'ок'}.\n\n"
        msg += "Все вложенные ссылки будут удалены безвозвратно!\n\nВы уверены, что хотите продолжить?"
        return DialogManager.ask_confirmation(
            self.main,
            msg,
            "Подтвердите удаление",
            informative_text="Действие необратимо. Все ссылки в категории будут удалены.",
            details=f"category_id={category_data.get('id')}, links={links_count}",
        )
    
    def handle_edit_category(self, category_id: int) -> None:
        item = self.controller.tree_manager._find_item_by_id("category", category_id)
        if item:
            self.edit_item(item)
    
    def handle_delete_category(self, category_id: int) -> None:
        item = self.controller.tree_manager._find_item_by_id("category", category_id)
        if item:
            self.delete_item(item)
    
    def _get_selected_section_id(self) -> int:
        current_item = self.tree.currentItem()
        if not current_item:
            return None
        t = get_tree_tuple(current_item, 0)
        if not t:
            return None
        typ, id_ = t
        if typ == "section":
            return id_
        if typ == "category":
            parent_item = current_item.parent()
            if parent_item:
                pt = get_tree_tuple(parent_item, 0)
                if not pt:
                    return None
                parent_typ, parent_id = pt
                if parent_typ == "section":
                    return parent_id
        return None