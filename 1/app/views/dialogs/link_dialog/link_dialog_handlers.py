"""
Обработчики событий для LinkDialog.
Содержит логику обработки пользовательских действий.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QFileDialog

from app.config_data import app_config
from app.utils.db.db_workers import LinkInfoWorker, StructureWorkerSignals
from app.utils.ui.dialog_manager import DialogManager
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.utils.ui.icon.selection import choose_icon_and_copy


class LinkDialogHandlers:
    """Обработчики событий для LinkDialog."""
    
    def __init__(self, dialog):
        """Инициализация обработчиков."""
        self.dialog = dialog
        self._last_processed_path = ""
        self._is_processing = False
        self._worker_task_id = 0
        self._active_worker = None
        # Создаем сигналы для воркеров
        self.signals = StructureWorkerSignals()
        # Подключаем сигналы
        self.signals.link_info_finished.connect(lambda info: self._on_link_info_fetched(info))
        self.signals.simple_error.connect(lambda error: self._on_link_info_error(error))
        
    def connect_signals(self) -> None:
        """Подключение сигналов к слотам."""
        # Тип ссылки
        self.dialog.ui.type_group.buttonClicked.connect(
            lambda b: self._on_type_changed(b.property("link_type"))
        )
        
        # URL изменение
        self.dialog.ui.get_widget('url_le').textChanged.connect(self._on_path_changed)
        
        # Кнопки
        self.dialog.ui.get_widget('browse_btn').clicked.connect(self._on_browse)
        self.dialog.ui.get_widget('profile_btn').clicked.connect(self._on_profile)
        self.dialog.ui.get_widget('icon_btn').clicked.connect(self._on_choose_icon)
        
        # Иерархия
        self.dialog.ui.get_widget('sphere_cb').currentIndexChanged.connect(self._update_sections)
        self.dialog.ui.get_widget('section_cb').currentIndexChanged.connect(self._update_categories)
        
        # Кнопки диалога
        self.dialog.ui.get_widget('button_box').accepted.connect(self._on_accept)
        self.dialog.ui.get_widget('button_box').rejected.connect(self.dialog.reject)
        
    def _on_type_changed(self, link_type: str) -> None:
        """Обработчик изменения типа ссылки."""
        self.dialog.link_type = link_type
        
        # Очистка полей при смене типа
        self.dialog.ui.set_widget_value('url_le', "")
        self.dialog.ui.set_widget_value('name_le', "")
        self.dialog.ui.set_widget_value('args_le', "")
        
        # Сброс состояния обработки ссылок для возможности повторного автозаполнения
        self._last_processed_path = ""
        self._is_processing = False
        
        # Отмена активного воркера при смене типа ссылки (используем переменные из dialog)
        if hasattr(self.dialog, '_active_worker') and self.dialog._active_worker:
            try:
                self.dialog._active_worker.cancel()
            except Exception:
                pass  # Игнорируем ошибки отмены
            self.dialog._active_worker = None
        
        # Установка иконки по умолчанию (без зависимости от темы)
        default_icons = app_config.get_default_icons()
        default_icon_filename = default_icons.get(link_type, default_icons.get("default"))
        self.dialog.icon_name = default_icon_filename or ""
        if default_icon_filename:
            icon_path = self.dialog.get_ui_icons_dir() / default_icon_filename
            if icon_path.exists():
                set_icon_to_button(self.dialog.ui.get_widget('icon_btn'), str(icon_path))
            else:
                self.dialog.ui.get_widget('icon_btn').setIcon(QIcon())
        else:
            self.dialog.ui.get_widget('icon_btn').setIcon(QIcon())
            
        self._update_ui_state()
        
    def _update_ui_state(self) -> None:
        """Обновляет состояние UI в зависимости от типа ссылки."""
        is_web = (self.dialog.link_type == "web")
        
        profile_btn = self.dialog.ui.get_widget('profile_btn')
        browse_btn = self.dialog.ui.get_widget('browse_btn')
        args_le = self.dialog.ui.get_widget('args_le')
        args_label = self.dialog.ui.get_widget('args_label')
        
        profile_btn.setVisible(is_web)
        
        # Кнопка 'Обзор' для определенных типов
        browse_btn.setVisible(self.dialog.link_type in 
                            ("file", "folder", "program", "script", "chromeapp"))
        
        # Аргументы только для типов, где они предусмотрены
        args_supported_types = ("program", "script", "chromeapp", "web")
        show_args = self.dialog.link_type in args_supported_types
        args_le.setVisible(show_args)
        args_label.setVisible(show_args)
        
    def _on_browse(self) -> None:
        """Обработчик кнопки 'Обзор'."""
        link_type = self.dialog.link_type
        path = ""
        
        # Получить путь по умолчанию из конфига
        default_paths = app_config.get_default_browse_paths()
        start_dir = default_paths.get(link_type, "")
        
        # Обработка путей: GUID пути не проверяем через os.path.exists
        if start_dir:
            if start_dir.startswith("::"):
                # GUID путь для "Мой компьютер" - оставляем как есть
                pass
            else:
                # Обычный путь - разворачиваем переменные и проверяем
                start_dir = os.path.expandvars(start_dir)
                if not os.path.exists(start_dir):
                    start_dir = ""  # Fallback к "Мой компьютер"
        
        PROGRAM_FILES = "Программы (*.exe *.bat *.com *.msi *.lnk)"
        SCRIPT_FILES = "Скрипты (*.py *.ps1 *.vbs *.js *.cmd)"
        LNK_FILES = "Ярлыки (*.lnk)"
        
        # Создаем новый диалог с принудительным сбросом директории
        dialog = QFileDialog(self.dialog)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if link_type == "program":
            dialog.setWindowTitle("Выбрать программу")
            dialog.setNameFilter(PROGRAM_FILES)
        elif link_type == "script":
            dialog.setWindowTitle("Выбрать скрипт")
            dialog.setNameFilter(SCRIPT_FILES)
        elif link_type == "folder":
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            dialog.setWindowTitle("Выбрать папку")
        elif link_type == "file":
            dialog.setWindowTitle("Выбрать файл")
            dialog.setNameFilter("Документы (*.txt *.pdf *.doc *.docx *.xls *.xlsx *.csv *.jpg *.png *.jpeg *.bmp *.gif);;Все файлы (*)")
        elif link_type == "chromeapp":
            dialog.setWindowTitle("Выбрать ярлык Chrome App")
            dialog.setNameFilter(LNK_FILES)
        
        # Принудительно устанавливаем директорию
        if start_dir:
            dialog.setDirectory(start_dir)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                path = selected_files[0]
            else:
                path = ""
        else:
            path = ""
                
        if path:
            normalized_path = path.replace('/', '\\')
            
            # Для типа "program" - разрешить .lnk ярлыки в реальные пути к .exe
            if link_type == "program" and normalized_path.lower().endswith('.lnk'):
                from app.utils.links.link_parser import _parse_lnk
                lnk_info = _parse_lnk(normalized_path)
                if lnk_info and lnk_info.get('path'):
                    # Используем реальный путь к .exe вместо ярлыка
                    normalized_path = lnk_info['path']
                    # Если есть аргументы в ярлыке, добавим их в поле аргументов
                    if lnk_info.get('args') and not self.dialog.ui.get_widget('args_le').text().strip():
                        self.dialog.ui.set_widget_value('args_le', lnk_info['args'])
            
            self.dialog.ui.set_widget_value('url_le', normalized_path)
            
            # Логика сохранения последних путей убрана - используются только пути по умолчанию
            
            name_widget = self.dialog.ui.get_widget('name_le')
            if not name_widget.text().strip():
                name = os.path.basename(normalized_path)
                if link_type in ("program", "chromeapp") or name.lower().endswith('.lnk'):
                    name = os.path.splitext(name)[0]
                name_widget.setText(name)
                
    def _on_path_changed(self, text: str) -> None:
        """Обработчик изменения пути."""
        self.dialog._processing_timer.stop()
        self.dialog._processing_timer.start(500)
        
    def _on_profile(self) -> None:
        """Обработчик кнопки выбора профиля."""
        import logging
        logger = logging.getLogger(__name__)
        
        from app.views.dialogs.browser_profile_dialog import BrowserProfileDialog
        
        dlg = BrowserProfileDialog(self.dialog)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.dialog.selected_profiles = dlg.get_selected_profiles()
            logger.debug(f"_on_profile: got {len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0} selected profiles")
            if self.dialog.selected_profiles:
                # Сохраняем выбранные профили
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(f"_on_profile: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}")
                
                profile_btn = self.dialog.ui.get_widget('profile_btn')
                profile_btn.setText(self.dialog._format_profile_text(self.dialog.selected_profiles))
                
    def _on_choose_icon(self) -> None:
        """Обработчик выбора иконки."""
        user_icons_dir = self.dialog.get_user_icons_dir()
        fname, icon = choose_icon_and_copy(self.dialog, user_icons_dir, file_filter="Изображения (*.png *.ico *.svg)")
        if not fname or not icon:
            return

        self.dialog.icon_name = fname
        btn = self.dialog.ui.get_widget('icon_btn')
        btn.setIcon(icon)
        
    def _update_sections(self) -> None:
        """Обновляет список разделов."""
        sphere_cb = self.dialog.ui.get_widget('sphere_cb')
        section_cb = self.dialog.ui.get_widget('section_cb')
        
        section_cb.clear()
        sphere_id = sphere_cb.currentData()
        
        if sphere_id and self.dialog.dialog_controller:
            sections = self.dialog.dialog_controller.get_sections_for_sphere(sphere_id)
            for sec in sections:
                section_cb.addItem(sec["name"], sec["id"])
                
        self._update_categories()
        
    def _update_categories(self) -> None:
        """Обновляет список категорий."""
        section_cb = self.dialog.ui.get_widget('section_cb')
        category_cb = self.dialog.ui.get_widget('category_cb')
        
        category_cb.clear()
        section_id = section_cb.currentData()
        
        if section_id and self.dialog.dialog_controller:
            categories = self.dialog.dialog_controller.get_categories_for_section(section_id)
            for cat in categories:
                category_cb.addItem(cat["name"], cat["id"])
                
    def _on_accept(self) -> None:
        """Обработчик подтверждения диалога."""
        form_data = self._collect_form_data()
        
        if hasattr(self.dialog, 'link_controller') and self.dialog.link_controller:
            result = self.dialog.link_controller.validate_and_save(form_data)
        else:
            result = self.dialog.dialog_controller.validate_and_save(form_data)
            
        if result['is_valid']:
            self.dialog.accept()
        else:
            # Специальный мягкий сценарий: пустая форма (без URL и имени)
            name_empty = not (form_data.get('name') or '').strip()
            url_empty = not (form_data.get('url') or '').strip()
            if name_empty and url_empty:
                DialogManager.show_info(
                    self.dialog,
                    "Пусто, как холодильник в конце месяца 🥶 — добавьте хоть адрес или название, и будет что сохранить!",
                    "Подсказка",
                    informative_text="Введите URL или имя и попробуйте снова.",
                    silent=True,
                )
            else:
                errors: List[str] = result.get('errors', [])
                error_text = "\n".join(errors)
                # Сформируем более понятный, короткий список проблемных полей
                problems = set()
                lower_errors = [e.lower() for e in errors]
                field_map = {
                    'name': 'Название',
                    'url': 'Адрес',
                    'link_type': 'Тип ссылки',
                    'type': 'Тип ссылки',
                    'category': 'Категория',
                    'category_id': 'Категория',
                    'args': 'Аргументы',
                }
                for key, label in field_map.items():
                    if any(key in e for e in lower_errors):
                        problems.add(label)
                # Составим конкретные подсказки по полям
                hint_map = {
                    'Название': "Укажите понятное название (например, 'Документация API').",
                    'Адрес': "Введите корректный URL вида https://example.com.",
                    'Тип ссылки': "Выберите тип ссылки (веб, файл, папка и т.д.).",
                    'Категория': "Выберите категорию для ссылки.",
                    'Аргументы': "Проверьте аргументы запуска — допустимы только безопасные значения.",
                }
                hints = [hint_map[p] for p in sorted(problems) if p in hint_map]
                # Ограничим длину подсказок, чтобы не перегружать окно
                short_hints = hints[:2]
                if problems:
                    main_msg = f"Заполните/исправьте: {', '.join(sorted(problems))}."
                    extra = (" " + " ".join(short_hints)) if short_hints else ""
                    info_msg = ("Проверьте подсказки возле полей." + extra +
                                " Полный список замечаний — в подробностях.")
                else:
                    main_msg = "Пожалуйста, проверьте данные перед сохранением."
                    info_msg = "Проверьте выделенные поля и всплывающие подсказки."

                DialogManager.show_info(
                    self.dialog,
                    main_msg,
                    "Небольшая подсказка",
                    informative_text=info_msg,
                    details=error_text,
                    silent=True,
                )

                # Перевести фокус на первое проблемное поле (если удаётся определить)
                try:
                    if 'Адрес' in problems:
                        self.dialog.ui.get_widget('url_le').setFocus()
                    elif 'Название' in problems:
                        self.dialog.ui.get_widget('name_le').setFocus()
                    elif 'Категория' in problems:
                        self.dialog.ui.get_widget('category_cb').setFocus()
                    elif 'Аргументы' in problems:
                        self.dialog.ui.get_widget('args_le').setFocus()
                except Exception:
                    pass
            
    def _collect_form_data(self) -> Dict[str, Any]:
        """Сбор данных из формы."""
        import logging
        logger = logging.getLogger(__name__)
        
        collected_name = self.dialog.ui.get_widget('name_le').text().strip()
        collected_args = self.dialog.ui.get_widget('args_le').text().strip()
        collected_link_id = self.dialog.link.get('id') if self.dialog.link else None
        
        # Проверяем, изменились ли аргументы (только для редактирования)
        if collected_link_id and hasattr(self.dialog, 'link') and self.dialog.link:
            original_args = self.dialog.link.get('args', '')
        
        logger.debug(f"_collect_form_data: collected name from UI='{collected_name}'")
        logger.debug(f"_collect_form_data: dialog.link={self.dialog.link}")
        logger.debug(f"_collect_form_data: dialog.selected_profiles count={len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0}")
        
        form_data = {
            'name': collected_name,
            'url': self.dialog.ui.get_widget('url_le').text().strip(),
            'link_type': self.dialog.link_type,
            'category_id': self.dialog.ui.get_widget('category_cb').currentData(),
            'args': collected_args,
            'is_favorite': self.dialog.ui.get_widget('fav_chk').isChecked(),
            'icon_name': self.dialog.icon_name,
            'notes': self.dialog.ui.get_widget('notes_te').toPlainText().strip(),
            'selected_profiles': self.dialog.selected_profiles,
            'link_id': collected_link_id,
            'last_used': self.dialog.link.get('last_used') if self.dialog.link else None,
            'position': self.dialog.link.get('position', 0) if self.dialog.link else 0
        }
        
        # Добавляем выбранные профили, если есть
        if hasattr(self.dialog, 'selected_profiles'):
            logger.debug(f"_collect_form_data: selected_profiles count={len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0}")
            if self.dialog.selected_profiles:
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(f"_collect_form_data: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}")
        else:
            logger.debug("_collect_form_data: no selected_profiles attribute")
        
        logger.debug(f"_collect_form_data: returning form_data with link_type={form_data.get('link_type')}")
        return form_data
        
    def set_link_type(self, link_type: str) -> None:
        """Программно выбрать тип ссылки и обновить UI."""
        if link_type not in {code for code, _ in self.dialog.LINK_TYPES}:
            return
            
        type_group = self.dialog.ui.widgets['type_group']
        for btn in type_group.buttons():
            if btn.property("link_type") == link_type:
                btn.setChecked(True)
                break
                
        self._on_type_changed(link_type)
        
    def trigger_link_processing(self, path: str) -> None:
        """Запуск обработки информации о ссылке."""
        if not path or self._is_processing:
            return
            
        if path == self._last_processed_path:
            return
            
        self._last_processed_path = path
        self._is_processing = True
        
        # Защита от race condition
        self._worker_task_id += 1
        task_id = self._worker_task_id
        
        # Отмена активного воркера
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except Exception as e:
                # Логируем ошибку отмены воркера, но продолжаем выполнение
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Ошибка при отмене воркера: {e}")
                
        worker = LinkInfoWorker(
            link_type=self.dialog.link_type,
            path=path,
            args=self.dialog.ui.get_widget('args_le').text().strip(),
            config_module=app_config,
            signals=self.signals
        )
        worker.task_id = task_id
        
        # Сигналы теперь подключены через self.signals
        pass
            
        self._active_worker = worker
        QThreadPool.globalInstance().start(worker)
        
    def _trigger_link_processing(self) -> None:
        """Внутренний метод для запуска обработки ссылки из таймера."""
        url = self.dialog.ui.get_widget('url_le').text().strip()
        self.trigger_link_processing(url)
        
    def _on_link_info_fetched(self, info: Dict) -> None:
        """Обработка полученной информации о ссылке."""
        self._is_processing = False
        self._active_worker = None
        
        name = info.get('name')
        if name and not self.dialog.ui.get_widget('name_le').text().strip():
            self.dialog.ui.set_widget_value('name_le', name)
            
        icon_path_str = info.get('icon')
        if icon_path_str and Path(icon_path_str).exists():
            self.dialog.icon_name = Path(icon_path_str).name
            set_icon_to_button(
                self.dialog.ui.get_widget('icon_btn'), 
                icon_path_str
            )
        else:
            # Фолбек на дефолтную иконку типа (без темы)
            default_icons = app_config.get_default_icons()
            default_icon_name = default_icons.get(self.dialog.link_type, default_icons.get("default"))
            if default_icon_name:
                root_path = self.dialog.get_ui_icons_dir() / default_icon_name
                if root_path.exists():
                    set_icon_to_button(
                        self.dialog.ui.get_widget('icon_btn'),
                        str(root_path)
                    )
                else:
                    self.dialog.ui.get_widget('icon_btn').setIcon(QIcon())
            
        if self.dialog.link_type in ('program', 'script', 'chromeapp'):
            args = info.get('args', '')
            if not self.dialog.ui.get_widget('args_le').text().strip():
                self.dialog.ui.set_widget_value('args_le', args)
                
        self._is_processing = False
        
    def _on_link_info_error(self, error_message: str) -> None:
        """Обработка ошибки получения информации."""
        self._is_processing = False
        self._active_worker = None
