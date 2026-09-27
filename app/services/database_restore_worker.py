"""Background worker for database restore operations."""

from __future__ import annotations

import gc
import logging
import os
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal

from app.core.database_manager import DatabaseManager
from app.core.paths.path_manager import PathManager
from app.models.db import Database
from app.utils.db.migrations import MigrationRunner
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.utils.ui.icon.file_lock import icon_files_lock
from app.utils.ui.icon.path_service import icon_path_service

logger = logging.getLogger(__name__)

REQUIRED_TABLES = frozenset({"sphere", "section", "category", "link"})

REQUIRED_BASE_COLUMNS = {
    "sphere": frozenset({"id", "name"}),
    "section": frozenset({"id", "sphere_id", "name"}),
    "category": frozenset({"id", "section_id", "name"}),
    "link": frozenset({"id", "category_id", "name"}),
}

REQUIRED_FINAL_COLUMNS = {
    "sphere": frozenset({"id", "name", "position", "icon_path"}),
    "section": frozenset({"id", "sphere_id", "name", "position", "icon_path"}),
    "category": frozenset({"id", "section_id", "name", "position", "icon_path"}),
    "link": frozenset({"id", "category_id", "name", "url", "type", "position", "icon_path", "is_favorite"}),
}


class DatabaseRestoreWorkerSignals(QObject):
    """Signals for DatabaseRestoreWorker."""

    success = pyqtSignal(object, str)  # new_db, backup_name
    error = pyqtSignal(str)  # error_message


