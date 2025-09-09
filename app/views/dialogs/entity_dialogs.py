import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QRunnable, QSize, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.business import StructureBusinessLogic
from app.controllers.ui.theme_controller import ThemeController
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


def _populate_spheres_common(
    structure_business: StructureBusinessLogic, sphere_cb: QComboBox
) -> None:
    """Общий помощник для заполнения комбобокса сферами.
    Не очищает список — повторяет текущее поведение вызывающих мест.
    """
    spheres = structure_business.get_spheres()
    for sphere in spheres:
        sphere_cb.addItem(sphere["name"], sphere["id"])


class BaseEntityDialog(BaseDialog):
    """
    Базовый диалог для сущностей с именем и иконкой (Раздел, Категория).
    """

    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        entity_name: str,
        entity_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.structure_business = structure_business
        self.entity_id = entity_id
        self.entity_name = entity_name  # e.g., 'section', 'category'
        self._result = None
        self._icon_filename = f"{entity_name}.png"

        title_verb = "Редактировать" if entity_id else "Добавить"
        title_noun_map = {"section": "раздел", "category": "категорию"}
        title_noun = title_noun_map.get(entity_name, "сущность")
        self.setWindowTitle(f"{title_verb} {title_noun}")

    def _init_common_ui(self, form_layout: QFormLayout):
        """Инициализирует общие элементы UI: поле имени и кнопку иконки."""
        self.name_le = QLineEdit()
        # По Enter сохраняем только если имя непустое (без назначения default-кнопки)
        try:
            self.name_le.returnPressed.connect(self._on_return_pressed)
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to connect returnPressed handler",
                exc_info=True,
            )
        self.icon_btn = QPushButton("Иконка")
        self.icon_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        # Use centralized dialog icon size from UIConfig
        self.icon_btn.setIconSize(QSize(*app_config.ui.get_dialog_icon_size()))
        self.icon_btn.setIcon(
            create_icon_from_path(
                str(icon_path_service.get_ui_icons_dir() / self._icon_filename)
            )
        )
        self.icon_btn.clicked.connect(self._choose_icon)

        name_layout = QHBoxLayout()
        name_layout.addWidget(self.name_le, 1)
        name_layout.addWidget(self.icon_btn)
        form_layout.addRow("Имя:", name_layout)

    def _create_button_box(self):
        """Создает и возвращает QDialogButtonBox."""
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = bb.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Сохранить")
        ok_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        # Не делаем кнопку по умолчанию, чтобы не было подсветки default/autoDefault без фокуса
        try:
            ok_btn.setDefault(False)
            ok_btn.setAutoDefault(False)
            # Кнопка получает фокус только по Tab (не автоматически при показе окна)
            ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to adjust Ok button defaults/focus",
                exc_info=True,
            )

        cancel_btn = bb.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Отмена")
        cancel_btn.setFixedWidth(app_config.ui.get_fixed_button_width())
        # Также убираем default/autoDefault у Cancel, чтобы кнопки не перехватывали фокус по умолчанию
        try:
            cancel_btn.setDefault(False)
            cancel_btn.setAutoDefault(False)
            cancel_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to adjust Cancel button defaults/focus",
                exc_info=True,
            )

        # Блокируем кнопку Сохранить, пока имя пустое; обновляем по мере ввода
        try:
            name_text = self.name_le.text().strip() if hasattr(self, "name_le") else ""
            ok_btn.setEnabled(bool(name_text))
            if hasattr(self, "name_le"):
                self.name_le.textChanged.connect(
                    lambda _t: ok_btn.setEnabled(bool(self.name_le.text().strip()))
                )
        except Exception:
            logger.debug(
                "BaseEntityDialog: failed to wire name_le textChanged to Ok button enable",
                exc_info=True,
            )

        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        return bb

    def showEvent(self, event):
        """На показе окна принудительно ставим фокус на поле имени, чтобы его не перехватывала кнопка."""
        super().showEvent(event)
        try:
            self.name_le.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        except Exception:
            logger.debug("BaseEntityDialog.showEvent: setFocus failed", exc_info=True)

    def _on_return_pressed(self):
        """Локальная обработка Enter на поле имени: триггерим сохранение только при валидном имени."""
        try:
            if hasattr(self, "name_le") and self.name_le.text().strip():
                # Делегируем основную валидацию в _on_accept (наследники проверят остальные поля)
                self._on_accept()
        except Exception:
            logger.debug("BaseEntityDialog._on_return_pressed failed", exc_info=True)

    def _get_icon_path(self, icon_filename: str) -> Path:
        """Возвращает путь к иконке, проверяя сначала пользовательские, затем UI иконки."""
        link_icon_path = icon_path_service.get_user_icons_dir() / icon_filename
        if link_icon_path.exists():
            return link_icon_path
        return icon_path_service.get_ui_icons_dir() / icon_filename

    def _choose_icon(self):
        """Выбор иконки с умным копированием без дублирования."""
        try:
            from app.utils.ui.icon.selection import choose_icon_and_copy

            user_icons_dir = icon_path_service.get_user_icons_dir()
            fname, icon = choose_icon_and_copy(self, user_icons_dir)
            if not fname or not icon:
                return

            self.icon_btn.setIcon(icon)
            self._icon_filename = fname

        except Exception as e:
            self.show_error(
                "Не удалось установить выбранную иконку.",
                "Ошибка выбора иконки",
                informative_text="Выберите другой файл изображения (.png, .ico, .jpg, .svg) и повторите попытку.",
                details=str(e),
            )

    def _on_accept_base(self) -> Optional[dict]:
        """Базовая проверка и сбор данных. Возвращает словарь с именем и иконкой или None при ошибке."""
        name = self.name_le.text().strip()
        if not name:
            self.show_warning(
                "Название не может быть пустым.",
                "Неверное имя",
                informative_text="Введите имя сущности (минимум 1 символ).",
            )
            return None
        return {"name": name, "icon_path": self._icon_filename}

    def get_result(self):
        return self._result

    def _populate_spheres(self):
        """Заполняет комбобокс сферами (используется в наследниках)."""
        _populate_spheres_common(self.structure_business, self.sphere_cb)


