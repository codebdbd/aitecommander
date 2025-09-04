"""
Обработчики событий для LinkDialog.
Содержит логику обработки пользовательских действий.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QFileDialog

from app.config_data import app_config
from app.utils.db.api import run_db
from app.utils.links.link_parser import parse_local_link, _parse_lnk
from app.utils.links.parser.fetcher import fetch_web_link_info
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.selection import choose_icon_and_copy
from .icon_utils import make_icon

logger = logging.getLogger(__name__)


class LinkDialogSignals(QObject):
    """Локальные сигналы для LinkDialog (совместимы с легаси-слотами)."""

    link_info_finished: pyqtSignal = pyqtSignal(dict)
    simple_error: pyqtSignal = pyqtSignal(str)


class LinkDialogHandlers:
    """Обработчики событий для LinkDialog."""

    def __init__(self, dialog):
        """Инициализация обработчиков."""
        self.dialog = dialog
        self._last_processed_path = ""
        self._is_processing = False
        self._worker_task_id = 0
        self._active_worker = None
        # Локальные сигналы (замена StructureWorkerSignals)
        self.signals = LinkDialogSignals()
        # Подключаем сигналы
        self.signals.link_info_finished.connect(
            lambda info: self._on_link_info_fetched(info)
        )
        self.signals.simple_error.connect(lambda error: self._on_link_info_error(error))

    def _make_icon(self, icon_path_str: str) -> Optional[QIcon]:
        """Пытается создать QIcon по сохранённому пути.
        Поддерживает абсолютные пути и относительные относительно пользовательской и UI-папок иконок.
        """
        return make_icon(icon_path_str)

    def connect_signals(self) -> None:
        """Подключение сигналов к слотам."""
        # Тип ссылки
        self.dialog.ui.type_group.buttonClicked.connect(
            lambda b: self._on_type_changed(b.property("link_type"))
        )

        # URL изменение
        url_widget = self.dialog.ui.get_widget("url_le")
        url_widget.textChanged.connect(self._on_path_changed)
        # Немедленный триггер при завершении редактирования (Enter/потеря фокуса)
        try:
            url_widget.editingFinished.connect(self._trigger_link_processing)
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Ошибка подключения сигнала editingFinished для url_widget: {e}")

        # Кнопки
        self.dialog.ui.get_widget("browse_btn").clicked.connect(self._on_browse)
        self.dialog.ui.get_widget("profile_btn").clicked.connect(self._on_profile)
        self.dialog.ui.get_widget("icon_btn").clicked.connect(self._on_choose_icon)

        # Иерархия
        self.dialog.ui.get_widget("sphere_cb").currentIndexChanged.connect(
            self._update_sections
        )
        self.dialog.ui.get_widget("section_cb").currentIndexChanged.connect(
            self._update_categories
        )

        # Кнопки диалога
        self.dialog.ui.get_widget("button_box").accepted.connect(self._on_accept)
        self.dialog.ui.get_widget("button_box").rejected.connect(self.dialog.reject)

    def _on_type_changed(self, link_type: str) -> None:
        """Обработчик изменения типа ссылки."""
        self.dialog.link_type = link_type

        # Очистка полей при смене типа
        self.dialog.ui.set_widget_value("url_le", "")
        self.dialog.ui.set_widget_value("name_le", "")
        self.dialog.ui.set_widget_value("args_le", "")

        # Сброс состояния обработки ссылок для возможности повторного автозаполнения
        self._last_processed_path = ""
        self._is_processing = False

        # Отмена активной задачи при смене типа ссылки
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except (AttributeError, RuntimeError) as e:
                logger.debug(f"Ошибка отмены активного воркера: {e}")
            self._active_worker = None

        # Установка иконки по умолчанию через централизованный резолвер
        try:
            resolved_icon_path = resolve_icon_for_link(
                {"type": link_type, "icon_path": ""}
            )
        except (AttributeError, KeyError, ValueError) as e:
            logger.warning(f"Ошибка резолвинга иконки для типа {link_type}: {e}")
            resolved_icon_path = ""
        self.dialog.icon_name = (
            Path(resolved_icon_path).name if resolved_icon_path else ""
        )
        if resolved_icon_path and Path(resolved_icon_path).exists():
            set_icon_to_button(
                self.dialog.ui.get_widget("icon_btn"), resolved_icon_path
            )
        else:
            self.dialog.ui.get_widget("icon_btn").setIcon(QIcon())

        self._update_ui_state()

    def _update_ui_state(self) -> None:
        """Обновляет состояние UI в зависимости от типа ссылки."""
        is_web = self.dialog.link_type == "web"

        profile_btn = self.dialog.ui.get_widget("profile_btn")
        browse_btn = self.dialog.ui.get_widget("browse_btn")
        args_le = self.dialog.ui.get_widget("args_le")
        args_label = self.dialog.ui.get_widget("args_label")

        profile_btn.setVisible(is_web)

        # Кнопка 'Обзор' для определенных типов
        browse_btn.setVisible(
            self.dialog.link_type
            in ("file", "folder", "program", "script", "chromeapp")
        )

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
        default_paths = app_config.settings.get_default_browse_paths()
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
            dialog.setNameFilter(
                "Документы (*.txt *.pdf *.doc *.docx *.xls *.xlsx *.csv *.jpg *.png *.jpeg *.bmp *.gif);;Все файлы (*)"
            )
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
            normalized_path = path.replace("/", "\\")

            # Для типа "program" - разрешить .lnk ярлыки в реальные пути к .exe
            if link_type == "program" and normalized_path.lower().endswith(".lnk"):
                lnk_info = _parse_lnk(normalized_path)
                if lnk_info and lnk_info.get("path"):
                    # Используем реальный путь к .exe вместо ярлыка
                    normalized_path = lnk_info["path"]
                    # Если есть аргументы в ярлыке, добавим их в поле аргументов
                    if (
                        lnk_info.get("args")
                        and not self.dialog.ui.get_widget("args_le").text().strip()
                    ):
                        self.dialog.ui.set_widget_value("args_le", lnk_info["args"])

            self.dialog.ui.set_widget_value("url_le", normalized_path)

            # Логика сохранения последних путей убрана - используются только пути по умолчанию

            name_widget = self.dialog.ui.get_widget("name_le")
            if not name_widget.text().strip():
                name = os.path.basename(normalized_path)
                if link_type in ("program", "chromeapp") or name.lower().endswith(
                    ".lnk"
                ):
                    name = os.path.splitext(name)[0]
                name_widget.setText(name)

    def _on_path_changed(self, text: str) -> None:
        """Обработчик изменения пути."""
        self.dialog._processing_timer.stop()
        # Уменьшаем задержку дебаунса, чтобы успеть запустить воркер до закрытия диалога
        self.dialog._processing_timer.start(300)

    def _on_profile(self) -> None:
        """Обработчик кнопки выбора профиля."""

        from app.views.dialogs.browser_profile_dialog import BrowserProfileDialog

        dlg = BrowserProfileDialog(self.dialog)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.dialog.selected_profiles = dlg.get_selected_profiles()
            logger.debug(
                f"_on_profile: got {len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0} selected profiles"
            )
            if self.dialog.selected_profiles:
                # Сохраняем выбранные профили
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(
                        f"_on_profile: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}"
                    )

                profile_btn = self.dialog.ui.get_widget("profile_btn")
                profile_btn.setText(
                    self.dialog._format_profile_text(self.dialog.selected_profiles)
                )

    def _on_choose_icon(self) -> None:
        """Обработчик выбора иконки."""
        user_icons_dir = self.dialog.get_user_icons_dir()
        fname, icon = choose_icon_and_copy(
            self.dialog, user_icons_dir, file_filter="Изображения (*.png *.ico *.svg)"
        )
        if not fname or not icon:
            return

        self.dialog.icon_name = fname
        btn = self.dialog.ui.get_widget("icon_btn")
        btn.setIcon(icon)

    def _update_sections(self) -> None:
        """Обновляет список разделов."""
        sphere_cb = self.dialog.ui.get_widget("sphere_cb")
        section_cb = self.dialog.ui.get_widget("section_cb")

        section_cb.clear()
        sphere_id = sphere_cb.currentData()

        if sphere_id and self.dialog.dialog_controller:
            sections = self.dialog.dialog_controller.get_sections_for_sphere(sphere_id)
            for sec in sections:
                icon_path_val = (
                    sec["icon_path"]
                    if (hasattr(sec, "keys") and "icon_path" in sec.keys())
                    else ""
                )
                icon = self._make_icon(icon_path_val)
                if icon:
                    section_cb.addItem(icon, sec["name"], sec["id"])
                else:
                    section_cb.addItem(sec["name"], sec["id"])

        self._update_categories()

    def _update_categories(self) -> None:
        """Обновляет список категорий."""
        section_cb = self.dialog.ui.get_widget("section_cb")
        category_cb = self.dialog.ui.get_widget("category_cb")

        category_cb.clear()
        section_id = section_cb.currentData()

        if section_id and self.dialog.dialog_controller:
            categories = self.dialog.dialog_controller.get_categories_for_section(
                section_id
            )
            for cat in categories:
                icon_path_val = (
                    cat["icon_path"]
                    if (hasattr(cat, "keys") and "icon_path" in cat.keys())
                    else ""
                )
                icon = self._make_icon(icon_path_val)
                if icon:
                    category_cb.addItem(icon, cat["name"], cat["id"])
                else:
                    category_cb.addItem(cat["name"], cat["id"])

    def _on_accept(self) -> None:
        """Обработчик подтверждения диалога (orchestration логика)."""
        form_data = self._build_form_data()
        result = self._validate_and_save_data(form_data)
        
        if result["is_valid"]:
            self.dialog.accept()
        else:
            self._handle_validation_errors(form_data, result)

    def _build_form_data(self) -> Dict[str, Any]:
        """Формирует данные формы из UI компонентов."""
        return self._collect_form_data()

    def _validate_and_save_data(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Проверяет и сохраняет данные формы."""
        if hasattr(self.dialog, "link_controller") and self.dialog.link_controller:
            return self.dialog.link_controller.validate_and_save(form_data)
        else:
            return self.dialog.dialog_controller.validate_and_save(form_data)

    def _handle_validation_errors(self, form_data: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Обрабатывает ошибки валидации и показывает соответствующие сообщения."""
        # Специальный мягкий сценарий: пустая форма (без URL и имени)
        name_empty = not (form_data.get("name") or "").strip()
        url_empty = not (form_data.get("url") or "").strip()
        
        if name_empty and url_empty:
            self._show_empty_form_message()
        else:
            errors = result.get("errors", [])
            problems = self._extract_problematic_fields(errors)
            self._show_validation_error_message(errors, problems)
            self._focus_problematic_field(problems)

    def _show_empty_form_message(self) -> None:
        """Показывает сообщение для пустой формы."""
        self.dialog.show_info(
            "Пусто, как холодильник в конце месяца 🥶 — добавьте хоть адрес или название, и будет что сохранить!",
            "Подсказка",
            informative_text="Введите URL или имя и попробуйте снова.",
            silent=True,
        )

    def _extract_problematic_fields(self, errors: List[str]) -> set:
        """Извлекает проблемные поля из списка ошибок."""
        problems = set()
        lower_errors = [e.lower() for e in errors]
        field_map = {
            "name": "Название",
            "url": "Адрес",
            "link_type": "Тип ссылки",
            "type": "Тип ссылки",
            "category": "Категория",
            "category_id": "Категория",
            "args": "Аргументы",
        }
        for key, label in field_map.items():
            if any(key in e for e in lower_errors):
                problems.add(label)
        return problems

    def _generate_error_messages(self, problems: set) -> tuple[str, str]:
        """Генерирует сообщения об ошибках на основе проблемных полей."""
        hint_map = {
            "Название": "Укажите понятное название (например, 'Документация API').",
            "Адрес": "Введите корректный URL вида https://example.com.",
            "Тип ссылки": "Выберите тип ссылки (веб, файл, папка и т.д.).",
            "Категория": "Выберите категорию для ссылки.",
            "Аргументы": "Проверьте аргументы запуска — допустимы только безопасные значения.",
        }
        hints = [hint_map[p] for p in sorted(problems) if p in hint_map]
        # Ограничим длину подсказок, чтобы не перегружать окно
        short_hints = hints[:2]
        
        if problems:
            main_msg = f"Заполните/исправьте: {', '.join(sorted(problems))}."
            extra = (" " + " ".join(short_hints)) if short_hints else ""
            info_msg = (
                "Проверьте подсказки возле полей."
                + extra
                + " Полный список замечаний — в подробностях."
            )
        else:
            main_msg = "Пожалуйста, проверьте данные перед сохранением."
            info_msg = "Проверьте выделенные поля и всплывающие подсказки."
        
        return main_msg, info_msg

    def _show_validation_error_message(self, errors: List[str], problems: set) -> None:
        """Показывает сообщение об ошибках валидации."""
        error_text = "\n".join(errors)
        main_msg, info_msg = self._generate_error_messages(problems)
        
        self.dialog.show_info(
            main_msg,
            "Небольшая подсказка",
            informative_text=info_msg,
            details=error_text,
            silent=True,
        )

    def _focus_problematic_field(self, problems: set) -> None:
        """Устанавливает фокус на первое проблемное поле."""
        try:
            if "Адрес" in problems:
                self.dialog.ui.get_widget("url_le").setFocus()
            elif "Название" in problems:
                self.dialog.ui.get_widget("name_le").setFocus()
            elif "Категория" in problems:
                self.dialog.ui.get_widget("category_cb").setFocus()
            elif "Аргументы" in problems:
                self.dialog.ui.get_widget("args_le").setFocus()
        except (AttributeError, RuntimeError) as e:
            logger.warning(f"Ошибка установки фокуса на проблемное поле: {e}")

    def _collect_form_data(self) -> Dict[str, Any]:
        """Сбор данных из формы."""

        collected_name = self.dialog.ui.get_widget("name_le").text().strip()
        collected_args = self.dialog.ui.get_widget("args_le").text().strip()
        collected_link_id = self.dialog.link.get("id") if self.dialog.link else None

        logger.debug(f"_collect_form_data: collected name from UI='{collected_name}'")
        logger.debug(f"_collect_form_data: dialog.link={self.dialog.link}")
        logger.debug(
            f"_collect_form_data: dialog.selected_profiles count={len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0}"
        )

        form_data = {
            "name": collected_name,
            "url": self.dialog.ui.get_widget("url_le").text().strip(),
            "link_type": self.dialog.link_type,
            "category_id": self.dialog.ui.get_widget("category_cb").currentData(),
            "args": collected_args,
            "is_favorite": self.dialog.ui.get_widget("fav_chk").isChecked(),
            "icon_name": self.dialog.icon_name,
            "notes": self.dialog.ui.get_widget("notes_te").toPlainText().strip(),
            "selected_profiles": self.dialog.selected_profiles,
            "link_id": collected_link_id,
            "last_used": self.dialog.link.get("last_used")
            if self.dialog.link
            else None,
            "position": self.dialog.link.get("position", 0) if self.dialog.link else 0,
        }

        # Добавляем выбранные профили, если есть
        if hasattr(self.dialog, "selected_profiles"):
            logger.debug(
                f"_collect_form_data: selected_profiles count={len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0}"
            )
            if self.dialog.selected_profiles:
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(
                        f"_collect_form_data: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}"
                    )
        else:
            logger.debug("_collect_form_data: no selected_profiles attribute")

        logger.debug(
            f"_collect_form_data: returning form_data with link_type={form_data.get('link_type')}"
        )
        return form_data

    def set_link_type(self, link_type: str) -> None:
        """Программно выбрать тип ссылки и обновить UI."""
        if link_type not in {code for code, _ in self.dialog.LINK_TYPES}:
            return

        type_group = self.dialog.ui.widgets["type_group"]
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
        _task_id = self._worker_task_id

        # Отмена активной задачи
        if self._active_worker:
            try:
                self._active_worker.cancel()
            except Exception as e:
                # Логируем ошибку отмены воркера, но продолжаем выполнение
                logger.debug(f"Ошибка при отмене воркера: {e}")

        link_type = self.dialog.link_type
        args_val = self.dialog.ui.get_widget("args_le").text().strip()

        def _do_work() -> Dict[str, Any]:
            try:
                if link_type == "web":
                    # Иконку подберём отложенно, чтобы не блокировать UI
                    info = fetch_web_link_info(
                        path,
                        app_config,
                        force_refresh=False,
                        defer_icon=True,
                        on_icon_ready=lambda icon_path: self.signals.link_info_finished.emit(
                            {"title": "", "icon": icon_path}
                        ),
                    )
                    return {"title": info.get("title"), "icon": info.get("icon")}
                # Локальные пути
                info = parse_local_link(link_type, path, app_config, args=args_val)
                return info or {"name": "", "icon": ""}
            except Exception as e:
                # Пробросим как исключение, on_error обработает
                raise e

        handle = run_db(
            _do_work,
            description=f"link_info:{link_type}",
            on_finished=lambda info: self.signals.link_info_finished.emit(info),
            on_error=lambda e: self.signals.simple_error.emit(str(e)),
        )

        # Сохраняем handle активного воркера
        self._active_worker = handle

    def _trigger_link_processing(self) -> None:
        """Внутренний метод для запуска обработки ссылки из таймера."""
        url = self.dialog.ui.get_widget("url_le").text().strip()
        self.trigger_link_processing(url)

    def _on_link_info_fetched(self, info: Dict) -> None:
        """Обработка полученной информации о ссылке."""
        self._is_processing = False
        self._active_worker = None

        title = info.get("title") or info.get("name")
        if title and not self.dialog.ui.get_widget("name_le").text().strip():
            self.dialog.ui.set_widget_value("name_le", title)

        icon_path_str = info.get("icon")
        if icon_path_str and Path(icon_path_str).exists():
            self.dialog.icon_name = Path(icon_path_str).name
            set_icon_to_button(self.dialog.ui.get_widget("icon_btn"), icon_path_str)
        else:
            # Фолбек через централизованный резолвер
            try:
                resolved_icon_path = resolve_icon_for_link(
                    {
                        "type": self.dialog.link_type,
                        "icon_path": self.dialog.icon_name or "",
                    }
                )
            except (AttributeError, KeyError, ValueError) as e:
                logger.warning(f"Ошибка резолвинга иконки для ссылки: {e}")
                resolved_icon_path = ""
            if resolved_icon_path and Path(resolved_icon_path).exists():
                set_icon_to_button(
                    self.dialog.ui.get_widget("icon_btn"), resolved_icon_path
                )
            else:
                self.dialog.ui.get_widget("icon_btn").setIcon(QIcon())

        if self.dialog.link_type in ("program", "script", "chromeapp"):
            args = info.get("args", "")
            if not self.dialog.ui.get_widget("args_le").text().strip():
                self.dialog.ui.set_widget_value("args_le", args)

        self._is_processing = False

    def _on_link_info_error(self, error_message: str) -> None:
        """Обработка ошибки получения информации."""
        self._is_processing = False
        self._active_worker = None