class DatabaseRestoreWorker(QRunnable):
    """Worker for database restore in background thread."""

    def __init__(
        self,
        db,
        backup_path,
        *,
        sqlite_connect=None,
        max_supported_version: int | None = None,
    ):
        super().__init__()
        self.db = db
        self.backup_path = Path(backup_path)
        self._sqlite_connect = sqlite_connect or sqlite3.connect
        self._max_supported_version = max_supported_version
        self.signals = DatabaseRestoreWorkerSignals()

    def run(self):
        """Execute restore in background thread."""
        try:
            with DatabaseManager.maintenance_scope():
                new_db, backup_name = self._restore_database(self.backup_path)
            self.signals.success.emit(new_db, backup_name)
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def _restore_database(self, backup_path: Path):
        """Perform database restore (blocking operation)."""
        db_path = Path(DatabaseManager.get_db_path())
        backup_path = Path(backup_path)

        is_zip = zipfile.is_zipfile(backup_path)
        source_db_file = backup_path
        staging_root: Path | None = None
        staged_icons_dir: Path | None = None

        if is_zip:
            staging_root = db_path.parent / f".restore_staging_{uuid4().hex}"
            staging_root.mkdir(parents=True, exist_ok=True)
            source_db_file, staged_icons_dir = self._extract_bundle_staging(backup_path, staging_root)

        self._verify_backup_integrity(source_db_file)

        logger.info(f"Starting database restore from: {backup_path}")

        # Close ALL connections
        logger.info("Closing ALL database connections")
        self.db.close_all()

        # Force Python garbage collection
        gc.collect()

        self._prepare_target_database_for_restore(db_path)

        tmp_target = db_path.with_name(f"{db_path.name}.restore_tmp")
        orig_backup = db_path.with_name(f"{db_path.name}.orig_bak")

        try:
            # 1. Copy backup to temporary staging file first
            self._copy_backup_with_retries(source_db_file, tmp_target)

            # 2. Verify integrity of the staged temporary file
            self._verify_backup_integrity(tmp_target)

            # 3. Apply pending migrations and validate schema compatibility on staged file
            self._migrate_and_validate_staged_database(tmp_target)

            # 4. Preserve original database before replacement
            has_orig = False
            if db_path.exists():
                try:
                    if orig_backup.exists():
                        orig_backup.unlink()
                    os.replace(db_path, orig_backup)
                    has_orig = True
                    logger.info(f"Preserved original database as {orig_backup}")
                except Exception as e:
                    logger.warning(f"Failed to preserve original DB via rename: {e}")

            # 5. Atomically move staged DB to live target path
            try:
                os.replace(tmp_target, db_path)
                logger.info(f"Atomically replaced live database with restored file: {db_path}")
            except Exception as replace_err:
                logger.error(f"Failed to replace live database with {tmp_target}: {replace_err}")
                # Rollback from preserved original if possible
                if has_orig and orig_backup.exists():
                    try:
                        os.replace(orig_backup, db_path)
                        logger.info("Successfully rolled back to original database")
                    except Exception as rollback_err:
                        logger.critical(f"Failed to rollback original database: {rollback_err}")
                raise replace_err

            # 6. Verify live database file and create Database wrapper
            logger.info("Verifying live database file after replacement")
            try:
                self._verify_live_database(db_path)
            except Exception as verify_err:
                logger.critical(f"Live database verification failed: {verify_err}")
                if has_orig and orig_backup.exists():
                    try:
                        os.replace(orig_backup, db_path)
                        logger.info("Successfully rolled back live database to original database")
                    except Exception as rollback_err:
                        logger.critical(f"Failed to rollback live database: {rollback_err}")
                raise ValueError(
                    QCoreApplication.translate(
                        "DatabaseRestoreWorker",
                        "Restored database failed verification: {error}",
                    ).format(error=verify_err)
                ) from verify_err

            # Clean up preserved original only after live verification succeeds
            if has_orig and orig_backup.exists():
                try:
                    orig_backup.unlink(missing_ok=True)
                except Exception:
                    pass

            # 7. Atomically publish staged bundle icons if present
            if staged_icons_dir and staged_icons_dir.exists():
                self._publish_staged_icons(staged_icons_dir)

            logger.info("Creating new Database object")
            new_db = Database()

            logger.info("Database restore completed successfully")
            return new_db, backup_path.name
        finally:
            if tmp_target.exists():
                try:
                    tmp_target.unlink(missing_ok=True)
                except Exception:
                    pass
            if staging_root and staging_root.exists():
                try:
                    shutil.rmtree(staging_root, ignore_errors=True)
                except Exception:
                    pass

    def _extract_bundle_staging(self, bundle_path: Path, staging_root: Path) -> tuple[Path, Path]:
        """Safely extract database and icons from zip into a local staging directory."""
        MAX_ICON_FILES = 2000
        MAX_ICON_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per icon
        MAX_TOTAL_EXTRACTED_SIZE = 100 * 1024 * 1024  # 100 MB max icons
        allowed_suffixes = {s.lower() for s in icon_path_service.get_supported_icon_formats()}

        staged_db = staging_root / "extracted_database.db"
        staged_icons = staging_root / "icons"
        staged_icons.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(bundle_path, "r") as zipf:
            infolist = zipf.infolist()
            db_member = None

            # Find database member (database.db or root *.db)
            for member in infolist:
                norm_name = member.filename.replace("\\", "/")
                if norm_name == "database.db" or (not "/" in norm_name and norm_name.lower().endswith(".db")):
                    db_member = member
                    break

            if not db_member:
                raise ValueError(
                    QCoreApplication.translate(
                        "DatabaseRestoreWorker",
                        "Archive does not contain a valid database file.",
                    )
                )

            with zipf.open(db_member, "r") as src, open(staged_db, "wb") as dst:
                shutil.copyfileobj(src, dst)

            # Safely extract icons without directory traversal
            total_size = 0
            icon_count = 0
            for member in infolist:
                if member.is_dir():
                    continue
                parts = PurePosixPath(member.filename.replace("\\", "/")).parts
                if len(parts) == 2 and parts[0] == "icons":
                    fname = parts[1]
                    if not fname or fname.startswith(".") or fname in (".", ".."):
                        continue
                    if Path(fname).suffix.lower() not in allowed_suffixes:
                        continue
                    if member.file_size > MAX_ICON_FILE_SIZE:
                        continue
                    total_size += member.file_size
                    if total_size > MAX_TOTAL_EXTRACTED_SIZE:
                        break
                    icon_count += 1
                    if icon_count > MAX_ICON_FILES:
                        break
                    target_dest = staged_icons / fname
                    with zipf.open(member, "r") as src, open(target_dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        return staged_db, staged_icons

    def _publish_staged_icons(self, staged_icons_dir: Path) -> None:
        """Publish staged icons into the live user icons directory."""
        user_icons_dir = Path(icon_path_service.get_user_icons_dir()).resolve()
        user_icons_dir.mkdir(parents=True, exist_ok=True)

        with icon_files_lock():
            for icon_path in staged_icons_dir.iterdir():
                if icon_path.is_file():
                    dest = user_icons_dir / icon_path.name
                    try:
                        os.replace(icon_path, dest)
                    except OSError:
                        shutil.copy2(icon_path, dest)
            clear_icon_cache()

    def _prepare_target_database_for_restore(self, db_path) -> None:
        """Prepare DB files/handles before replacing file from backup."""
        self._switch_journal_mode_for_restore(db_path)

        # Wait for Windows to release file handles
        time.sleep(1.0)

        self._remove_wal_sidecar_files(db_path)

    def _switch_journal_mode_for_restore(self, db_path) -> None:
        """Best-effort switch to DELETE journal mode before file replacement."""
        logger.info("Switching database to DELETE journal mode for restore")
        try:
            temp_conn = self._open_sqlite_connection(db_path, timeout=10.0)
            try:
                temp_conn.execute("PRAGMA mmap_size = 0")
                temp_conn.execute("PRAGMA journal_mode = DELETE")
                temp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                temp_conn.commit()
                logger.info("Successfully switched to DELETE journal mode")
            finally:
                temp_conn.close()
                del temp_conn
                gc.collect()
        except Exception as journal_err:
            logger.warning(f"Failed to switch journal mode: {journal_err}")

    def _remove_wal_sidecar_files(self, db_path) -> None:
        """Remove SQLite sidecar files (`-wal`, `-shm`) before restore copy."""
        wal_path = f"{db_path}-wal"
        shm_path = f"{db_path}-shm"
        for extra_file in [wal_path, shm_path]:
            self._remove_sidecar_file_with_retry(extra_file)

    def _remove_sidecar_file_with_retry(self, extra_file: str) -> None:
        if not os.path.exists(extra_file):
            return
        try:
            logger.info(f"Removing {extra_file}")
            os.remove(extra_file)
            logger.info(f"Successfully removed {extra_file}")
        except Exception as exc:
            logger.warning(f"Could not remove {extra_file}: {exc}")
            try:
                time.sleep(0.5)
                os.remove(extra_file)
                logger.info(f"Successfully removed {extra_file} on retry")
            except Exception as retry_exc:
                logger.error(f"Failed to remove {extra_file} on retry: {retry_exc}")
                if "wal" in extra_file.lower():
                    raise self._build_locked_wal_error(extra_file) from retry_exc

    def _build_locked_wal_error(self, file_name: str) -> OSError:
        message = QCoreApplication.translate(
            "DatabaseRestoreWorker",
            (
                "Cannot restore database: WAL file {file_name} is locked. "
                "Please close all connections and try again."
            ),
        ).format(file_name=file_name)
        return OSError(message)

    def _copy_backup_with_retries(self, backup_path, db_path, *, max_retries: int = 3) -> None:
        """Create a consistent snapshot of source DB into target staging file using SQLite Backup API."""
        src_path = Path(backup_path).resolve()
        dest_path = Path(db_path).resolve()
        logger.info(f"Creating snapshot of {src_path} at {dest_path}")

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                # Use SQLite backup API to consistently incorporate WAL journal if present
                src_uri = f"{src_path.as_uri()}?mode=ro"
                src_conn = self._sqlite_connect(src_uri, uri=True)
                try:
                    dest_conn = self._sqlite_connect(str(dest_path))
                    try:
                        src_conn.backup(dest_conn)
                        logger.info(f"Successfully created SQLite backup snapshot at {dest_path}")
                        return
                    finally:
                        dest_conn.close()
                finally:
                    src_conn.close()
            except Exception as backup_err:
                last_error = backup_err
                logger.warning(
                    f"SQLite backup API attempt {attempt + 1} of {max_retries} failed: {backup_err}"
                )
                if dest_path.exists():
                    try:
                        dest_path.unlink()
                    except OSError:
                        pass
                if attempt < max_retries - 1:
                    time.sleep(1.0)
                    gc.collect()

        logger.error(f"All {max_retries} SQLite backup snapshot attempts failed for {src_path}: {last_error}")
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to create database snapshot of {src_path}")

    def _get_migrations_dir(self) -> Path:
        return PathManager.app_root() / "models" / "migrations"

    def _get_max_supported_schema_version(self) -> int:
        if self._max_supported_version is not None:
            return self._max_supported_version
        try:
            migrations_dir = self._get_migrations_dir()
            if not migrations_dir.exists():
                return 0
            runner = MigrationRunner(None, migrations_dir)
            all_migs = runner.discover()
            if not all_migs:
                return 0
            return max(m.version for m in all_migs)
        except Exception as exc:
            logger.warning("Could not determine max supported schema version: %s", exc)
            return 0

    def _migrate_and_validate_staged_database(self, staged_path: Path) -> None:
        """Apply pending migrations and verify full schema compatibility on staged file before swapping."""
        logger.info(f"Applying pending migrations and validating staged DB at {staged_path}")
        path_str = str(staged_path.resolve())
        conn = self._open_sqlite_connection(path_str)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            migrations_dir = self._get_migrations_dir()
            if migrations_dir and migrations_dir.exists():
                runner = MigrationRunner(conn, migrations_dir)
                applied_count = runner.run_all_pending()
                logger.info(f"Applied {applied_count} pending migration(s) on staged database")

            # Verify foreign keys after migrations
            fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_violations:
                raise ValueError(
                    f"Foreign key check failed after migrations on staged database: {len(fk_violations)} violation(s)"
                )

            # Verify required final columns
            for table_name, req_cols in REQUIRED_FINAL_COLUMNS.items():
                col_info = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
                existing_cols = {r[1] for r in col_info}
                missing_cols = req_cols - existing_cols
                if missing_cols:
                    raise ValueError(
                        f"Staged database table '{table_name}' is missing required column(s): {', '.join(sorted(missing_cols))}"
                    )

            # Smoke queries on staged database
            conn.execute("SELECT id, name, position, icon_path FROM sphere LIMIT 1;").fetchall()
            conn.execute("SELECT id, sphere_id, name, position, icon_path FROM section LIMIT 1;").fetchall()
            conn.execute("SELECT id, section_id, name, position, icon_path FROM category LIMIT 1;").fetchall()
            conn.execute("SELECT id, category_id, name, url, type, position, icon_path, is_favorite FROM link LIMIT 1;").fetchall()

            conn.commit()
            logger.info("Staged database migration and schema validation succeeded")
        finally:
            conn.close()
            del conn
            gc.collect()

    def _verify_live_database(self, db_path: Path) -> None:
        """Smoke test live database file before finalizing restore."""
        logger.info(f"Performing smoke verification on live database at {db_path}")
        path_str = str(Path(db_path).resolve())
        conn = self._open_sqlite_connection(path_str)
        try:
            conn.execute("SELECT id, name, position, icon_path FROM sphere LIMIT 1;").fetchall()
            conn.execute("SELECT id, sphere_id, name, position, icon_path FROM section LIMIT 1;").fetchall()
            conn.execute("SELECT id, section_id, name, position, icon_path FROM category LIMIT 1;").fetchall()
            conn.execute("SELECT id, category_id, name, url, type, position, icon_path, is_favorite FROM link LIMIT 1;").fetchall()
        finally:
            conn.close()
            del conn
            gc.collect()

    def _verify_backup_integrity(self, backup_path: Path | str) -> None:
        path = Path(backup_path).resolve()
        if not path.is_file():
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup file does not exist: {path}",
                ).format(path=path)
            )

        if path.stat().st_size == 0:
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup file is empty: {path}",
                ).format(path=path)
            )

        try:
            backup_uri = f"{path.as_uri()}?mode=ro"
            conn = self._open_sqlite_connection(backup_uri, uri=True)
            try:
                # 1. PRAGMA integrity_check
                row = conn.execute("PRAGMA integrity_check").fetchone()
                result = row[0] if row else "unknown"
                if result != "ok":
                    raise ValueError(f"SQLite integrity check failed: {result}")

                # 2. Check required tables and base columns
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                missing_tables = REQUIRED_TABLES - tables
                if missing_tables:
                    raise ValueError(
                        f"Database is missing required table(s): {', '.join(sorted(missing_tables))}"
                    )

                for table_name, req_cols in REQUIRED_BASE_COLUMNS.items():
                    col_info = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
                    existing_cols = {r[1] for r in col_info}
                    missing_cols = req_cols - existing_cols
                    if missing_cols:
                        raise ValueError(
                            f"Database table '{table_name}' is missing required column(s): {', '.join(sorted(missing_cols))}"
                        )

                # 3. Check schema version
                user_ver_row = conn.execute("PRAGMA user_version").fetchone()
                user_version = int(user_ver_row[0]) if user_ver_row else 0
                max_supported = self._get_max_supported_schema_version()
                if user_version < 0:
                    raise ValueError(f"Invalid schema version: {user_version}")
                if max_supported > 0 and user_version > max_supported:
                    raise ValueError(
                        f"Backup schema version ({user_version}) is newer than supported ({max_supported})"
                    )

                # 4. PRAGMA foreign_key_check
                fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if fk_violations:
                    raise ValueError(
                        f"Foreign key integrity check failed: {len(fk_violations)} violation(s) found"
                    )
            finally:
                conn.close()
        except Exception as exc:
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup integrity check failed: {error}",
                ).format(error=exc)
            ) from exc

    def _open_sqlite_connection(self, path, **kwargs):
        """Wrapper for sqlite connection creation to simplify tests and tracing."""
        try:
            conn = self._sqlite_connect(path, **kwargs)
        except TypeError:
            conn = self._sqlite_connect(path)
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        return conn