class SectionDialog(BaseEntityDialog):
    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        section_id: Optional[int] = None,
        default_sphere_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(structure_business, "section", section_id, parent)
        self.default_sphere_id = default_sphere_id
        self.resize(400, 150)
        self._init_ui()
        # Фокус на поле имени при открытии
        try:
            self.name_le.setFocus()
        except Exception:
            logger.debug("SectionDialog.__init__: setFocus failed", exc_info=True)
        if section_id:
            self._load_section()

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Имя на первой строке
        self._init_common_ui(form)

        # Затем выбор сферы
        self.sphere_cb = QComboBox()
        self._populate_spheres()
        form.addRow("Сфера:", self.sphere_cb)

        if self.default_sphere_id is not None and self.entity_id is None:
            self._set_sphere_selection(self.default_sphere_id)

        vbox.addLayout(form)
        vbox.addWidget(self._create_button_box())

    def _set_sphere_selection(self, sphere_id: int):
        """Устанавливает выбранную сферу по ID."""
        idx = self.sphere_cb.findData(sphere_id)
        if idx >= 0:
            self.sphere_cb.setCurrentIndex(idx)

    def _load_section(self):
        """Загружает данные раздела для редактирования."""
        section_data = self.structure_business.get_section_for_editing(self.entity_id)

        if not section_data:
            self.show_warning(
                "Раздел для редактирования не найден.",
                "Раздел недоступен",
                informative_text=f"Возможно, раздел был удалён. ID: {self.entity_id}",
            )
            return

        self.name_le.setText(section_data["name"])
        self._set_sphere_selection(section_data["sphere_id"])

        icon = section_data["icon_path"] or f"{self.entity_name}.ico"
        self._icon_filename = icon
        icon_path = self._get_icon_path(icon)
        self.icon_btn.setIcon(create_icon_from_path(str(icon_path)))

    def _on_accept(self):
        base_result = self._on_accept_base()
        if base_result is None:
            return

        sphere_id = self.sphere_cb.currentData()
        if sphere_id is None:
            self.show_warning(
                "Сфера не выбрана.",
                "Требуется выбор сферы",
                informative_text="Выберите сферу из выпадающего списка, затем нажмите 'Сохранить'.",
            )
            return

        self._result = base_result
        self._result["sphere_id"] = sphere_id
        self.accept()


