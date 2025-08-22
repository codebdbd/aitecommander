import logging
from typing import Dict, List

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.utils.browser.browser_profiles import get_profile_manager
from app.utils.browser.browser_profiles.utils import get_browser_display_name


class BrowserProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор профиля браузера")
        self.setMinimumSize(480, 400)
        self.manager = get_profile_manager()
        self.selected_profiles = []
        self.profile_checkboxes = []
        self._setup_ui()
        self._populate_browsers()
        # Не загружаем все профили сразу, только для выбранного браузера
        # self._populate_profiles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        # Браузер
        browser_layout = QHBoxLayout()
        browser_layout.addWidget(QLabel("Браузер:"))
        self.browser_combo = QComboBox()
        self.browser_combo.currentIndexChanged.connect(self._populate_profiles)
        browser_layout.addWidget(self.browser_combo)
        layout.addLayout(browser_layout)
        
        # Кнопки управления профилями
        control_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать все")
        self.deselect_all_btn = QPushButton("Снять выделение")
        self.select_all_btn.clicked.connect(self._select_all_profiles)
        self.deselect_all_btn.clicked.connect(self._deselect_all_profiles)
        control_layout.addWidget(self.select_all_btn)
        control_layout.addWidget(self.deselect_all_btn)
        layout.addLayout(control_layout)
        
        # Список профилей
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.profile_widget = QWidget()
        self.profile_layout = QVBoxLayout(self.profile_widget)
        self.scroll.setWidget(self.profile_widget)
        layout.addWidget(self.scroll)
        
        # Кнопки
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _populate_browsers(self):
        self.browser_combo.clear()
        browsers = self.manager.get_supported_browsers()
        for b in browsers:
            self.browser_combo.addItem(b["name"], b["key"])
        # Выбрать первый браузер по умолчанию
        if self.browser_combo.count() > 0:
            self.browser_combo.setCurrentIndex(0)

    def _populate_profiles(self):
        # Очистка старых виджетов из layout
        for cb in self.profile_checkboxes:
            cb.deleteLater()
        self.profile_checkboxes.clear()
        
        # Очищаем все виджеты из layout
        while self.profile_layout.count():
            child = self.profile_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        browser_key = self.browser_combo.currentData()
        profiles = []
        
        # Загружаем только профили выбранного браузера
        profiles = self.manager.get_profiles_by_browser(browser_key)
        finder = self.manager.finders.get(browser_key)
        if finder:
            for profile in profiles:
                profile['browser_key'] = browser_key
                profile['browser_name'] = get_browser_display_name(finder, browser_key)

        logger = logging.getLogger(__name__)
        logger.debug(f"_populate_profiles: browser_key={browser_key}")

        if not profiles:
            self.profile_layout.addWidget(QLabel("Профили не найдены"))
            return

        # Создание чекбоксов для профилей
        for profile in profiles:
            # Для визуальной ясности добавляем имя браузера
            browser_name = profile.get('browser_name', '')
            profile_name = profile.get('email', profile.get('name', 'Без имени'))
            text = f"{profile_name} ({browser_name})"
            cb = QCheckBox(text)
            cb.profile_data = profile
            self.profile_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)
        # Добавляем stretch, чтобы чекбоксы не растягивались по вертикали
        self.profile_layout.addStretch()

    def accept(self):
        """Переопределение accept для сохранения выбранных профилей."""
        self.selected_profiles = [cb.profile_data for cb in self.profile_checkboxes if cb.isChecked()]
        super().accept()
    
    def get_selected_profiles(self) -> List[Dict]:
        """Возвращает список выбранных профилей."""
        logger = logging.getLogger(__name__)
        
        selected = self.selected_profiles
        
        logger.debug(f"get_selected_profiles: returning {len(selected)} profiles")
        for i, profile in enumerate(selected):
            logger.debug(f"get_selected_profiles: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}")
        
        return selected
    
    def _select_all_profiles(self):
        """Выбрать все профили."""
        for cb in self.profile_checkboxes:
            cb.setChecked(True)
    
    def _deselect_all_profiles(self):
        """Снять выделение со всех профилей."""
        for cb in self.profile_checkboxes:
            cb.setChecked(False)
