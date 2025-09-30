"""Модуль для управления резервным копированием базы данных."""
import datetime
import logging
import os
import sqlite3
import time
from pathlib import Path

from ..types.constants import BACKUP_RETRY_ATTEMPTS, BACKUP_RETRY_DELAY
from ..base.db_base import DatabaseError

logger = logging.getLogger(__name__)


class BackupManager:
    """Управление резервным копированием базы данных."""

    def __init__(self, db):
        """
        Args:
            db: Экземпляр Database для доступа к соединению и сигналам
        """
        self.db = db

    def backup(self, backup_dir: Path):
        """Создаёт резервную копию базы данных и удаляет старые копии при превышении лимита.
        
        Args:
            backup_dir: Директория для хранения резервных копий
            
        Raises:
            DatabaseError: При ошибке создания резервной копии
        """
        operation = "backup"
        try:
            self.db.operation_started.emit(operation, 2)
            max_bak = self._get_max_backups()
            
            # 1) Создаём новый бэкап
            self.db.operation_progress.emit(operation, 0, 2, "Создание резервной копии...")
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
            dst = backup_dir / f"links_{timestamp}.db"
            
            with sqlite3.connect(self.db.db_path) as src, sqlite3.connect(dst) as dest:
                src.backup(dest)
            logger.info("Создана резервная копия: %s", dst)
            
            # Явно обновляем метку времени файла
            try:
                os.utime(dst, None)
            except Exception:
                pass

            # 2) Очистка сверх лимита
            self.db.operation_progress.emit(operation, 1, 2, "Очистка старых копий...")
            files = sorted(backup_dir.glob("links_*.db"))
            
            if len(files) > max_bak:
                candidates = [f for f in files if f != dst]
                deleted_count = 0
                target_deletions = len(files) - max_bak
                
                for attempt in range(BACKUP_RETRY_ATTEMPTS):
                    files_to_try = [f for f in candidates if f.exists()]
                    if not files_to_try or deleted_count >= target_deletions:
                        break
                        
                    for old_file in files_to_try:
                        if deleted_count >= target_deletions:
                            break
                        try:
                            old_file.unlink()
                            deleted_count += 1
                            if old_file in candidates:
                                candidates.remove(old_file)
                        except Exception as del_err:
                            logger.warning(
                                "Не удалось удалить старую резервную копию %s: %s",
                                old_file,
                                del_err,
                                exc_info=False,
                            )
                    
                    if attempt < BACKUP_RETRY_ATTEMPTS - 1 and deleted_count < target_deletions:
                        time.sleep(BACKUP_RETRY_DELAY)
            
            self.db.operation_finished.emit(operation, True)
            
            # Уведомляем UI об успешном создании резервной копии
            try:
                self.db.backup_created.emit(str(dst))
            except Exception as signal_err:
                logger.debug(
                    "Ошибка отправки сигнала backup_created: %s",
                    signal_err,
                    exc_info=True,
                )
        except Exception as e:
            logger.error("Ошибка создания резервной копии: %s", e, exc_info=True)
            self.db.operation_finished.emit(operation, False)
            try:
                self.db.error_occurred.emit("Ошибка бэкапа", str(e))
            except Exception:
                pass
            raise DatabaseError(f"Не удалось создать резервную копию: {e}")

    def _get_max_backups(self) -> int:
        """Возвращает максимальное количество резервных копий из пользовательских настроек."""
        from app.config_data import app_config
        return app_config.settings.get_max_backups()
