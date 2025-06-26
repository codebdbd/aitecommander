import json
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QToolButton,
    QPushButton,
    QFileDialog,
    QDialogButtonBox,
    QMessageBox,
    QTextEdit,
    QSpinBox,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QWidget
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize, Qt, pyqtSignal, QObject, QRunnable, QThreadPool, pyqtSlot

from app.config import LINK_ICONS_DIR, UI_ICONS_DIR
from app.models.db import Database
from app.controllers.ui import ThemeController
from app.utils.chrome_profiles import find_chrome_profiles


class SectionDialog(QDialog):
    def __init__(self, db: Database, section_id: Optional[int] = None, default_sphere_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.section_id = section_id
        self.default_sphere_id = default_sphere_id
        self._result = None
        self._icon_filename = "section.ico"
        self.setWindowTitle("Редактировать раздел" if section_id else "Добавить раздел")
        self.resize(400, 150)
        self._init_ui()
        if section_id:
            self._load_section()

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sphere_cb = QComboBox()
        for s in self.db.get_spheres():
            self.sphere_cb.addItem(s["name"], s["id"])
        form.addRow("Сфера:", self.sphere_cb)
        # If a default sphere was provided (user invoked dialog from within a sphere), preselect it.
        if self.default_sphere_id is not None and self.section_id is None:
            idx = self.sphere_cb.findData(self.default_sphere_id)
            if idx >= 0:
                self.sphere_cb.setCurrentIndex(idx)

        self.name_le = QLineEdit()
        form.addRow("Название:", self.name_le)

        self.icon_btn = QToolButton()
        self.icon_btn.setIconSize(QSize(24, 24))
        self.icon_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.icon_btn.setIcon(QIcon(str(UI_ICONS_DIR / self._icon_filename)))
        form.addRow("Иконка:", self.icon_btn)
        self.icon_btn.clicked.connect(self._choose_icon)

        vbox.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _load_section(self):
        row = self.db.conn.execute(
            "SELECT name, sphere_id, icon_path FROM section WHERE id=?", (self.section_id,)
        ).fetchone()
        if row:
            self.name_le.setText(row["name"])
            idx = self.sphere_cb.findData(row["sphere_id"])
            if idx >= 0:
                self.sphere_cb.setCurrentIndex(idx)
            icon = row["icon_path"] or "section.ico"
            self._icon_filename = icon
            icon_path = (LINK_ICONS_DIR / icon) if Path(LINK_ICONS_DIR / icon).exists() else UI_ICONS_DIR / icon
            self.icon_btn.setIcon(QIcon(str(icon_path)))

    def _choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать иконку", "", "Изображения (*.png *.ico *.jpg *.svg)"
        )
        if path:
            fname = Path(path).name
            dest = LINK_ICONS_DIR / fname
            if not dest.exists():
                shutil.copy2(path, dest)
            self._icon_filename = fname
            self.icon_btn.setIcon(QIcon(str(dest)))

    def _on_accept(self):
        name = self.name_le.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Название не может быть пустым")
            return
        self._result = {
            "name": name,
            "sphere_id": self.sphere_cb.currentData(),
            "icon_path": self._icon_filename
        }
        self.accept()

    def get_result(self):
        return self._result


