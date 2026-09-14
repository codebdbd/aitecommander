# app/controllers/database_controller.py

import logging
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PyQt6.QtCore import (
    QObject,
    pyqtSignal,
    pyqtSlot,
)

from app.core.worker_manager import WorkerManager
from app.services.database_restore_worker import DatabaseRestoreWorker
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
        self._is_restoring = False

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
        if self._is_restoring:
            self._emit_error(self.tr("Database restoration is already in progress."))
            return

        from app.views.windows.dialogs.restore_db_dialog import RestoreDbDialog

        dlg = RestoreDbDialog(parent=self.parent())
        if dlg.exec() == dlg.DialogCode.Accepted:
            selected = dlg.get_selected_backup()
            if selected:
                self._is_restoring = True
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
        self._is_restoring = False
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
        self._is_restoring = False
        logger.error(f"Restore failed: {error_msg}")
        self._emit_error(
            self.tr("Restore error: {error}").format(error=error_msg),
        )

    def handle_connect_database(self):
        """Another database connection handler with validation and exclusive maintenance."""
        if self._is_restoring:
            self._emit_error(self.tr("Database operation is already in progress."))
            return

        db_path = self._get_db_path_or_emit_error()
        if not db_path:
            return

        file_path = self.dialogs.get_connect_file()
        if file_path:
            self._is_restoring = True
            self._perform_database_connection_async(str(file_path))

    def _perform_database_connection_async(self, file_path: str) -> None:
        """Perform database connection in background thread with verification and maintenance lock."""
        worker = DatabaseRestoreWorker(self.db, file_path)
        worker.signals.success.connect(self._on_connect_success)
        worker.signals.error.connect(self._on_connect_error)
        WorkerManager.run(worker)
        logger.info(f"Started async database connect from: {file_path}")

    @pyqtSlot(object, str)
    def _on_connect_success(self, new_db, file_name: str) -> None:
        """Handle successful connect in GUI thread."""
        self._is_restoring = False
        logger.info(f"Database connect completed, updating DB reference: {new_db}")
        self.db = new_db
        self.database_connected.emit(new_db)
        self._emit_success(
            self.tr("Database connected from:\n{file_name}").format(
                file_name=file_name
            ),
        )

    @pyqtSlot(str)
    def _on_connect_error(self, error_msg: str) -> None:
        """Handle connect error in GUI thread."""
        self._is_restoring = False
        logger.error(f"Database connect failed: {error_msg}")
        self._emit_error(
            self.tr("Database connection error: {error}").format(error=error_msg),
        )

    def _perform_database_connection(self, file_path: str, db_path: str | None = None) -> None:
        """Entry point for connecting database with full verification and maintenance mode."""
        if self._is_restoring:
            self._emit_error(self.tr("Database operation is already in progress."))
            return
        self._is_restoring = True
        self._perform_database_connection_async(file_path)

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
        target_path = Path(save_path).resolve()
        temp_path = target_path.with_name(f".{target_path.name}.tmp")
        try:
            from app.core.database_manager import DatabaseManager

            conn = getattr(self.db, "connection", None)
            if conn is None:
                conn = DatabaseManager.get_connection()

            try:
                conn.execute("PRAGMA wal_checkpoint(FULL)")
            except Exception as checkpoint_err:
                logger.debug("WAL checkpoint prior to save warning: %s", checkpoint_err)

            temp_path.parent.mkdir(parents=True, exist_ok=True)
            dest_conn = sqlite3.connect(str(temp_path))
            try:
                conn.backup(dest_conn)
            finally:
                dest_conn.close()

            # Atomic publication
            try:
                os.replace(temp_path, target_path)
            except OSError:
                shutil.copy2(temp_path, target_path)
                try:
                    temp_path.unlink()
                except OSError:
                    pass

            self.database_saved.emit(str(target_path))
            self._emit_success(
                self.tr("Database copy saved:\n{path}").format(path=str(target_path)),
            )
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
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
        """Extract icon archive safely with limits and atomic placement."""
        MAX_ICON_FILES = 2000
        MAX_ICON_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per icon
        MAX_TOTAL_EXTRACTED_SIZE = 100 * 1024 * 1024  # 100 MB total archive payload

        allowed_suffixes = {
            suffix.lower()
            for suffix in icon_path_service.get_supported_icon_formats()
        }
        target_root = Path(icons_dir).resolve()
        target_root.mkdir(parents=True, exist_ok=True)

        with icon_files_lock():
            with zipfile.ZipFile(zip_path, "r") as zipf:
                infolist = zipf.infolist()
                valid_members = []
                total_size = 0

                for member in infolist:
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

                    if member.file_size > MAX_ICON_FILE_SIZE:
                        raise ValueError(
                            self.tr("File {name} exceeds maximum allowed size ({size} MB)").format(
                                name=member_name,
                                size=MAX_ICON_FILE_SIZE // (1024 * 1024),
                            )
                        )
                    total_size += member.file_size
                    if total_size > MAX_TOTAL_EXTRACTED_SIZE:
                        raise ValueError(
                            self.tr("Archive exceeds total allowed icon size ({size} MB)").format(
                                size=MAX_TOTAL_EXTRACTED_SIZE // (1024 * 1024)
                            )
                        )
                    valid_members.append((member, member_name))

                if len(valid_members) > MAX_ICON_FILES:
                    raise ValueError(
                        self.tr("Archive contains too many icons ({count} > {limit})").format(
                            count=len(valid_members),
                            limit=MAX_ICON_FILES,
                        )
                    )

                imported = 0
                tmp_root = target_root.parent / f".{target_root.name}.import-{uuid4().hex}.tmp"
                shutil.rmtree(tmp_root, ignore_errors=True)
                tmp_root.mkdir(parents=True, exist_ok=False)
                try:
                    for member, member_name in valid_members:
                        tmp_dest = tmp_root / member_name
                        with zipf.open(member, "r") as src, open(tmp_dest, "wb") as dst:
                            shutil.copyfileobj(src, dst)

                    for _, member_name in valid_members:
                        src_path = tmp_root / member_name
                        dest_path = target_root / member_name
                        try:
                            os.replace(src_path, dest_path)
                        except OSError:
                            shutil.copy2(src_path, dest_path)
                        imported += 1
                finally:
                    shutil.rmtree(tmp_root, ignore_errors=True)

        return imported
