from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QAbstractItemView, QMessageBox
)
from app.models.db import Database
from app.views.dialogs import SectionDialog, CategoryDialog


class StructureController:
    def __init__(self, tree_widget: QTreeWidget, db: Database, main_window):
        self.tree = tree_widget
        self.db = db
        self.main = main_window

        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_single_click)

      

    def populate_tree(self):
        self.tree.clear()
        sid = self.main.current_sphere_id
        if sid is None:
            return

        for section in self.db.get_sections(sid):
            sec_item = QTreeWidgetItem([section["name"]])
            sec_item.setData(0, Qt.ItemDataRole.UserRole, ("section", section["id"]))
            self.tree.addTopLevelItem(sec_item)
            for category in self.db.get_categories(section["id"]):
                cat_item = QTreeWidgetItem([category["name"]])
                cat_item.setData(0, Qt.ItemDataRole.UserRole, ("category", category["id"]))
                sec_item.addChild(cat_item)
            sec_item.setExpanded(True)

    def _on_single_click(self, item: QTreeWidgetItem, _col: int):
        typ, id_ = item.data(0, Qt.ItemDataRole.UserRole)
        if typ == "section":
            self.main.load_section(id_)
        elif typ == "category":
            self.main.load_category(id_)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self.tree)
        if item:
            typ, id_ = item.data(0, Qt.ItemDataRole.UserRole)
            if typ == "section":
                menu.addAction("Редактировать раздел", lambda: self._edit_section(id_))
                menu.addAction("Добавить категорию", lambda: self._add_category(parent_section=id_))
                menu.addSeparator()
                menu.addAction("Удалить раздел", lambda: self._delete_section(id_))
            elif typ == "category":
                menu.addAction("Редактировать категорию", lambda: self._edit_category(id_))
                menu.addAction("Добавить ссылку", lambda: self.main.show_link_dialog(category_id=id_))
                menu.addSeparator()
                menu.addAction("Удалить категорию", lambda: self._delete_category(id_))
        else:
            menu.addAction("Добавить раздел", self._add_section)
            menu.addSeparator()
            menu.addAction("Сортировать дерево", self._sort_tree)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _add_section(self):
        dlg = SectionDialog(self.db, default_sphere_id=self.main.current_sphere_id, parent=self.main)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                data.setdefault("icon_path", "section.ico")
                self.db.insert_section(data)
                self.main.switch_sphere(self.main.current_sphere_id)

    def _edit_section(self, section_id: int):
        dlg = SectionDialog(self.db, section_id=section_id, parent=self.main)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.db.update_section(section_id, data)
                self.main.switch_sphere(self.main.current_sphere_id)

    def _delete_section(self, section_id: int):
        reply = QMessageBox.question(
            self.tree, "Удалить раздел",
            "Удалить этот раздел и все его категории?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_section(section_id)
            self.main.switch_sphere(self.main.current_sphere_id)

    def _add_category(self, parent_section: int):
        dlg = CategoryDialog(self.db, parent=self.main)
        dlg.set_result({"section_id": parent_section})
        if dlg.exec():
            data = dlg.get_result()
            if data:
                data.setdefault("icon_path", "category.ico")
                self.db.insert_category(data)
                self.main.switch_sphere(self.main.current_sphere_id)

    def _edit_category(self, category_id: int):
        dlg = CategoryDialog(self.db, category_id=category_id, parent=self.main)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                self.db.update_category(category_id, data)
                self.main.switch_sphere(self.main.current_sphere_id)

    def _delete_category(self, category_id: int):
        reply = QMessageBox.question(
            self.tree, "Удалить категорию",
            "Удалить эту категорию и все её ссылки?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_category(category_id)
            self.main.switch_sphere(self.main.current_sphere_id)

    def _sort_tree(self):
        def sort_item(parent: QTreeWidgetItem):
            children = [parent.child(i) for i in range(parent.childCount())]
            children.sort(key=lambda x: x.text(0).lower())
            parent.takeChildren()
            for child in children:
                parent.addChild(child)
                sort_item(child)

        for i in range(self.tree.topLevelItemCount()):
            sort_item(self.tree.topLevelItem(i))
