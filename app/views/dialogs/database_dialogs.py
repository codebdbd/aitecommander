# app/views/dialogs/database_dialogs.py

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QFileDialog

from app.utils.ui.dialog_manager import DialogManager


class DatabaseDialogs(QObject):
    """Диалоги для операций с базой данных."""
    
    def confirm_clear_favorites(self) -> bool:
        """Диалог подтверждения очистки избранного."""
        return DialogManager.ask_confirmation(
            self.parent(),
            "Вы действительно хотите очистить избранное?",
            "Очистить избранное",
            informative_text="Действие необратимо. Все пометки 'Избранное' будут удалены.",
        )
    
    def confirm_database_restore(self, backup_name: str) -> bool:
        """Диалог подтверждения восстановления базы данных."""
        return DialogManager.ask_confirmation(
            self.parent(),
            "Восстановить базу данных из выбранной резервной копии?",
            "Восстановление базы данных",
            informative_text="Текущая база будет полностью заменена. Рекомендуется сделать бэкап перед восстановлением.",
            details=f"Файл бэкапа: {backup_name}",
        )
    
    def get_restore_file(self) -> Optional[Path]:
        """Показать диалог выбора файла для восстановления БД."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Выберите файл резервной копии для восстановления",
            "",
            "SQLite DB (*.db);;Все файлы (*)"
        )
        return Path(file_path) if file_path else None
    
    def get_connect_file(self) -> Optional[Path]:
        """Показать диалог выбора файла БД для подключения."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Выберите файл базы данных для подключения",
            "",
            "SQLite DB (*.db);;Все файлы (*)"
        )
        return Path(file_path) if file_path else None
    
    def get_save_location(self, default_name: str) -> Optional[Path]:
        """Показать диалог выбора места сохранения копии БД."""
        save_path, _ = QFileDialog.getSaveFileName(
            self.parent(),
            "Сохранить копию базы данных",
            default_name,
            "SQLite DB (*.db);;Все файлы (*)"
        )
        return Path(save_path) if save_path else None
    
    def get_icons_archive_location(self, default_name: str = "icons.zip") -> Optional[Path]:
        """Показать диалог выбора места сохранения архива иконок."""
        save_path, _ = QFileDialog.getSaveFileName(
            self.parent(),
            "Сохранить архив иконок",
            default_name,
            "ZIP архив (*.zip);;Все файлы (*)"
        )
        return Path(save_path) if save_path else None
    
    def get_icons_archive_to_load(self) -> Optional[Path]:
        """Показать диалог выбора архива иконок для загрузки."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.parent(),
            "Выберите архив иконок для вставки",
            "",
            "ZIP архив (*.zip);;Все файлы (*)"
        )
        return Path(file_path) if file_path else None
