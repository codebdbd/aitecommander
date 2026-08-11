# app/controllers/database_controller.py

import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QObject,
    pyqtSignal,
    pyqtSlot,
)

from app.core.worker_manager import WorkerManager
from app.models.db import Database
from app.services.database_restore_worker import DatabaseRestoreWorker
from app.utils.ui.db_errors import handle_db_error
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.utils.ui.icon.file_lock import icon_files_lock
from app.utils.ui.icon.path_service import icon_path_service
from app.views.windows.dialogs.database_dialogs import DatabaseDialogs

logger = logging.getLogger(__name__)


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
    operation_success = pyqtSignal(str, str)  # str, str - title, success message

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.dialogs = DatabaseDialogs(parent)

    def _emit_success(self, message: str, *, title: str | None = None) -> None:
        self.operation_success.emit(title or self.tr("Done"), message)

    def _emit_error(self, message: str, *, title: str | None = None) -> None:
        self.operation_error.emit(title or self.tr("Error"), message)

    def _get_db_path_or_emit_error(self) -> str | None:
        """Return current DB path or emit a user-facing error."""
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self._emit_error(self.tr("Database path not found."))
            return None
        return db_path

    def _run_if_path_selected(
        self,
        selected_path: str | Path | None,
        action: Callable[[str], None],
    ) -> None:
        """Run action only when path is selected in dialog."""
        if selected_path:
            action(str(selected_path))

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
                # Run restore in background thread to avoid GUI freeze
                self._perform_database_restore_async(selected)

    def _perform_database_restore_async(self, backup_path):
        """Perform database restore in background thread.
        
        Avoids GUI freeze from blocking operations (sleep, file I/O, DB checkpoint).
        """
        worker = DatabaseRestoreWorker(self.db, backup_path)
        worker.signals.success.connect(self._on_restore_success)
        worker.signals.error.connect(self._on_restore_error)
        WorkerManager.run(worker)
        logger.info(f"Started async database restore from: {backup_path}")
    
    @pyqtSlot(object, str)
    def _on_restore_success(self, new_db, backup_name):
        """Handle successful restore in GUI thread."""
        logger.info(f"Restore completed, updating DB reference: {new_db}")
        self.db = new_db
        self.database_restored.emit(new_db)
        self._emit_success(
            self.tr("Database restored from backup:\n{backup_name}").format(
                backup_name=backup_name
            ),
        )
    
    @pyqtSlot(str)
    def _on_restore_error(self, error_msg):
        """Handle restore error in GUI thread."""
        logger.error(f"Restore failed: {error_msg}")
        self._emit_error(
            self.tr("Restore error: {error}").format(error=error_msg),
        )

    def handle_connect_database(self):
        """Another database connection handler."""
        db_path = self._get_db_path_or_emit_error()
        if not db_path:
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
            self._replace_database_file(file_path, db_path, backup_path)

            new_db = Database()
            self.db = new_db

            # Notify UI through signal - it will update all dependencies
            self.database_connected.emit(new_db)

        except Exception as e:
            # Use centralized error handler
            if not handle_db_error(e, self):
                # In case of error restore old database
                self._restore_database_backup(backup_path, db_path)
                self._emit_error(
                    self.tr("Database connection error: {error}\nOld database restored.").format(
                        error=e
                    ),
                )

    def _copy_file(self, src: str, dst: str) -> None:
        """Wrapper for file copies to centralize future tracing/retries."""
        shutil.copy2(src, dst)

    def _replace_database_file(self, file_path: str, db_path: str, backup_path: str) -> None:
        """Close DB, backup current file, then replace it with selected file."""
        self.db.close_all()
        self._copy_file(db_path, backup_path)
        self._copy_file(file_path, db_path)

    def _restore_database_backup(self, backup_path: str, db_path: str) -> None:
        """Best-effort rollback after failed connect operation."""
        try:
            self._copy_file(backup_path, db_path)
        except Exception:
            pass

    def handle_save_database(self):
        """Database copy save handler."""
        db_path = self._get_db_path_or_emit_error()
        if not db_path:
            return

        default_name = f"aite_db_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
        save_path = self.dialogs.get_save_location(default_name)
        self._run_if_path_selected(
            save_path,
            lambda selected_path: self._save_database_copy(db_path, selected_path),
        )

    def _save_database_copy(self, db_path: str, save_path: str) -> None:
        try:
            self._copy_file(db_path, save_path)
            self.database_saved.emit(save_path)
            self._emit_success(
                self.tr("Database copy saved:\n{path}").format(path=save_path),
            )
        except Exception as e:
            self._emit_error(
                self.tr("Save error: {error}").format(error=e),
            )

    def handle_save_icons(self):
        """Icon archive save handler."""
        icons_dir = self._get_user_icons_dir()
        if not Path(icons_dir).is_dir():
            self._emit_error(
                self.tr("Icons folder not found: {path}").format(path=icons_dir),
            )
            return

        default_name = f"aite_icons_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        save_path = self.dialogs.get_icons_archive_location(default_name)
        self._run_if_path_selected(
            save_path,
            lambda selected_path: self._save_icons_archive(icons_dir, selected_path),
        )

    def _save_icons_archive(self, icons_dir: str, save_path: str) -> None:
        try:
            self._export_icons_archive(icons_dir, save_path)
            self.icons_exported.emit(save_path)
            self._emit_success(
                self.tr("Icon archive saved to:\n{path}").format(path=save_path),
            )
        except Exception as e:
            self._emit_error(
                self.tr("Archive creation error: {error}").format(error=e),
            )

    def handle_load_icons(self):
        """Icon archive load handler."""
        icons_dir = self._get_user_icons_dir()
        Path(icons_dir).mkdir(parents=True, exist_ok=True)

        zip_path = self.dialogs.get_icons_archive_to_load()
        self._run_if_path_selected(
            zip_path,
            lambda selected_path: self._load_icons_archive(selected_path, icons_dir),
        )

    def _load_icons_archive(self, zip_path: str, icons_dir: str) -> None:
        try:
            icon_count = self._import_icons_archive(zip_path, icons_dir)
            clear_icon_cache()
            self.icons_imported.emit(icon_count)
            self._emit_success(
                self.tr("Icons successfully added to: {path}").format(
                    path=icons_dir
                ),
            )
        except Exception as e:
            self._emit_error(
                self.tr("Archive load error: {error}").format(error=e),
            )

    def _get_user_icons_dir(self) -> str:
        """Return user icon storage directory."""
        return icon_path_service.get_user_icons_dir()

    def _export_icons_archive(self, icons_dir: str, save_path: str) -> None:
        """Write all files from icons dir into zip archive."""
        allowed_suffixes = {
            suffix.lower()
            for suffix in icon_path_service.get_supported_icon_formats()
        }
        with icon_files_lock():
            with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for fname in os.listdir(icons_dir):
                    fpath = Path(icons_dir) / fname
                    if (
                        fpath.is_file()
                        and not fname.startswith(".")
                        and fpath.suffix.lower() in allowed_suffixes
                    ):
                        zipf.write(str(fpath), fname)

    def _import_icons_archive(self, zip_path: str, icons_dir: str) -> int:
        """Extract icon archive and return extracted entry count."""
        allowed_suffixes = {
            suffix.lower()
            for suffix in icon_path_service.get_supported_icon_formats()
        }
        target_root = Path(icons_dir).resolve()
        imported = 0
        with icon_files_lock():
            with zipfile.ZipFile(zip_path, "r") as zipf:
                for member in zipf.infolist():
                    if member.is_dir():
                        continue
                    member_path = Path(member.filename)
                    if len(member_path.parts) != 1 or member.filename != member_path.name:
                        continue
                    member_name = member_path.name
                    if (
                        not member_name
                        or member_name.startswith(".")
                        or Path(member_name).suffix.lower() not in allowed_suffixes
                    ):
                        continue
                    destination = (target_root / member_name).resolve()
                    if destination.parent != target_root:
                        continue
                    with zipf.open(member, "r") as src, open(destination, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    imported += 1
        return imported
