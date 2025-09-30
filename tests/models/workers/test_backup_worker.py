"""Tests for BackupWorker."""
import tempfile
from pathlib import Path
import pytest
import sqlite3

from app.models.workers import BackupWorker


@pytest.fixture
def temp_db():
    """Создает временную тестовую БД."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Создаем простую таблицу
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test (name) VALUES ('test1')")
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_backup_dir():
    """Создает временную директорию для backup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_backup_worker_success(temp_db, temp_backup_dir):
    """Тест успешного создания backup."""
    worker = BackupWorker(temp_db, temp_backup_dir)
    
    # Создаем mock соединение
    connection = worker.create_connection()
    
    # Выполняем работу
    result = worker.do_work(connection)
    
    # Проверяем результат
    assert result is not None
    assert 'backup_path' in result
    assert 'backup_filename' in result
    
    # Проверяем что файл создан
    backup_path = Path(result['backup_path'])
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0
    
    connection.close()


def test_backup_worker_creates_directory(temp_db):
    """Тест что worker создает директорию если её нет."""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir) / "non_existent" / "backup"
        
        worker = BackupWorker(temp_db, backup_dir)
        connection = worker.create_connection()
        result = worker.do_work(connection)
        
        assert backup_dir.exists()
        assert result is not None
        
        connection.close()


def test_backup_worker_cleanup_old_backups(temp_db, temp_backup_dir):
    """Тест что worker удаляет старые backup (оставляет 10 последних)."""
    # Создаем 12 старых backup файлов
    for i in range(12):
        backup_file = temp_backup_dir / f"osteen_path_20230101_0000{i:02d}.db"
        backup_file.write_text("old backup")
    
    # Запускаем worker
    worker = BackupWorker(temp_db, temp_backup_dir)
    connection = worker.create_connection()
    result = worker.do_work(connection)
    
    # Проверяем что осталось максимум 11 файлов (10 старых + 1 новый)
    backup_files = list(temp_backup_dir.glob("osteen_path_*.db"))
    assert len(backup_files) <= 11
    
    connection.close()


def test_backup_worker_cancelled(temp_db, temp_backup_dir):
    """Тест отмены операции."""
    worker = BackupWorker(temp_db, temp_backup_dir)
    
    # Отменяем операцию
    worker.cancel()
    
    connection = worker.create_connection()
    result = worker.do_work(connection)
    
    # При отмене должен вернуть пустой dict
    assert result == {}
    
    # Backup не должен быть создан
    backup_files = list(temp_backup_dir.glob("osteen_path_*.db"))
    assert len(backup_files) == 0
    
    connection.close()
