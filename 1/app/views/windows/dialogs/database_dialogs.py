# app/views/dialogs/database_dialogs.py

from pathlib import Path
from typing import Optional, cast

from PyQt6.QtCore import QCoreApplication, QObject
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

_TR_CONTEXT = "DatabaseDialogs"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class DatabaseDialogs(QObject):
    """Dialogs for database operations."""

    def confirm_clear_favorites(self) -> bool:
        """Ask the user to confirm clearing favorites."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(_tr("Clear favorites"))
        box.setText(_tr("Do you really want to clear favorites?"))
        box.setInformativeText(
            _tr("This action cannot be undone. All Favorite marks will be removed.")
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def confirm_database_restore(self, backup_name: str) -> bool:
        """Ask for confirmation to restore the database."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(_tr("Database restore"))
        box.setText(_tr("Restore the database from the selected backup?"))
        box.setInformativeText(
            _tr(
                "The current database will be fully replaced. It is recommended to back up before restoring."
            )
        )
        box.setDetailedText(_tr("Backup file: {name}").format(name=backup_name))
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def get_restore_file(self) -> Optional[Path]:
        """Return the file path for restoring the database."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            _tr("Select a backup file to restore"),
            "",
            _tr("SQLite DB (*.db);;All files (*)"),
        )
        return Path(file_path) if file_path else None

    def get_connect_file(self) -> Optional[Path]:
        """Return the database file path to connect to."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            _tr("Select a database file to connect"),
            "",
            _tr("SQLite DB (*.db);;All files (*)"),
        )
        return Path(file_path) if file_path else None

    def get_save_location(self, default_name: str) -> Optional[Path]:
        """Return the destination path for saving a database copy."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        save_path, _ = QFileDialog.getSaveFileName(
            parent,
            _tr("Save database copy"),
            default_name,
            _tr("SQLite DB (*.db);;All files (*)"),
        )
        return Path(save_path) if save_path else None

    def get_icons_archive_location(
        self, default_name: str = "icons.zip"
    ) -> Optional[Path]:
        """Return the destination path for saving icons archive."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        save_path, _ = QFileDialog.getSaveFileName(
            parent,
            _tr("Save icons archive"),
            default_name,
            _tr("ZIP archive (*.zip);;All files (*)"),
        )
        return Path(save_path) if save_path else None

    def get_icons_archive_to_load(self) -> Optional[Path]:
        """Return the archive path when loading icons."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            _tr("Select an icons archive to import"),
            "",
            _tr("ZIP archive (*.zip);;All files (*)"),
        )
        return Path(file_path) if file_path else None