class CategoryDialog(QDialog):
    def __init__(self, db: Database, category_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.category_id = category_id
        self._result = None
        self._icon_filename = "category.ico"
        self.setWindowTitle("Редактировать категорию" if category_id else "Добавить категорию")
        self.resize(400, 200)
        self._init_ui()
        if category_id:
            self._load_category()

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.sphere_cb = QComboBox()
        for s in self.db.get_spheres():
            self.sphere_cb.addItem(s["name"], s["id"])
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        form.addRow("Сфера:", self.sphere_cb)

        self.section_cb = QComboBox()
        form.addRow("Раздел:", self.section_cb)
        self._update_sections()

        self.name_le = QLineEdit()
        form.addRow("Название:", self.name_le)

        self.icon_btn = QToolButton()
        self.icon_btn.setIconSize(QSize(24, 24))
        self.icon_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.icon_btn.setIcon(QIcon(str(UI_ICONS_DIR / self._icon_filename)))
        form.addRow("Иконка:", self.icon_btn)
        self.icon_btn.clicked.connect(self._choose_icon)

        vbox.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _update_sections(self):
        sphere_id = self.sphere_cb.currentData()
        self.section_cb.clear()
        for sec in self.db.get_sections(sphere_id):
            self.section_cb.addItem(sec["name"], sec["id"])

    def _load_category(self):
        row = self.db.conn.execute(
            "SELECT name, section_id, icon_path FROM category WHERE id=?", (self.category_id,)
        ).fetchone()
        if row:
            self.name_le.setText(row["name"])
            sec_id = row["section_id"]
            sp_row = self.db.conn.execute("SELECT sphere_id FROM section WHERE id=?", (sec_id,)).fetchone()
            if sp_row:
                sph_id = sp_row["sphere_id"]
                idx = self.sphere_cb.findData(sph_id)
                if idx >= 0:
                    self.sphere_cb.setCurrentIndex(idx)
                    self._update_sections()
                    j = self.section_cb.findData(sec_id)
                    if j >= 0:
                        self.section_cb.setCurrentIndex(j)
            icon = row["icon_path"] or "category.ico"
            self._icon_filename = icon
            icon_path = (LINK_ICONS_DIR / icon) if Path(LINK_ICONS_DIR / icon).exists() else UI_ICONS_DIR / icon
            self.icon_btn.setIcon(QIcon(str(icon_path)))

    def _choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать иконку", "", "Изображения (*.png *.ico *.jpg *.svg)"
        )
        if path:
            fname = Path(path).name
            dest = LINK_ICONS_DIR / fname
            if not dest.exists():
                shutil.copy2(path, dest)
            self._icon_filename = fname
            self.icon_btn.setIcon(QIcon(str(dest)))

    def _on_accept(self):
        name = self.name_le.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Название не может быть пустым")
            return
        self._result = {
            "name": name,
            "section_id": self.section_cb.currentData(),
            "icon_path": self._icon_filename
        }
        self.accept()

    def get_result(self):
        return self._result

    def set_result(self, data: dict):
        if "section_id" in data:
            sec_id = data["section_id"]
            sp_row = self.db.conn.execute("SELECT sphere_id FROM section WHERE id=?", (sec_id,)).fetchone()
            if sp_row:
                sph_id = sp_row["sphere_id"]
                idx = self.sphere_cb.findData(sph_id)
                if idx >= 0:
                    self.sphere_cb.setCurrentIndex(idx)
                    self._update_sections()
                    j = self.section_cb.findData(sec_id)
                    if j >= 0:
                        self.section_cb.setCurrentIndex(j)


class NoteDialog(QDialog):
    def __init__(self, link: dict, db: Database, parent=None):
        super().__init__(parent)
        self.link = link
        self.db = db
        self.setWindowTitle("Заметки")
        self.resize(400, 300)
        vbox = QVBoxLayout(self)
        self.notes_te = QTextEdit(self.link.get("notes", ""))
        vbox.addWidget(self.notes_te)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _on_accept(self):
        notes = self.notes_te.toPlainText()
        self.link["notes"] = notes
        self.db.upsert_link(self.link)
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, settings, theme_ctrl: ThemeController, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        self.setWindowTitle("Настройки")
        self.resize(400, 200)
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.auto_spin = QSpinBox()
        self.auto_spin.setRange(1, 1440)
        self.auto_spin.setValue(self.settings.get_autosave_interval())
        form.addRow("Автосохранение (мин):", self.auto_spin)

        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 100)
        self.max_spin.setValue(self.settings.get_max_backups())
        form.addRow("Макс. бэкапов:", self.max_spin)

        self.dark_cb = QCheckBox("Темная тема")
        self.dark_cb.setChecked(self.theme_ctrl.is_dark())
        form.addRow(self.dark_cb)

        vbox.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _on_accept(self):
        self.settings.set_autosave_interval(self.auto_spin.value())
        self.settings.set_max_backups(self.max_spin.value())
        theme = "dark" if self.dark_cb.isChecked() else "light"
        self.theme_ctrl.apply(theme)
        self.accept()


