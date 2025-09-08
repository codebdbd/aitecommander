"""
Миксин для обработки кнопки "Обзор" в LinkDialogHandlers.
"""
import logging
import os

from PyQt6.QtWidgets import QFileDialog

from app.config_data import app_config
from app.models.link_type import LinkType
from app.utils.links.link_parser import parse_lnk

logger = logging.getLogger(__name__)


PROGRAM_FILES = "Программы (*.exe *.bat *.com *.msi *.lnk)"
SCRIPT_FILES = "Скрипты (*.py *.ps1 *.vbs *.js *.cmd)"
LNK_FILES = "Ярлыки (*.lnk)"
DOC_FILES = (
    "Документы (*.txt *.pdf *.doc *.docx *.xls *.xlsx *.csv *.jpg *.png *.jpeg *.bmp *.gif);;Все файлы (*)"
)

# Конфигурации диалога по типам ссылок
BROWSE_CONFIG = {
    "program": {
        "title": "Выбрать программу",
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": PROGRAM_FILES,
    },
    "script": {
        "title": "Выбрать скрипт",
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": SCRIPT_FILES,
    },
    "folder": {
        "title": "Выбрать папку",
        "mode": QFileDialog.FileMode.Directory,
        "filter": None,
    },
    "file": {
        "title": "Выбрать файл",
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": DOC_FILES,
    },
    "chromeapp": {
        "title": "Выбрать ярлык Chrome App",
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": LNK_FILES,
    },
}


class FileDialogMixin:
    def _on_browse(self) -> None:
        """Обработчик кнопки 'Обзор'."""
        lt = LinkType.from_value(self.dialog.link_type)
        path = ""

        # Получить путь по умолчанию из конфига
        default_paths = app_config.settings.get_default_browse_paths()
        start_dir = default_paths.get(lt.value, "")

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

        # Создаем новый диалог с принудительным сбросом директории
        dialog = QFileDialog(self.dialog)
        cfg = BROWSE_CONFIG.get(lt.value) or {
            "title": "Выбрать файл",
            "mode": QFileDialog.FileMode.ExistingFile,
            "filter": DOC_FILES,
        }
        dialog.setFileMode(cfg["mode"])
        dialog.setWindowTitle(cfg["title"])
        if cfg.get("filter"):
            dialog.setNameFilter(cfg["filter"])

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
            if lt == LinkType.PROGRAM and normalized_path.lower().endswith(".lnk"):
                try:
                    lnk_info = parse_lnk(normalized_path)
                except (FileNotFoundError, PermissionError, OSError, ValueError, RuntimeError) as e:
                    # Логируем проблему разбора ярлыка, но не прерываем сценарий выбора файла
                    logger.warning("parse_lnk: не удалось разобрать ярлык '%s': %s", normalized_path, e)
                    lnk_info = None
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
                if lt in (LinkType.PROGRAM, LinkType.CHROMEAPP) or name.lower().endswith(
                    ".lnk"
                ):
                    name = os.path.splitext(name)[0]
                name_widget.setText(name)

