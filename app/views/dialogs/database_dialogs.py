# app/views/dialogs/database_dialogs.py

from pathlib import Path
from typing import Optional, cast

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget


class DatabaseDialogs(QObject):
    """Диалоги для операций с базой данных."""

    def confirm_clear_favorites(self) -> bool:
        """Диалог подтверждения очистки избранного."""
        parent = cast(QWidget | None, self.parent())
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Очистить избранное")
        box.setText("Вы действительно хотите очистить избранное?")
        box.setInformativeText(
            "Действие необратимо. Все пометки 'Избранное' будут удалены."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def confirm_database_restore(self, backup_name: str) -> bool:
        """Диалог подтверждения восстановления базы данных."""
        parent = cast(QWidget | None, self.parent())
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Восстановление базы данных")
        box.setText("Восстановить базу данных из выбранной резервной копии?")
        box.setInformativeText(
            "Текущая база будет полностью заменена. Рекомендуется сделать бэкап перед восстановлением."
        )
        box.setDetailedText(f"Файл бэкапа: {backup_name}")
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def get_restore_file(self) -> Optional[Path]:
        """Показать диалог выбора файла для восстановления БД."""
        parent = cast(QWidget | None, self.parent())
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Выберите файл резервной копии для восстановления",
            "",
            "SQLite DB (*.db);;Все файлы (*)",
        )
        return Path(file_path) if file_path else None

    def get_connect_file(self) -> Optional[Path]:
        """Показать диалог выбора файла БД для подключения."""
        parent = cast(QWidget | None, self.parent())
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Выберите файл базы данных для подключения",
            "",
            "SQLite DB (*.db);;Все файлы (*)",
        )
        return Path(file_path) if file_path else None

    def get_save_location(self, default_name: str) -> Optional[Path]:
        """Показать диалог выбора места сохранения копии БД."""
        parent = cast(QWidget | None, self.parent())
        save_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Сохранить копию базы данных",
            default_name,
            "SQLite DB (*.db);;Все файлы (*)",
        )
        return Path(save_path) if save_path else None

    def get_icons_archive_location(
        self, default_name: str = "icons.zip"
    ) -> Optional[Path]:
        """Показать диалог выбора места сохранения архива иконок."""
        parent = cast(QWidget | None, self.parent())
        save_path, _ = QFileDialog.getSaveFileName(
            parent,
            "Сохранить архив иконок",
            default_name,
            "ZIP архив (*.zip);;Все файлы (*)",
        )
        return Path(save_path) if save_path else None

    def get_icons_archive_to_load(self) -> Optional[Path]:
        """Показать диалог выбора архива иконок для загрузки."""
        parent = cast(QWidget | None, self.parent())
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Выберите архив иконок для вставки",
            "",
            "ZIP архив (*.zip);;Все файлы (*)",
        )
        return Path(file_path) if file_path else None
