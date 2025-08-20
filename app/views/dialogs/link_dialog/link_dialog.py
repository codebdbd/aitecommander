"""
LinkDialog - диалог добавления/редактирования ссылок.
Основной класс с бизнес-логикой, использующий модульную структуру.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtGui import QColor, QIcon

from app.config_data import app_config
from app.utils.db.db_workers import LinkInfoWorker
from app.controllers.ui.dialogs import DialogManager
from app.utils.ui.icon.path_service import icon_path_service
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.utils.validators import validate_config_for_icons

from ..base_dialog import BaseDialog
from .link_dialog_handlers import LinkDialogHandlers
from .link_dialog_ui import LinkDialogUI
from app.views.effects.neon_effect import NeonEventFilter

# Обеспечиваем существование директории пользовательских иконок
icon_path_service.ensure_user_icons_dir()


class LinkDialog(BaseDialog):
    """Диалог добавления/редактирования ссылок с модульной структурой."""
    
    def __init__(self, initialization_data: Dict, dialog_controller, 
                 link: Optional[Dict] = None, category_id: Optional[int] = None, 
                 parent=None, link_controller=None):
        super().__init__(parent)
        
        # Получаем типы ссылок из конфигурации
        self.link_types = app_config.get_link_types()
        
        # Инициализация основных свойств
        self._init_core_properties(initialization_data, dialog_controller, link, category_id)
        
        # Опциональный контроллер для MVC архитектуры
        self.link_controller = link_controller
        
        # Инициализация компонентов
        self._init_components()
        
        # Проверка конфигурации
        if not self._validate_configuration():
            return
            
        # Настройка свойств UI и загрузка данных
        self._setup_ui_properties()
        self._load_initial()
        
    def _init_core_properties(self, initialization_data: Dict, dialog_controller, 
                            link: Optional[Dict], category_id: Optional[int]) -> None:
        """Инициализирует основные свойства диалога."""
        self.initialization_data = initialization_data
        self.dialog_controller = dialog_controller
        self.link = link.copy() if link else {}
        self.initial_category = category_id
        self.link_type = self.link.get("type", "web")
        self.icon_name = self.link.get("icon_path", "")
        self.selected_profiles: List[Dict] = []
        
    def _init_components(self) -> None:
        """Инициализация UI и обработчиков."""
        # UI компоненты
        self.ui = LinkDialogUI(self)
        self.ui.build_ui(self.link_types)

        # Неоновое свечение для кнопок типов ссылок — как у кнопок сфер
        try:
            self._neon_link_filter = NeonEventFilter(color=QColor('#0194F0'), blur_radius=18)
            for btn in self.ui.get_widget('type_group').buttons():
                btn.installEventFilter(self._neon_link_filter)
        except Exception:
            # Не блокируем диалог при ошибке эффекта
            pass
        
        # Обработчики событий
        self.handlers = LinkDialogHandlers(self)
        self.handlers.connect_signals()
        
        # Инициализация воркеров и таймеров
        self._init_workers_and_timers()
        
    def _make_icon(self, icon_path_str: str) -> Optional[QIcon]:
        """Создаёт QIcon из пути (абсолютного или относительного к папкам иконок)."""
        try:
            if not icon_path_str:
                return None
            p = Path(icon_path_str)
            if p.exists():
                return QIcon(str(p))
            user_p = self.get_user_icons_dir() / icon_path_str
            if user_p.exists():
                return QIcon(str(user_p))
            ui_p = self.get_ui_icons_dir() / icon_path_str
            if ui_p.exists():
                return QIcon(str(ui_p))
        except Exception:
            pass
        return None

    def _init_workers_and_timers(self) -> None:
        """Инициализирует воркеры и таймеры для обработки ссылок."""
        self._worker_task_id = 0  # Для защиты от race condition
        self._processing_timer = QTimer(self)
        self._processing_timer.setSingleShot(True)
        self._processing_timer.timeout.connect(self.handlers._trigger_link_processing)
        self._link_info_worker = None
        self._is_processing = False
        self._last_processed_path = ""
        self._active_worker = None  # Для отслеживания активного воркера
        
    def _validate_configuration(self) -> bool:
        """Проверяет конфигурацию диалога."""
        if not validate_config_for_icons(app_config):
            DialogManager.show_error(
                self,
                "Некорректная конфигурация иконок.",
                "Ошибка конфигурации",
                informative_text=(
                    "Не задан путь к каталогу иконок. Укажите путь в настройках приложения или конфиге."
                ),
                details="Параметр конфигурации для иконок отсутствует или пуст.",
            )
            self.close()
            return False
        return True
        
    def _setup_ui_properties(self) -> None:
        """Настраивает свойства UI диалога."""
        self.setWindowTitle("Редактировать ссылку" if self.link else "Добавить ссылку")
        self.setFixedSize(app_config.get('ui.link_dialog_width', 600), app_config.get('ui.link_dialog_height', 520))
        
    def _load_initial(self) -> None:
        """Загружает начальные данные в форму."""
        import logging
        logger = logging.getLogger(__name__)
        
        # ДИАГНОСТИЧЕСКОЕ ЛОГИРОВАНИЕ ДЛЯ ARGS

        
        # Установка типа ссылки
        type_group = self.ui.get_widget('type_group')
        for btn in type_group.buttons():
            if btn.property("link_type") == self.link_type:
                btn.setChecked(True)
                break

        # Загрузка данных формы
        form_data = {
            'url_le': self.link.get("url", ""),
            'name_le': self.link.get("name", ""),
            'args_le': self.link.get("args", ""),
            'notes_te': self.link.get("notes", ""),
            'fav_chk': bool(self.link.get("is_favorite", False))
        }
        
        # ДИАГНОСТИЧЕСКОЕ ЛОГИРОВАНИЕ ДЛЯ FORM_DATA

        
        self.ui.set_form_data(form_data)
        
        # ДИАГНОСТИЧЕСКОЕ ЛОГИРОВАНИЕ ПОСЛЕ УСТАНОВКИ В UI
        args_widget = self.ui.get_widget('args_le')


        # Установка иконки
        self._set_initial_icon()

        # Заполнение иерархии
        self._populate_hierarchy()

        # Загрузка мигрированных профилей
        if self.link and self.link.get('migrated_profiles'):
            self.selected_profiles = self.link['migrated_profiles']
            profile_btn = self.ui.get_widget('profile_btn')
            profile_btn.setText(self._format_profile_text(self.selected_profiles))

        # Обновление состояния UI
        self.handlers._update_ui_state()
        
    def _set_initial_icon(self) -> None:
        """Устанавливает начальную иконку."""
        if self.icon_name:
            icon_path = Path(self.icon_name)
            if not icon_path.is_absolute():
                icon_path = self.get_user_icons_dir() / icon_path
            if icon_path.exists():
                set_icon_to_button(self.ui.get_widget('icon_btn'), str(icon_path))
                return
                
        # Используем иконку по умолчанию
        default_icon = app_config.get_default_icons().get(self.link_type, "default.png")
        icon_path = self.get_ui_icons_dir() / default_icon
        if icon_path.exists():
            set_icon_to_button(self.ui.get_widget('icon_btn'), str(icon_path))
        else:
            # Сообщаем один раз, что иконка не найдена
            DialogManager.show_warning(
                self,
                "Иконка по умолчанию не найдена.",
                "Проблема с иконкой",
                informative_text="Кнопка будет отображаться без иконки. Укажите корректный путь к иконкам в настройках.",
                details=f"Ожидался файл: {icon_path}",
            )
            
    def set_link_type(self, link_type: str) -> None:
        """Программно выбрать тип ссылки и обновить UI.

        Вызывается внешним кодом (например, MainWindow.quick_add_link) вместо прямого
        доступа к приватному _on_type_changed.
        """
        if link_type not in {code for code, _ in self.link_types}:
            DialogManager.show_warning(
                self,
                "Неизвестный тип ссылки.",
                "Ошибка типа",
                informative_text="Допустимые значения берутся из конфигурации приложения.",
                details=f"Получен тип: {link_type}. Доступные: {[code for code, _ in self.link_types]}",
            )
            return
        # Отметить радиокнопку
        for btn in self.ui.get_widget('type_group').buttons():
            if btn.property("link_type") == link_type:
                btn.setChecked(True)
                break
        # Запуск стандартной обработки
        self.handlers._on_type_changed(link_type)
                    
    def _populate_hierarchy(self) -> None:
        """Заполняет иерархические списки."""
        sphere_cb = self.ui.get_widget('sphere_cb')
        section_cb = self.ui.get_widget('section_cb')
        category_cb = self.ui.get_widget('category_cb')
        
        # Используем данные из initialization_data вместо прямых запросов к БД
        spheres = self.initialization_data.get('spheres', [])
        for sp in spheres:
            sphere_cb.addItem(sp["name"], sp["id"])
        self.handlers._update_sections()
        
        # Используем иерархию из initialization_data
        cid = self.link.get("category_id") or self.initial_category
        if cid:
            hierarchy = self.initialization_data.get('category_hierarchy')
            if hierarchy:
                # Устанавливаем сферу
                sphere_idx = sphere_cb.findData(hierarchy['sphere_id'])
                if sphere_idx >= 0:
                    sphere_cb.setCurrentIndex(sphere_idx)
                    self.handlers._update_sections()
                    
                    # Устанавливаем раздел
                    section_idx = section_cb.findData(hierarchy['section_id'])
                    if section_idx >= 0:
                        section_cb.setCurrentIndex(section_idx)
                        self.handlers._update_categories()
                        
                        # Устанавливаем категорию
                        category_idx = category_cb.findData(hierarchy['category_id'])
                        if category_idx >= 0:
                            category_cb.setCurrentIndex(category_idx)
        else:
            # Устанавливаем первую сферу по умолчанию
            if spheres:
                sphere_cb.setCurrentIndex(0)
                sphere_id = spheres[0]["id"]
                
                # Обновляем разделы для первой сферы
                sections = [s for s in self.initialization_data.get('sections', [])
                           if s.get('sphere_id') == sphere_id]
                section_cb.clear()
                for sec in sections:
                    icon = self._make_icon(sec.get("icon_path", ""))
                    if icon:
                        section_cb.addItem(icon, sec["name"], sec["id"])
                    else:
                        section_cb.addItem(sec["name"], sec["id"])
                
                # Обновляем категории для первого раздела
                if sections:
                    section_id = sections[0]["id"]
                    categories = [c for c in self.initialization_data.get('categories', [])
                                 if c.get('section_id') == section_id]
                    category_cb.clear()
                    for cat in categories:
                        icon = self._make_icon(cat.get("icon_path", ""))
                        if icon:
                            category_cb.addItem(icon, cat["name"], cat["id"])
                        else:
                            category_cb.addItem(cat["name"], cat["id"])

    def get_ui_icons_dir(self) -> Path:
        """Получает директорию UI иконок."""
        return icon_path_service.get_ui_icons_dir()
        
    def get_user_icons_dir(self) -> Path:
        """Получает директорию пользовательских иконок."""
        return icon_path_service.get_user_icons_dir()
        
    def _format_profile_text(self, profiles: List[Dict]) -> str:
        """Форматирует текст для отображения выбранных профилей."""
        emails = [p.get("email") or p.get("name") for p in profiles]
        if not emails:
            return "Профиль"
        elif len(emails) == 1:
            return f"Профиль: {emails[0]}"
        elif len(emails) == 2:
            return f"Профили: {emails[0]}, {emails[1]}"
        return f"Профили: {emails[0]}, {emails[1]} и ещё {len(emails)-2}"
        
    def closeEvent(self, event) -> None:
        """Обработчик события закрытия окна."""
        # Если идёт обработка ссылки, попросим подтверждение у пользователя
        if getattr(self, '_is_processing', False) or getattr(self, '_active_worker', None):
            path_info = getattr(self, '_last_processed_path', '') or self.link.get('url', '')
            proceed = DialogManager.ask_confirmation(
                self,
                "Идёт обработка ссылки. Прервать и закрыть диалог?",
                "Подтверждение закрытия",
                informative_text="Текущая операция будет отменена и изменения могут быть потеряны.",
                details=(f"Последний путь/URL: {path_info}" if path_info else None),
            )
            if not proceed:
                event.ignore()
                return
        self._processing_timer.stop()
        self._processing_timer.deleteLater()
        # Корректно отменяем воркер, отписываемся от сигналов и сбрасываем ссылки
        if hasattr(self, '_active_worker') and self._active_worker:
            try:
                self._active_worker.signals.finished.disconnect()
            except Exception:
                pass
            try:
                self._active_worker.signals.error.disconnect()
            except Exception:
                pass
            self._active_worker.cancel()
            self._active_worker = None
        super().closeEvent(event)