class CategoryDialog(BaseEntityDialog):
    def __init__(
        self,
        structure_business: StructureBusinessLogic,
        category_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(structure_business, "category", category_id, parent)
        self.resize(400, 200)
        self._init_ui()
        # Фокус на поле имени при открытии
        try:
            self.name_le.setFocus()
        except Exception:
            pass
        if category_id:
            self._load_category()

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Имя на первой строке
        self._init_common_ui(form)

        # Затем сфера и раздел
        self.sphere_cb = QComboBox()
        self._populate_spheres()
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        form.addRow("Сфера:", self.sphere_cb)

        self.section_cb = QComboBox()
        form.addRow("Раздел:", self.section_cb)
        self._update_sections()

        vbox.addLayout(form)
        vbox.addWidget(self._create_button_box())

    def _update_sections(self):
        """Обновляет список разделов при изменении сферы."""
        sphere_id = self.sphere_cb.currentData()
        if sphere_id is None:
            return

        self.section_cb.clear()
        try:
            sections = self.structure_business.get_sections(sphere_id)
            for section in sections:
                self.section_cb.addItem(section["name"], section["id"])
        except Exception as e:
            self.show_error(
                "Не удалось загрузить список разделов.",
                "Ошибка загрузки разделов",
                informative_text="Проверьте подключение к базе данных и повторите попытку.",
                details=str(e),
            )

    def _load_category(self):
        """Загружает данные категории для редактирования."""
        category_data = self.structure_business.get_category_for_editing(self.entity_id)

        if not category_data:
            self.show_warning(
                "Категория для редактирования не найдена.",
                "Категория недоступна",
                informative_text=f"Возможно, категория была удалена. ID: {self.entity_id}",
            )
            return

        self.name_le.setText(category_data["name"])
        section_id = category_data["section_id"]

        # Получаем иерархию через бизнес-логику
        hierarchy = self.structure_business.get_category_hierarchy(self.entity_id)

        if hierarchy:
            sphere_id = hierarchy["sphere_id"]
            # Устанавливаем сферу
            sphere_idx = self.sphere_cb.findData(sphere_id)
            if sphere_idx >= 0:
                self.sphere_cb.setCurrentIndex(sphere_idx)
                self._update_sections()
                # Устанавливаем раздел
                section_idx = self.section_cb.findData(section_id)
                if section_idx >= 0:
                    self.section_cb.setCurrentIndex(section_idx)

        # Устанавливаем иконку
        icon = category_data["icon_path"] or f"{self.entity_name}.ico"
        self._icon_filename = icon
        icon_path = self._get_icon_path(icon)
        self.icon_btn.setIcon(create_icon_from_path(str(icon_path)))

    def _on_accept(self):
        base_result = self._on_accept_base()
        if base_result is None:
            return

        section_id = self.section_cb.currentData()
        if section_id is None:
            self.show_warning(
                "Раздел не выбран.",
                "Требуется выбор раздела",
                informative_text="Выберите раздел из выпадающего списка, затем нажмите 'Сохранить'.",
            )
            return

        self._result = base_result
        self._result["section_id"] = section_id
        self.accept()

    def set_result(self, data: dict):
        """Устанавливает результат диалога на основе переданных данных."""
        if "section_id" not in data:
            return

        section_id = data.get("section_id")
        if not section_id:
            return

        section_data = self.structure_business.get_section_for_editing(section_id)

        if section_data:
            sphere_id = section_data["sphere_id"]
            sphere_idx = self.sphere_cb.findData(sphere_id)
            if sphere_idx >= 0:
                self.sphere_cb.setCurrentIndex(sphere_idx)
                self._update_sections()
                section_idx = self.section_cb.findData(section_id)
                if section_idx >= 0:
                    self.section_cb.setCurrentIndex(section_idx)


class NoteDialog(BaseDialog):
    def __init__(self, link: dict, parent=None):
        super().__init__(parent)
        self.link = link
        self.setWindowTitle("Заметки")
        self.resize(400, 300)
        self._init_ui()

    def _init_ui(self):
        """Инициализирует интерфейс диалога заметок."""
        vbox = QVBoxLayout(self)

        self.notes_te = QTextEdit(self.link.get("notes", ""))
        # Не перехватывать Tab внутри многострочного поля — Tab должен переключать фокус
        try:
            self.notes_te.setTabChangesFocus(True)
        except Exception:
            pass
        vbox.addWidget(self.notes_te)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Сохранить")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _on_accept(self):
        """Обновляет заметки в объекте ссылки."""
        try:
            notes = self.notes_te.toPlainText()
            self.link["notes"] = notes
            # Не сохраняем сразу - пусть это делает контроллер
            self.accept()
        except Exception as e:
            self.show_error(
                "Не удалось обновить заметки.",
                "Ошибка обновления заметок",
                informative_text="Закройте и откройте диалог снова, затем повторите попытку.",
                details=str(e),
            )


class SettingsDialog(BaseDialog):
    def __init__(self, settings, theme_ctrl: ThemeController, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Настройки")
        self.resize(400, 200)
        self._init_ui()

    def _init_ui(self):
        """Инициализирует интерфейс диалога настроек."""
        vbox = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Настройка максимального количества бэкапов через выпадающий список
        self.max_backups_combo = QComboBox()
        self.max_backups_combo.addItems([str(i) for i in range(1, 11)])
        try:
            current = int(self.settings.get_max_backups())
            if 1 <= current <= 10:
                self.max_backups_combo.setCurrentIndex(current - 1)
            else:
                self.max_backups_combo.setCurrentIndex(0)
        except Exception:
            self.max_backups_combo.setCurrentIndex(0)
        form.addRow("Макс. бэкапов:", self.max_backups_combo)

        # Настройка размера шрифта
        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems([str(i) for i in range(9, 15)])
        try:
            current_font_size = int(self.settings.get_font_size())
            if 9 <= current_font_size <= 14:
                self.font_size_combo.setCurrentIndex(current_font_size - 9)
            else:
                self.font_size_combo.setCurrentIndex(3)  # 12 по умолчанию
        except Exception:
            self.font_size_combo.setCurrentIndex(3)
        form.addRow("Размер шрифта:", self.font_size_combo)

        vbox.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Сохранить")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def _on_accept(self):
        """Сохраняет настройки."""
        try:
            # Сохраняем выбранное значение из выпадающего списка
            max_backups = int(self.max_backups_combo.currentText())
            self.settings.set_max_backups(max_backups)

            font_size = int(self.font_size_combo.currentText())
            self.settings.set_font_size(font_size)

            parent = self.parent()
            # Применяем размер шрифта только локально для дерева и таблицы
            if parent is not None:
                if hasattr(parent, "tree") and hasattr(parent.tree, "update_font_size"):
                    parent.tree.update_font_size(font_size)
                if hasattr(parent, "table") and hasattr(
                    parent.table, "update_font_size"
                ):
                    parent.table.update_font_size(font_size)

            self.accept()

        except Exception as e:
            self.show_error(
                "Не удалось сохранить настройки.",
                "Ошибка сохранения настроек",
                informative_text="Проверьте корректность значений и повторите попытку.",
                details=str(e),
            )


class ChromeProfilesWorker(QRunnable):
    """Воркер для асинхронной загрузки профилей Chrome."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    @pyqtSlot()
    def run(self):
        """Выполняет поиск профилей Chrome в отдельном потоке."""
        try:
            from app.utils.browser.browser_profiles import get_profile_manager

            manager = get_profile_manager()
            profiles = manager.get_browser_profiles("chrome")
            self.callback(profiles)
        except ImportError:
            self.callback([])  # Возвращаем пустой список если модуль недоступен
        except Exception:
            self.callback([])  # Возвращаем пустой список при любой ошибке


class ChromeProfileDialog(BaseDialog):
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
        """Устанавливает размер диалога."""
        base_width, base_height = 600, 500
        scale = getattr(self, "scale_factor", 1.0)
        self.resize(int(base_width * scale), int(base_height * scale))

    def _setup_ui(self):
        """Настраивает интерфейс диалога."""
        main_layout = QVBoxLayout(self)

        label = QLabel("Выберите профиль Chrome:")
        main_layout.addWidget(label)

        # Список профилей с чекбоксами
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        scroll_content = QWidget(self.scroll)
        self.profiles_layout = QVBoxLayout(scroll_content)
        self.profiles_layout.setContentsMargins(0, 0, 0, 0)
        self.profiles_layout.setSpacing(0)
        self.scroll.setWidget(scroll_content)
        main_layout.addWidget(self.scroll, 1)

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
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _start_profiles_loading(self):
        """Запускает асинхронную загрузку профилей."""
        # Блокируем кнопку обновления во время загрузки
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Загрузка...")

        worker = ChromeProfilesWorker(self._on_profiles_loaded)
        self.threadpool.start(worker)

    def _on_profiles_loaded(self, profiles):
        """Обработчик завершения загрузки профилей (вызывается из воркера)."""
        # Восстанавливаем кнопку обновления
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Обновить профили")

        # Передаем результат в главный поток через сигнал
        self.profiles_loaded.emit(profiles)

    def _populate_profiles(self, profiles):
        """Заполняет список профилей чекбоксами."""
        # Очищаем старые чекбоксы
        self._clear_profile_checkboxes()

        if not profiles:
            no_profiles_label = QLabel("Профили Chrome не найдены")
            no_profiles_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_layout.addWidget(no_profiles_label)
            return

        # Создаем чекбоксы для каждого профиля
        for profile in profiles:
            email = profile.get("email", "(без email)")
            cb = QCheckBox(email)
            cb.profile = profile
            self.profiles_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)

    def _clear_profile_checkboxes(self):
        """Очищает список чекбоксов профилей."""
        while self.profiles_layout.count():
            child = self.profiles_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.setParent(None)
        self.profile_checkboxes.clear()

    def _on_select_all(self):
        """Выбирает все профили."""
        for cb in self.profile_checkboxes:
            cb.setChecked(True)

    def _on_deselect_all(self):
        """Снимает выбор со всех профилей."""
        for cb in self.profile_checkboxes:
            cb.setChecked(False)

    def accept(self) -> None:
        """Сохраняет выбранные профили и закрывает диалог."""
        self.result = [cb.profile for cb in self.profile_checkboxes if cb.isChecked()]
        super().accept()

    def get_selected_profiles(self):
        """Возвращает список выбранных профилей."""
        return self.result
