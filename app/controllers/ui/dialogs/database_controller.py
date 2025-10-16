# app/controllers/database_controller.py

import os
import shutil
import zipfile
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.db import Database
from app.utils.db.db_error_handler import handle_db_error
from app.utils.ui.icon.path_service import icon_path_service
from app.views.windows.dialogs.database_dialogs import DatabaseDialogs


class DatabaseController(QObject):
    """Controller for managing database and icon operations.

    Uses signals to notify UI about operations instead of direct
    access to main_window.
    """

    # UI notification signals
    database_restored = pyqtSignal(object)  # Database - new DB after restore
    database_connected = pyqtSignal(object)  # Database - new DB after connection
    database_saved = pyqtSignal(str)  # str - path to saved copy
    favorites_cleared = pyqtSignal()  # Favorites cleared
    icons_exported = pyqtSignal(str)  # str - path to exported archive
    icons_imported = pyqtSignal(int)  # int - number of imported icons
    operation_error = pyqtSignal(str, str)  # str, str - title, error message
    operation_success = pyqtSignal(
        str, str
    )  # str, str - title, success message

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.dialogs = DatabaseDialogs(parent)

    def handle_clear_favorites(self):
        """Favorites clearing handler.

        No confirmation and no info dialog: immediately sends
        signal to clear favorites. UI will perform clearing through controllers.
        """
        # Send signal - UI will handle clearing and updating itself
        self.favorites_cleared.emit()

    def handle_restore_database(self):
        """Database restore handler from backup."""
        from app.views.windows.dialogs.restore_db_dialog import RestoreDbDialog

        dlg = RestoreDbDialog(parent=self.parent())
        if dlg.exec() == dlg.DialogCode.Accepted:
            selected = dlg.get_selected_backup()
            if selected:
                self._perform_database_restore(selected)

    def _perform_database_restore(self, backup_path):
        """Perform database restore.

        Business logic only. UI is updated via signals.
        """
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self.operation_error.emit("Error", "Database path not found.")
            return

        if self.dialogs.confirm_database_restore(backup_path.name):
            try:
                # Close old connection
                self.db.close()

                # Copy backup
                shutil.copy2(backup_path, db_path)

                # Create new database connection
                new_db = Database()
                self.db = new_db

                # Notify UI via signal - it will update all dependencies
                self.database_restored.emit(new_db)
                self.operation_success.emit(
                    "Done", f"Database restored from backup:\n{backup_path.name}"
                )

            except Exception as e:
                self.operation_error.emit("Error", f"Restore error: {e}")

    def handle_connect_database(self):
        """Another database connection handler."""
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self.operation_error.emit("Error", "Database path not found.")
            return

        file_path = self.dialogs.get_connect_file()
        if file_path:
            self._perform_database_connection(str(file_path), db_path)

    def _perform_database_connection(self, file_path: str, db_path: str):
        """Perform database connection.

        Business logic only. UI is updated via signals.
        """
        backup_path = db_path + ".bak"
        try:
            # Close database connection
            self.db.close()
            # Make backup of current database
            shutil.copy2(db_path, backup_path)
            # Replace database file
            shutil.copy2(file_path, db_path)

            new_db = Database()
            self.db = new_db

            # Notify UI through signal - it will update all dependencies
            self.database_connected.emit(new_db)

        except Exception as e:
            # Use centralized error handler
            if not handle_db_error(e, self):
                # In case of error restore old database
                try:
                    shutil.copy2(backup_path, db_path)
                except Exception:
                    pass
                self.operation_error.emit(
                    "Error",
                    f"Database connection error: {e}\nOld database restored.",
                )

    def handle_save_database(self):
        """Database copy save handler."""
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self.operation_error.emit("Error", "Database path not found.")
            return

        default_name = (
            db_path.split("/")[-1] if "/" in db_path else db_path.split("\\")[-1]
        )
        save_path = self.dialogs.get_save_location(default_name)

        if save_path:
            try:
                shutil.copy2(db_path, str(save_path))
                self.database_saved.emit(str(save_path))
                self.operation_success.emit(
                    "Done", f"Database copy saved:\n{save_path}"
                )
            except Exception as e:
                self.operation_error.emit("Error", f"Save error: {e}")

    def handle_save_icons(self):
        """Icon archive save handler."""
        icons_dir = icon_path_service.get_user_icons_dir()
        if not Path(icons_dir).is_dir():
            self.operation_error.emit("Error", f"Icons folder not found: {icons_dir}")
            return

        save_path = self.dialogs.get_icons_archive_location("icons.zip")

        if save_path:
            try:
                with zipfile.ZipFile(str(save_path), "w", zipfile.ZIP_DEFLATED) as zipf:
                    for fname in os.listdir(icons_dir):
                        fpath = Path(icons_dir) / fname
                        if fpath.is_file():
                            zipf.write(str(fpath), fname)
                self.icons_exported.emit(str(save_path))
                self.operation_success.emit(
                    "Done", f"Icon archive saved to:\n{save_path}"
                )
            except Exception as e:
                self.operation_error.emit("Error", f"Archive creation error: {e}")

    def handle_load_icons(self):
        """Icon archive load handler."""
        icons_dir = icon_path_service.get_user_icons_dir()
        Path(icons_dir).mkdir(parents=True, exist_ok=True)

        zip_path = self.dialogs.get_icons_archive_to_load()

        if zip_path:
            try:
                icon_count = 0
                with zipfile.ZipFile(zip_path, "r") as zipf:
                    zipf.extractall(icons_dir)
                    icon_count = len(zipf.namelist())
                self.icons_imported.emit(icon_count)
                self.operation_success.emit(
                    "Done", f"Icons successfully added to: {icons_dir}"
                )
            except Exception as e:
                self.operation_error.emit("Error", f"Archive load error: {e}")
