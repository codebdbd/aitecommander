# app/views/dialogs/database_dialogs.py

from pathlib import Path
from typing import Optional, cast

from PyQt6.QtCore import QCoreApplication, QObject
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from app.utils.i18n.common import tr as tr_common
from app.utils.share_paths import ensure_service_root, get_desktop_dir, get_entity_dir
from app.views.windows.dialogs.base_dialog import apply_uniform_height_to_message_box

_TR_CONTEXT = "DatabaseDialogs"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class DatabaseDialogs(QObject):
    """Dialogs for database operations."""

    def _get_service_dir(self, entity: str) -> str:
        desktop = get_desktop_dir()
        if not desktop:
            return ""
        root = ensure_service_root(desktop)
        if not root:
            return ""
        return str(get_entity_dir(root, entity))

    def confirm_clear_favorites(self) -> bool:
        """Ask the user to confirm clearing favorites."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr_common("Clear favorites"))
        box.setText(QCoreApplication.translate("DatabaseDialogs", "Do you really want to clear favorites?"))
        box.setInformativeText(
            QCoreApplication.translate("DatabaseDialogs", "This action cannot be undone. All Favorite marks will be removed.")
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        apply_uniform_height_to_message_box(box)
        return box.exec() == QMessageBox.StandardButton.Ok

    def confirm_database_restore(self, backup_name: str) -> bool:
        """Ask for confirmation to restore the database."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr_common("Database restore"))
        box.setText(QCoreApplication.translate("DatabaseDialogs", "Restore the database from the selected backup?"))
        box.setInformativeText(
            QCoreApplication.translate("DatabaseDialogs", 
                "The current database will be replaced. "
                "A backup will be created before the restore."
            )
        )
        box.setDetailedText(QCoreApplication.translate("DatabaseDialogs", "Backup file: {name}").format(name=backup_name))
        box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        apply_uniform_height_to_message_box(box)
        return box.exec() == QMessageBox.StandardButton.Ok

    def get_restore_file(self) -> Optional[Path]:
        """Return the file path for restoring the database."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        start_dir = self._get_service_dir("database")
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            QCoreApplication.translate("DatabaseDialogs", "Select a backup file to restore"),
            start_dir,
            QCoreApplication.translate("DatabaseDialogs", "SQLite DB (*.db);;All files (*)"),
        )
        return Path(file_path) if file_path else None

    def get_connect_file(self) -> Optional[Path]:
        """Return the database file path to connect to."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        start_dir = self._get_service_dir("database")
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            QCoreApplication.translate("DatabaseDialogs", "Select a database file to connect"),
            start_dir,
            QCoreApplication.translate("DatabaseDialogs", "SQLite DB (*.db);;All files (*)"),
        )
        return Path(file_path) if file_path else None

    def get_save_location(self, default_name: str) -> Optional[Path]:
        """Return the destination path for saving a database copy."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        start_dir = self._get_service_dir("database")
        start_path = str(Path(start_dir) / default_name) if start_dir else default_name
        save_path, _ = QFileDialog.getSaveFileName(
            parent,
            QCoreApplication.translate("DatabaseDialogs", "Save database copy"),
            start_path,
            QCoreApplication.translate("DatabaseDialogs", "SQLite DB (*.db);;All files (*)"),
        )
        return Path(save_path) if save_path else None

    def get_icons_archive_location(
        self, default_name: str = "icons.zip"
    ) -> Optional[Path]:
        """Return the destination path for saving icons archive."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        start_dir = self._get_service_dir("icons")
        start_path = str(Path(start_dir) / default_name) if start_dir else default_name
        save_path, _ = QFileDialog.getSaveFileName(
            parent,
            QCoreApplication.translate("DatabaseDialogs", "Save icons archive"),
            start_path,
            QCoreApplication.translate("DatabaseDialogs", "ZIP archive (*.zip);;All files (*)"),
        )
        return Path(save_path) if save_path else None

    def get_icons_archive_to_load(self) -> Optional[Path]:
        """Return the archive path when loading icons."""
        parent = cast(QWidget, self.parent()) if self.parent() else None
        start_dir = self._get_service_dir("icons")
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            QCoreApplication.translate("DatabaseDialogs", "Select an icons archive to import"),
            start_dir,
            QCoreApplication.translate("DatabaseDialogs", "ZIP archive (*.zip);;All files (*)"),
        )
        return Path(file_path) if file_path else None
