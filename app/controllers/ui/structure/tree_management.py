# app/controllers/structure/tree_management.py

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidgetItem, QTreeWidgetItemIterator

from app.utils.ui.icon.icon_operations.creators import themed_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.qt.roles import get_tree_tuple
from app.utils.system.task_scheduler import schedule_selection_restore


class TreeManagement:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.icon_handler = controller.icon_handler
    
    def _on_structure_loaded(self, sections_data: list) -> None:
        # Сохраняем текущее выделение перед очисткой дерева
        current_item = self.tree.currentItem()
        current_selection = None
        if current_item:
            current_selection = get_tree_tuple(current_item, 0)
        
        expanded_state = self._save_expanded_state()
        self.tree.clear()
        for section_data in sections_data:
            self._create_section_item(section_data)
        self._restore_expanded_state(expanded_state)
        
        # Восстанавливаем выделение, если оно существовало
        if current_selection:
            item_type, item_id = current_selection
            if item_type in ("section", "category") and isinstance(item_id, int):
                self.controller.selection_handler._restore_selection_after_load(item_type, item_id)
        else:
            self.controller.selection_handler._select_first_item_if_needed()
        
        # После первой загрузки структуры обновляем отображение главного окна
        if hasattr(self.controller, 'main') and getattr(self.controller.main, '_first_structure_load', False):
            self.controller.main._first_structure_load = False
            # Принудительно обновляем layout
            self.tree.updateGeometry()
            self.tree.update()
    
    def _on_item_added(self, item_type: str, parent_id: int, data: dict) -> None:
        new_item = QTreeWidgetItem([data["name"]])
        new_item.setData(0, Qt.ItemDataRole.UserRole, (item_type, data["id"]))
        self.icon_handler._set_tree_item_icon(new_item, item_type, data)
        
        if item_type == "section":
            self.tree.addTopLevelItem(new_item)
            new_item.setExpanded(True)
        elif item_type == "category":
            parent_item = self._find_item_by_id("section", parent_id)
            if parent_item:
                parent_item.addChild(new_item)
                parent_item.setExpanded(True)
        
        item_id = data["id"]
        schedule_selection_restore(
            lambda: self.controller.selection_handler._set_focus_on_new_item_by_id(item_type, item_id),
            f"new_{item_type}_{item_id}"
        )
    
    def _on_item_updated(self, item_type: str, item_id: int, data: dict) -> None:
        item = self._find_item_by_id(item_type, item_id)
        if item:
            item.setText(0, data["name"])
            self.icon_handler._set_tree_item_icon(item, item_type, data)
            
            # Обновляем плитки категорий если обновилась категория
            if item_type == "category":
                self._update_category_tiles_after_edit(item)
            # Обновляем плитки категорий если обновился раздел (название раздела могло измениться)
            elif item_type == "section":
                self._update_section_tiles_after_edit(item)
    
    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        item = self._find_item_by_id(item_type, item_id)
        if item:
            # Сохраняем информацию для восстановления фокуса
            parent = item.parent()
            next_item = None
            
            if parent:
                # Для категории: выбираем родительский раздел
                if item_type == "category":
                    next_item = parent
                parent.removeChild(item)
            else:
                # Для элементов верхнего уровня
                index = self.tree.indexOfTopLevelItem(item)
                if index >= 0:
                    # Пытаемся взять следующий или предыдущий элемент
                    if index < self.tree.topLevelItemCount() - 1:
                        next_item = self.tree.topLevelItem(index + 1)
                    elif index > 0:
                        next_item = self.tree.topLevelItem(index - 1)
                    
                    self.tree.takeTopLevelItem(index)
            
            # Восстанавливаем фокус на выбранном элементе
            if next_item:
                self.tree.setCurrentItem(next_item)
                self.tree.setFocus()
                # Принудительно вызываем обработчик выбора для обновления плиток
                if hasattr(self.controller, 'selection_handler') and self.controller.selection_handler:
                    self.controller.selection_handler._handle_item_selection(next_item)
    
    def _find_item_by_id(self, item_type: str, item_id: int) -> QTreeWidgetItem:
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            data = get_tree_tuple(item, 0)
            if data:
                typ, id_ = data
                if typ == item_type and id_ == item_id:
                    return item
            iterator += 1
        return None
    
    def _save_expanded_state(self) -> dict:
        expanded_state = {}
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() > 0:
                item_key = get_tree_tuple(item, 0)
                if item_key:
                    expanded_state[item_key] = item.isExpanded()
            iterator += 1
        return expanded_state
    
    def _restore_expanded_state(self, expanded_state: dict) -> None:
        if not expanded_state:
            return
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() > 0:
                item_key = get_tree_tuple(item, 0)
                if item_key and item_key in expanded_state:
                    item.setExpanded(expanded_state[item_key])
            iterator += 1
    
    def _create_section_item(self, sec_data: dict) -> None:
        sec_item = QTreeWidgetItem([sec_data["name"]])
        sec_item.setData(0, Qt.ItemDataRole.UserRole, ("section", sec_data["id"]))
        self.icon_handler._set_tree_item_icon(sec_item, "section", sec_data)
        self.tree.addTopLevelItem(sec_item)
        for cat_data in sec_data.get('categories', []):
            self._create_category_item(cat_data, sec_item)
    
    def _create_category_item(self, cat_data: dict, parent_item: QTreeWidgetItem) -> None:
        cat_item = QTreeWidgetItem([cat_data["name"]])
        cat_item.setData(0, Qt.ItemDataRole.UserRole, ("category", cat_data["id"]))
        self.icon_handler._set_tree_item_icon(cat_item, "category", cat_data)
        parent_item.addChild(cat_item)
    
    def _sort_tree(self, reverse_sort: bool = False) -> None:
        def sort_item(parent: QTreeWidgetItem, reverse: bool = False) -> None:
            if not parent:
                return
            children = [parent.child(i) for i in range(parent.childCount())]
            children.sort(key=lambda x: x.text(0).lower() if x else '', reverse=reverse)
            parent.takeChildren()
            for child in children:
                if child:
                    parent.addChild(child)
                    sort_item(child, reverse)
        
        for i in range(self.tree.topLevelItemCount()):
            root_item = self.tree.topLevelItem(i)
            if root_item:
                sort_item(root_item, reverse_sort)
    
    def on_structure_item_changed(self, item_type: str, item_id: int, data: dict) -> None:
        self._on_item_updated(item_type, item_id, data)
    
    def on_structure_item_added(self, item_type: str, parent_id: int, data: dict) -> None:
        self._on_item_added(item_type, parent_id, data)
    
    def _update_category_display(self, category_id: int, new_data: dict) -> None:
        """Обновляет отображение категории в дереве."""
        item = self._find_item_by_id("category", category_id)
        if item:
            # Обновляем текст элемента
            item.setText(0, new_data.get('name', ''))
            
            # Обновляем иконку если она изменилась
            if 'icon' in new_data:
                icon_path = new_data['icon']
                if icon_path:
                    theme = get_current_theme()
                    icon = themed_icon(icon_path, theme, 'tree_management')
                    item.setIcon(0, icon)
            
            # Обновляем плитки категорий если они открыты
            if hasattr(self.controller.main, 'tiles'):
                # Перезагружаем плитки для текущего раздела
                parent_item = item.parent()
                if parent_item:
                    st = get_tree_tuple(parent_item, 0)
                    if st and st[0] == "section":
                        section_id = st[1]
                        self.controller.business.select_section(section_id)
    
    def _update_category_tiles_after_edit(self, category_item) -> None:
        """Обновляет плитки категорий после редактирования категории."""
        # Находим родительский раздел
        parent_item = category_item.parent()
        if parent_item:
            st = get_tree_tuple(parent_item, 0)
            if st and st[0] == "section":
                section_id = st[1]
                # Принудительно обновляем плитки для текущего раздела
                if hasattr(self.controller.main, 'tiles'):
                    self.controller.business.select_section(section_id)
    
    def _update_section_tiles_after_edit(self, section_item) -> None:
        """Обновляет плитки категорий после редактирования раздела."""
        # Если текущий раздел выбран, обновляем его плитки
        current_item = self.tree.currentItem()
        if current_item == section_item:
            st = get_tree_tuple(section_item, 0)
            if st and st[0] == "section":
                section_id = st[1]
                # Принудительно обновляем плитки для текущего раздела
                if hasattr(self.controller.main, 'tiles'):
                    self.controller.business.select_section(section_id)