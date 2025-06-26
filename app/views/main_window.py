# app/views/main_window.py

import sys
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QTreeWidgetItem,
    QTableWidget, QLineEdit, QToolButton, QPushButton,
    QScrollArea, QStackedLayout, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QStatusBar, QButtonGroup
)
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSize, QTimer

from app.controllers.structure import StructureController
from app.controllers.links import LinksController
from app.controllers.ui import FavoritesWidget, ThemeController
from app.settings import AppSettings
from app.models.db import Database
from app.views.category_tiles import CategoryTiles
from app.views.link_dialog import LinkDialog
from app.views.dialogs import SectionDialog, CategoryDialog
from app.config import UI_ICONS_DIR, LINK_ICONS_DIR
from app.views.custom_widgets import StructureTreeWidget, LinksTableWidget


class MainWindow(QMainWindow):
    def __init__(self, db: Database, settings: AppSettings, theme_ctrl: ThemeController):
        super().__init__()
        self.setWindowTitle("Link Manager")
        self.resize(1000, 600)

        self.db = db
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        self.current_sphere_id = None
        self.current_category_id = None

        menubar = self.menuBar()
        file_menu = menubar.addMenu("&Файл")
        file_menu.addAction("Импорт JSON...", self.import_json)
        file_menu.addAction("Экспорт JSON...", self.export_json)
        file_menu.addSeparator()
        file_menu.addAction("Настройки...", self.show_settings_dialog)
        file_menu.addSeparator()
        file_menu.addAction("Выход", self.close)

        edit_menu = menubar.addMenu("&Правка")
        edit_menu.addAction("Отменить", self.undo)
        edit_menu.addAction("Повторить", self.redo)

        view_menu = menubar.addMenu("&Вид")
        for name, disp in self.theme_ctrl.available():
            act = view_menu.addAction(disp)
            act.triggered.connect(lambda _, n=name: self.theme_ctrl.apply(n))

        help_menu = menubar.addMenu("&Справка")
        help_menu.addAction("О программе", self.show_about_dialog)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        self.fav_widget = FavoritesWidget(self, self.db)
        top_bar.addWidget(self.fav_widget)

        # Панель быстрых кнопок добавления ссылок разных типов
        quick_types = [
            ("web",       "web_icon.png",       "Веб-ссылка"),
            ("file",      "documents_icon.png", "Файл"),
            ("program",   "program_icon.png",   "Программа"),
            ("script",    "script_icon.png",    "Скрипт"),
            ("chromeapp", "chrome_icon.png",    "Chrome App"),
        ]
        for code, icon_name, tooltip in quick_types:
            btn = QToolButton()
            icon_path = UI_ICONS_DIR / icon_name
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
            btn.setToolTip(f"Добавить {tooltip}")
            btn.clicked.connect(lambda _, ct=code: self.quick_add_link(ct))
            top_bar.addWidget(btn)

        top_bar.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск… (Ctrl+F)")
        self.search.textChanged.connect(self.on_search)
        top_bar.addWidget(self.search)

        main_layout.addLayout(top_bar)

        mid = QHBoxLayout()

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.tree = StructureTreeWidget(self.db)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(24, 24))
        left_layout.addWidget(self.tree)

        self.spheres_bar = QWidget()
        s_layout = QHBoxLayout(self.spheres_bar)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(5)
        self.sphere_group = QButtonGroup(self)
        for sp in self.db.get_spheres():
            btn = QToolButton()
            btn.setCheckable(True)
            icon_path = UI_ICONS_DIR / (sp["icon_path"] or "")
            btn.setIcon(QIcon(str(icon_path)))
            btn.setIconSize(QSize(24, 24))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setToolTip(sp["name"])
            self.sphere_group.addButton(btn, sp["id"])
            btn.clicked.connect(lambda _, sid=sp["id"]: self.switch_sphere(sid))
            s_layout.addWidget(btn)
        left_layout.addWidget(self.spheres_bar)

        mid.addWidget(left_panel, 1)

        self.tiles = CategoryTiles(self)
        self.tiles_scroll = QScrollArea()
        self.tiles_scroll.setWidgetResizable(True)
        self.tiles_scroll.setWidget(self.tiles)
        # Use custom LinksTableWidget for drag support
        self.table = LinksTableWidget()

        self.stack = QStackedLayout()
        self.stack.addWidget(self.tiles_scroll)
        self.stack.addWidget(self.table)
        mid.addLayout(self.stack, 3)

        main_layout.addLayout(mid)

        self.structure = StructureController(self.tree, self.db, self)
        self.links = LinksController(self.table, self.db, self)

        bot = QHBoxLayout()
        actions = [
            ("Добавить раздел (F3)",     self.show_section_dialog),
            ("Добавить категорию (F4)", self.show_category_dialog),
            ("Добавить ссылку (F1)",    self.show_link_dialog),
            ("Редактировать (F2)",      self.edit_current),
            ("Удалить (Del)",           self.delete_current),
        ]
        for text, fn in actions:
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            bot.addWidget(btn)
        main_layout.addLayout(bot)

        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage("Готово")

        self._setup_shortcuts()

        timer = QTimer(self)
        timer.timeout.connect(self.db.backup)
        timer.start(self.settings.get_autosave_interval() * 60 * 1000)

        spheres = self.db.get_spheres()
        if spheres:
            self.switch_sphere(spheres[0]["id"])

    def switch_sphere(self, sphere_id: int):
        """Переключить сферу и автоматически выбрать первый раздел."""
        self.current_sphere_id = sphere_id
        # Отметить радиокнопку сферы
        for btn in self.sphere_group.buttons():
            btn.setChecked(self.sphere_group.id(btn) == sphere_id)

        self.tree.clear()
        first_section_item = None
        first_section_id = None

        for sec in self.db.get_sections(sphere_id):
            sec_item = QTreeWidgetItem([sec["name"]])
            sec_item.setData(0, Qt.ItemDataRole.UserRole, ("section", sec["id"]))
            sec_item.setSizeHint(0, QSize(0, 28))
            icon_name = sec["icon_path"] or "section.ico"
            icon_path = LINK_ICONS_DIR / icon_name if (LINK_ICONS_DIR / icon_name).exists() else UI_ICONS_DIR / icon_name
            sec_item.setIcon(0, QIcon(str(icon_path)))
            self.tree.addTopLevelItem(sec_item)

            # Запомнить первый раздел
            if first_section_item is None:
                first_section_item = sec_item
                first_section_id = sec["id"]

            for cat in self.db.get_categories(sec["id"]):
                cat_item = QTreeWidgetItem([cat["name"]])
                cat_item.setData(0, Qt.ItemDataRole.UserRole, ("category", cat["id"]))
                cat_item.setSizeHint(0, QSize(0, 28))
                icon_name = cat["icon_path"] or "category.ico"
                icon_path = LINK_ICONS_DIR / icon_name if (LINK_ICONS_DIR / icon_name).exists() else UI_ICONS_DIR / icon_name
                cat_item.setIcon(0, QIcon(str(icon_path)))
                sec_item.addChild(cat_item)
            sec_item.setExpanded(True)

        # Выбрать первый раздел по умолчанию
        if first_section_item is not None:
            self.tree.setCurrentItem(first_section_item)
            self.tree.setFocus()
            self.load_section(first_section_id)

    def on_search(self, text: str):
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 1).text().lower()
            notes = self.table.item(r, 3).text().lower()
            self.table.setRowHidden(r, text.lower() not in name and text.lower() not in notes)

    def show_section_dialog(self):
        dlg = SectionDialog(self.db, default_sphere_id=self.current_sphere_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_result()
            if data:
                if dlg.section_id:
                    self.db.update_section(dlg.section_id, data)
                else:
                    self.db.insert_section(data)
                self.switch_sphere(self.current_sphere_id)

    def show_category_dialog(self):
        """Открыть диалог категории для текущего или первого раздела текущей сферы."""
        # Определяем раздел, куда добавлять/редактировать
        target_section_id = None
        item = self.tree.currentItem()
        if item is not None:
            typ, id_ = item.data(0, Qt.ItemDataRole.UserRole)
            if typ == "section":
                target_section_id = id_
            elif typ == "category":
                parent = item.parent()
                if parent:
                    target_section_id = parent.data(0, Qt.ItemDataRole.UserRole)[1]

        if target_section_id is None:
            sections = self.db.get_sections(self.current_sphere_id)
            if sections:
                target_section_id = sections[0]["id"]
            else:
                # Нет разделов — предложить создать
                reply = QMessageBox.question(
                    self, "Нет разделов",
                    "В текущей сфере нет разделов. Создать новый раздел?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.show_section_dialog()
                return

        dlg = CategoryDialog(self.db, parent=self)
        dlg.set_result({"section_id": target_section_id})
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_result()
            if data:
                if dlg.category_id:
                    self.db.update_category(dlg.category_id, data)
                else:
                    self.db.insert_category(data)
                self.switch_sphere(self.current_sphere_id)

    def show_link_dialog(self, link=None, category_id=None):
        dlg = LinkDialog(
            self.db,
            link=link,
            category_id=category_id or self.current_category_id,
            parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_category(self.current_category_id)
            self.fav_widget.update_favorites()

    def edit_current(self):
        """Редактировать выбранный элемент (ссылку, категорию или раздел)."""
        # Сначала пробуем ссылку
        link = self.links.get_link_at(self.table.currentRow())
        if link:
            self.show_link_dialog(link=link)
            return

        item = self.tree.currentItem()
        if item is None:
            return
        typ, id_ = item.data(0, Qt.ItemDataRole.UserRole)
        if typ == "category":
            dlg = CategoryDialog(self.db, category_id=id_, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                data = dlg.get_result()
                if data:
                    self.db.update_category(id_, data)
                    self.switch_sphere(self.current_sphere_id)
        elif typ == "section":
            dlg = SectionDialog(self.db, section_id=id_, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                data = dlg.get_result()
                if data:
                    self.db.update_section(id_, data)
                    self.switch_sphere(self.current_sphere_id)

    def delete_current(self):
        """Удалить выбранный элемент (ссылка, категория или раздел) с подтверждением."""
        # Проверяем, выбрано ли несколько ссылок в таблице
        selected_rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()})
        if selected_rows:
            links = [self.links.get_link_at(r) for r in selected_rows]
            links = [ln for ln in links if ln]
            if links:
                msg = ("Удалить выбранную ссылку?" if len(links) == 1
                       else f"Удалить {len(links)} выбранных ссылок?")
                if QMessageBox.question(self, "Удалить ссылки", msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                    for ln in links:
                        self.db.delete_link(ln["id"])
                    self.load_category(self.current_category_id)
                    self.fav_widget.update_favorites()
                    return

        item = self.tree.currentItem()
        if item is None:
            return
        typ, id_ = item.data(0, Qt.ItemDataRole.UserRole)
        if typ == "category":
            if QMessageBox.question(self, "Удалить категорию", "Удалить эту категорию и все её ссылки?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.db.delete_category(id_)
                self.switch_sphere(self.current_sphere_id)
        elif typ == "section":
            if QMessageBox.question(self, "Удалить раздел", "Удалить этот раздел и все его категории?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.db.delete_section(id_)
                self.switch_sphere(self.current_sphere_id)

    def load_section(self, section_id: int):
        cats = self.db.get_categories(section_id)
        tiles = []
        for cat in cats:
            tiles.append({
                "id": cat["id"],
                "name": cat["name"],
                "icon_path": cat["icon_path"] if "icon_path" in cat.keys() else ""
            })
        self.tiles.set_categories(tiles)
        self.stack.setCurrentIndex(0)

    def load_category(self, category_id: int):
        self.links.load_links(category_id)
        self.stack.setCurrentIndex(1)
        self.current_category_id = category_id

    def _on_table_cell_double_clicked(self, row, column):
        # Открывать NoteDialog только если клик по колонке заметок (обычно 3)
        if column == 3:
            link = self.links.get_link_at(row)
            if link:
                from app.views.dialogs import NoteDialog
                dlg = NoteDialog(link, self.db, self)
                if dlg.exec() == dlg.Accepted:
                    # После сохранения обновить данные
                    self.load_category(self.current_category_id)

    def _setup_shortcuts(self):
        mappings = [
            ("F1",   self.show_link_dialog),
            ("F2",   self.edit_current),
            ("F3",   self.show_section_dialog),
            ("F4",   self.show_category_dialog),
            ("Del",  self.delete_current),
            ("Ctrl+X", self.links.cut_link),
            ("Ctrl+C", self.links.copy_link),
            ("Ctrl+V", self.links.paste_link),
            ("Ctrl+N", lambda: self.links.show_note_dialog(self.links.get_link_at(self.table.currentRow()))),
            ("Ctrl+A", lambda: self.table.selectAll()),
            ("Ctrl+F", self.search.setFocus),
            ("Escape", self.search.clear),
        ]
        for seq, fn in mappings:
            QShortcut(QKeySequence(seq), self).activated.connect(fn)

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт из JSON", "", "JSON Files (*.json)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # TODO: десериализация

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт в JSON", "", "JSON Files (*.json)")
        if not path:
            return
        data = []  # TODO: собрать структуру
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def undo(self):
        pass

    def redo(self):
        pass

    def show_settings_dialog(self):
        self.menuBar().actions()[0].menu().actions()[2].trigger()

    def show_about_dialog(self):
         QMessageBox.about(self, "О программе", "Link Manager\nВерсия 1.0\n© MyCompany")

    def quick_add_link(self, link_type: str):
        """Открыть диалог добавления ссылки с уже выбранным типом."""
        dlg = LinkDialog(self.db, category_id=self.current_category_id, parent=self)
        # Отметить нужную кнопку типа до показа окна
        for btn in dlg.type_group.buttons():
            if btn.property("link_type") == link_type:
                btn.setChecked(True)
                break
        # Явно вызвать обработку, чтобы UI обновился под тип
        dlg._on_type_changed(link_type)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Обновить текущую категорию и избранное после добавления
            if self.current_category_id is not None:
                self.load_category(self.current_category_id)
            self.fav_widget.update_favorites()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    settings = AppSettings()
    theme_ctrl = ThemeController(settings)
    theme_ctrl.apply(settings.get_theme())
    db = Database()
    win = MainWindow(db, settings, theme_ctrl)
    win.show()
    sys.exit(app.exec())