class ChromeProfilesWorker(QRunnable):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
    @pyqtSlot()
    def run(self):
        from app.utils.chrome_profiles import find_chrome_profiles
        profiles = find_chrome_profiles()
        self.callback(profiles)

class ChromeProfileDialog(QDialog):
    profiles_loaded = pyqtSignal(list)
    """
    Диалог выбора профиля Chrome с чекбоксами, кнопками "Выбрать все", "Снять все", "Обновить профили" и нижними кнопками "Сохранить", "Отмена".
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор профиля Chrome")
        self.setModal(True)
        self.result = []
        self.profile_checkboxes = []
        self._setup_size()
        self._setup_ui()
        self.threadpool = QThreadPool.globalInstance()
        self.profiles_loaded.connect(self._populate_profiles)
        self._start_profiles_loading()

    def _setup_size(self):
        base_width, base_height = 600, 500
        scale = getattr(self, 'scale_factor', 1.0)
        self.resize(int(base_width * scale), int(base_height * scale))

    def _setup_ui(self):
        from PyQt6.QtWidgets import QScrollArea, QCheckBox, QHBoxLayout
        main_layout = QVBoxLayout(self)
        label = QLabel("Выберите профиль Chrome:")
        main_layout.addWidget(label)

        # Список профилей с чекбоксами
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.profiles_layout = QVBoxLayout(scroll_content)
        self.profiles_layout.setContentsMargins(0, 0, 0, 0)
        self.profiles_layout.setSpacing(0)
        self.scroll.setWidget(scroll_content)
        main_layout.addWidget(self.scroll, 1)
        # Профили будут загружены асинхронно

        # Кнопки "Выбрать все", "Снять все"
        btns_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать все")
        self.select_all_btn.clicked.connect(self._on_select_all)
        btns_layout.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton("Снять все")
        self.deselect_all_btn.clicked.connect(self._on_deselect_all)
        btns_layout.addWidget(self.deselect_all_btn)
        main_layout.addLayout(btns_layout)

        # Кнопка "Обновить профили"
        self.refresh_btn = QPushButton("Обновить профили")
        self.refresh_btn.clicked.connect(self._start_profiles_loading)
        main_layout.addWidget(self.refresh_btn)

        # Нижние кнопки "Сохранить" и "Отмена"
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _start_profiles_loading(self):
        # Запуск воркера для поиска профилей
        worker = ChromeProfilesWorker(self._on_profiles_loaded)
        self.threadpool.start(worker)

    def _on_profiles_loaded(self, profiles):
        # Вызывается из воркера, но callback в главном потоке
        self.profiles_loaded.emit(profiles)

    def _populate_profiles(self, profiles):
        from PyQt6.QtWidgets import QCheckBox
        # Очистить старые чекбоксы
        while self.profiles_layout.count():
            child = self.profiles_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.setParent(None)
        self.profile_checkboxes = []
        for prof in profiles:
            email = prof.get("email", "(без email)")
            cb = QCheckBox(email)
            cb.profile = prof
            self.profiles_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)

    def _on_select_all(self):
        for cb in self.profile_checkboxes:
            cb.setChecked(True)

    def _on_deselect_all(self):
        for cb in self.profile_checkboxes:
            cb.setChecked(False)

    def accept(self) -> None:
        self.result = [cb.profile for cb in self.profile_checkboxes if cb.isChecked()]
        super().accept()

    def get_selected_profiles(self):
        return self.result