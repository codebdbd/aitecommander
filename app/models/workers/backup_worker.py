"""Worker для создания резервной копии БД в фоновом потоке."""
import logging
import shutil
from pathlib import Path

from .base_worker import DatabaseWorker

logger = logging.getLogger(__name__)


class BackupWorker(DatabaseWorker):
    """Worker для выполнения backup() в фоновом потоке.
    
    Создает резервную копию базы данных.
    """
    
    def __init__(self, db_path: str, backup_dir: Path):
        """
        Args:
            db_path: Путь к файлу БД
            backup_dir: Директория для сохранения backup
        """
        super().__init__(db_path)
        self.backup_dir = backup_dir
    
    def do_work(self, connection) -> dict[str, str]:
        """Выполняет резервное копирование.
        
        Returns:
            Словарь с путем к backup файлу
        """
        from datetime import datetime
        
        self.emit_progress(0, 3, "Подготовка к резервному копированию...")
        
        # Создаем директорию для backup если не существует
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Генерируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"osteen_path_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename
        
        if self.is_cancelled:
            return {}
        
        self.emit_progress(1, 3, "Создание резервной копии...")
        
        # Выполняем checkpoint для WAL mode
        connection.execute("PRAGMA wal_checkpoint(FULL)")
        
        # Копируем файл БД
        shutil.copy2(self.db_path, backup_path)
        
        if self.is_cancelled:
            # Удаляем созданный backup если операция отменена
            if backup_path.exists():
                backup_path.unlink()
            return {}
        
        self.emit_progress(2, 3, "Очистка старых backup...")
        
        # Удаляем старые backup файлы (оставляем только последние 10)
        backup_files = sorted(
            self.backup_dir.glob("osteen_path_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for old_backup in backup_files[10:]:  # Оставляем 10 последних
            try:
                old_backup.unlink()
                logger.info("Удален старый backup: %s", old_backup.name)
            except Exception as e:
                logger.warning("Не удалось удалить старый backup %s: %s", old_backup.name, e)
        
        self.emit_progress(3, 3, "Резервное копирование завершено")
        
        return {
            "backup_path": str(backup_path),
            "backup_filename": backup_filename
        }
