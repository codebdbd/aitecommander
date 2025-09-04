"""
Миксин для обработки кнопки "Обзор" в LinkDialogHandlers.
"""
import os
from PyQt6.QtWidgets import QFileDialog
from app.config_data import app_config
from app.utils.links.link_parser import _parse_lnk


class FileDialogMixin:
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
                import os as _os
                name = _os.path.basename(normalized_path)
                if link_type in ("program", "chromeapp") or name.lower().endswith(
                    ".lnk"
                ):
                    name = _os.path.splitext(name)[0]
                name_widget.setText(name)
