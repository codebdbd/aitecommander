"""Worker для асинхронной инициализации базы данных.

✅ НОВЫЙ ФАЙЛ: Решает проблему блокировки UI при initialize_or_migrate().
"""
import logging
from pathlib import Path

from .base_worker import DatabaseWorker

logger = logging.getLogger(__name__)


class InitializationWorker(DatabaseWorker):
    """Worker для выполнения initialize_or_migrate() в фоновом потоке.
    
    Инициализирует новую БД или выполняет миграции для существующей
    без блокировки UI.
    """
    
    def __init__(self, db_path: str, migrations_dir: Path):
        """
        Args:
            db_path: Путь к файлу БД
            migrations_dir: Директория с миграциями
        """
        super().__init__(db_path)
        self.migrations_dir = migrations_dir
    
    def do_work(self, connection) -> dict:
        """Выполняет инициализацию/миграцию БД.
        
        Returns:
            Статистика: {is_new: bool, migrations_applied: int}
        """
        from app.utils.db.migrations import MigrationRunner
        
        db_path = Path(self.db_path)
        is_new = not db_path.exists()
        
        self.emit_progress(0, 1, "Применение миграций...")
        
        # Запускаем миграции через MigrationRunner
        runner = MigrationRunner(connection, self.migrations_dir)
        applied = runner.run_all_pending()
        
        logger.info("Миграции применены: %d", applied)
        
        # Инициализация дефолтных данных для новой базы
        if is_new:
            if self.is_cancelled:
                return {"is_new": is_new, "migrations_applied": applied}
            
            self.emit_progress(1, 1, "Инициализация дефолтных данных...")
            
            try:
                # Вставляем дефолтные сферы
                connection.execute(
                    "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                    ("Работа", "", 0)
                )
                connection.execute(
                    "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                    ("Личное", "", 1)
                )
                connection.commit()
                logger.info("Инициализированы дефолтные сферы")
            except Exception as init_err:
                logger.warning(
                    "Не удалось инициализировать дефолтные сферы: %s",
                    init_err,
                    exc_info=True,
                )
        
        return {
            "is_new": is_new,
            "migrations_applied": applied
        }
