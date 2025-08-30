import logging
from typing import Dict, List

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.utils.browser.browser_profiles import async_profile_manager as _apm
from app.utils.browser.browser_profiles import get_profile_manager
from app.utils.browser.browser_profiles import persistent_cache as _pc
from app.utils.browser.browser_profiles import profile_manager as _pm
from app.utils.browser.browser_profiles.utils import get_browser_display_name

logger = logging.getLogger(__name__)


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
        # 1. Линия: Браузеры + Обновить
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Браузеры:"))
        self.browser_combo = QComboBox()
        self.browser_combo.currentIndexChanged.connect(self._populate_profiles)
        top_layout.addWidget(self.browser_combo, 1)
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self.refresh_profiles)
        top_layout.addWidget(self.refresh_btn, 0)
        layout.addLayout(top_layout)

        # 2. Линия: строка поиска
        search_layout = QHBoxLayout()
        self.search_line = QLineEdit()
        self.search_line.setPlaceholderText("Поиск по имени/email…")
        self.search_line.textChanged.connect(self._populate_profiles)
        search_layout.addWidget(self.search_line, 1)
        layout.addLayout(search_layout)

        # Список профилей
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.profile_widget = QWidget()
        self.profile_layout = QVBoxLayout(self.profile_widget)
        self.scroll.setWidget(self.profile_widget)
        layout.addWidget(self.scroll)

        # Кнопки
        # 4. Нижняя линия: слева выборные кнопки и статус, справа Сохранить/Отмена
        bottom_layout = QHBoxLayout()
        left_bottom = QHBoxLayout()
        # Кнопки выборных действий слева
        self.select_all_btn = QPushButton("Добавить все")
        self.select_all_btn.clicked.connect(self._select_all_profiles)
        left_bottom.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton("Отменить выделение")
        self.deselect_all_btn.clicked.connect(self._deselect_all_profiles)
        left_bottom.addWidget(self.deselect_all_btn)
        # Индикатор статуса/прогресса
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; margin-left: 8px;")
        left_bottom.addWidget(self.status_label, 0)
        bottom_layout.addLayout(left_bottom, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Локализация подписей
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText("Сохранить")
            ok_btn.setEnabled(False)  # по умолчанию неактивна до выбора
            self._ok_button = ok_btn
        if cancel_btn is not None:
            cancel_btn.setText("Отмена")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        bottom_layout.addWidget(self.button_box, 0)
        layout.addLayout(bottom_layout)

    def _set_controls_enabled(self, enabled: bool):
        self.browser_combo.setEnabled(enabled)
        self.search_line.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.deselect_all_btn.setEnabled(enabled)
        # Кнопка сохранить зависит от наличия выбора, но при блокировке всего диалога тоже дизейблим
        if hasattr(self, "_ok_button") and self._ok_button is not None:
            if not enabled:
                self._ok_button.setEnabled(False)
            else:
                self._update_save_enabled()

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

        # Загружаем только профили выбранного браузера из кэша менеджера (без дискового сканирования)
        profiles = self.manager.get_profiles_by_browser(browser_key)
        # Фильтрация по строке поиска
        query = (self.search_line.text() or "").strip().lower()
        if query:
            def _match(p: Dict) -> bool:
                name = str(p.get("email") or p.get("name") or "").lower()
                path = str(p.get("path") or "").lower()
                return query in name or query in path
            profiles = [p for p in profiles if _match(p)]
        finder = self.manager.finders.get(browser_key)
        if finder:
            for profile in profiles:
                profile["browser_key"] = browser_key
                profile["browser_name"] = get_browser_display_name(finder, browser_key)

        logger.debug(f"_populate_profiles: browser_key={browser_key}")

        if not profiles:
            self.profile_layout.addWidget(QLabel("Профили не найдены"))
            return

        # Создание чекбоксов для профилей
        for profile in profiles:
            # Для визуальной ясности добавляем имя браузера
            browser_name = profile.get("browser_name", "")
            profile_name = profile.get("email", profile.get("name", "Без имени"))
            text = f"{profile_name} ({browser_name})"
            cb = QCheckBox(text)
            cb.profile_data = profile
            # Отслеживаем изменения для управления доступностью кнопки "Сохранить"
            try:
                cb.stateChanged.connect(self._update_save_enabled)
            except Exception:
                pass
            self.profile_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)
        # Добавляем stretch, чтобы чекбоксы не растягивались по вертикали
        self.profile_layout.addStretch()
        # Обновить состояние кнопки "Сохранить" после перестроения списка
        self._update_save_enabled()

    def refresh_profiles(self):
        """Ручное обновление всех профилей: асинхронно, с сохранением кэша и обновлением UI."""
        self._set_controls_enabled(False)
        self.status_label.setText("Загрузка профилей…")
        try:
            async_mgr = _apm.get_async_profile_manager()

            def _on_ready(all_profiles: Dict[str, List[Dict]]):
                try:
                    # Сохранить профили в персистентный кэш
                    cache = _pc.PersistentProfileCache(default_ttl=3600)
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            cache.set(key, profiles)
                        except Exception:
                            pass
                    # Обновить кэш синхронного менеджера (единый кэш)
                    mgr = _pm.get_profile_manager()
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            mgr.cache.set(key, profiles)
                        except Exception:
                            pass
                    # Обновить списки в диалоге
                    self._populate_browsers()
                    self._populate_profiles()
                finally:
                    # Отписка и восстановление контролов
                    try:
                        async_mgr.all_profiles_ready.disconnect(_on_ready)
                        async_mgr.loading_progress.disconnect(_on_progress)
                        async_mgr.loading_error.disconnect(_on_error)
                    except Exception:
                        pass
                    self._set_controls_enabled(True)
                    self.status_label.setText("")

            # Подписка и запуск загрузки без использования оперативного кэша воркера
            async_mgr.all_profiles_ready.connect(_on_ready)
            def _on_progress(operation: str, current: int, total: int):
                # operation вида "Загрузка chrome" из менеджера
                try:
                    self.status_label.setText(f"{operation} ({current}/{total})…")
                except Exception:
                    pass

            def _on_error(operation: str, message: str):
                logging.warning("Ошибка во время %s: %s", operation, message)
                self.status_label.setText("Ошибка загрузки профилей")

            async_mgr.loading_progress.connect(_on_progress)
            async_mgr.loading_error.connect(_on_error)
            async_mgr.load_all_profiles_async(use_cache=False)
        except Exception as e:
            logging.warning("Не удалось запустить обновление профилей: %s", e)
            self._set_controls_enabled(True)
            self.status_label.setText("Ошибка запуска загрузки")

    def accept(self):
        """Переопределение accept для сохранения выбранных профилей."""
        self.selected_profiles = [
            cb.profile_data for cb in self.profile_checkboxes if cb.isChecked()
        ]
        super().accept()

    def get_selected_profiles(self) -> List[Dict]:
        """Возвращает список выбранных профилей."""
        selected = self.selected_profiles

        logger.debug(f"get_selected_profiles: returning {len(selected)} profiles")
        for i, profile in enumerate(selected):
            logger.debug(
                f"get_selected_profiles: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}"
            )

        return selected

    def _select_all_profiles(self):
        """Выбрать все профили."""
        for cb in self.profile_checkboxes:
            cb.setChecked(True)
        self._update_save_enabled()

    def _deselect_all_profiles(self):
        """Снять выделение со всех профилей."""
        for cb in self.profile_checkboxes:
            cb.setChecked(False)
        self._update_save_enabled()

    def _update_save_enabled(self):
        """Включает кнопку "Сохранить", если выбран хотя бы один профиль."""
        try:
            any_checked = any(cb.isChecked() for cb in self.profile_checkboxes)
            if hasattr(self, "_ok_button") and self._ok_button is not None:
                self._ok_button.setEnabled(any_checked)
        except Exception:
            pass
