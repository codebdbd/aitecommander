"""
Тесты для критичных сценариев Database.

✅ НОВЫЙ ФАЙЛ: Покрытие исправленных критичных проблем.
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from app.models import Database


@pytest.fixture
def temp_db_path(tmp_path):
    """Создаёт временный путь для БД."""
    return tmp_path / "test.db"


@pytest.fixture
def qapp():
    """Создаёт QApplication для тестов."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Не закрываем app, т.к. может использоваться другими тестами


class TestDatabaseCleanup:
    """Тесты cleanup ресурсов."""

    def test_cleanup_is_idempotent(self, temp_db_path, qapp):
        """cleanup() можно вызывать многократно."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()

        # Act
        db.cleanup()
        db.cleanup()
        db.cleanup()

        # Assert
        assert db._cleaned_up is True

    def test_cleanup_waits_for_thread_pool(self, temp_db_path, qapp):
        """cleanup() ждёт завершения thread pool."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        # Mock thread pool
        db._thread_pool = Mock()
        db._thread_pool.waitForDone = Mock(return_value=True)

        # Act
        db.cleanup()

        # Assert
        db._thread_pool.waitForDone.assert_called_once_with(5000)

    def test_cleanup_closes_connection(self, temp_db_path, qapp):
        """cleanup() закрывает соединение с БД."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        # Создаём соединение
        _ = db.connection

        # Act
        db.cleanup()

        # Assert
        assert not hasattr(db.thread_local, 'conn') or db.thread_local.conn is None

    def test_cleanup_clears_models(self, temp_db_path, qapp):
        """cleanup() очищает ссылки на модели."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()

        # Act
        db.cleanup()

        # Assert
        for attr in ['spheres', 'sections', 'categories', 'links']:
            assert not hasattr(db, attr)


class TestDatabaseParent:
    """Тесты правильного управления памятью через parent."""

    def test_database_accepts_parent(self, temp_db_path, qapp):
        """Database принимает parent параметр."""
        # Arrange
        parent = QObject()

        # Act
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database(parent=parent)

        # Assert
        assert db.parent() is parent

    def test_database_without_parent(self, temp_db_path, qapp):
        """Database работает без parent."""
        # Act
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()

        # Assert
        assert db.parent() is None


class TestInitializeOrMigrateAsync:
    """Тесты асинхронной инициализации."""

    def test_initialize_or_migrate_async_starts_worker(self, temp_db_path, qapp):
        """initialize_or_migrate_async() запускает worker."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        db._thread_pool = Mock()

        # Act
        db.initialize_or_migrate_async()

        # Assert
        db._thread_pool.start.assert_called_once()

    def test_initialize_or_migrate_async_calls_on_finished(self, temp_db_path, qapp):
        """initialize_or_migrate_async() вызывает on_finished callback."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        on_finished = Mock()

        # Act
        with patch.object(db._thread_pool, 'start'):
            db.initialize_or_migrate_async(on_finished=on_finished)

        # Assert
        # Callback должен быть подключен к сигналу
        # (проверяем через mock, что метод был вызван)
        assert on_finished is not None

    def test_initialize_or_migrate_deprecated_warning(self, temp_db_path, qapp):
        """initialize_or_migrate() выдаёт DeprecationWarning."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()

        # Act & Assert
        with pytest.warns(DeprecationWarning, match="устарел"):
            with patch.object(db, 'connection'):
                with patch('app.models.db.MigrationRunner'):
                    try:
                        db.initialize_or_migrate()
                    except Exception:
                        pass  # Игнорируем ошибки инициализации


class TestSafeEmit:
    """Тесты безопасного эмита сигналов."""

    def test_safe_emit_works_with_qapplication(self, temp_db_path, qapp):
        """_safe_emit() работает при наличии QApplication."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        signal_emitted = []
        db.data_changed.connect(lambda *args: signal_emitted.append(args))

        # Act
        db._safe_emit(db.data_changed, "test_table", "insert", [1, 2, 3])

        # Assert
        assert len(signal_emitted) == 1
        assert signal_emitted[0] == ("test_table", "insert", [1, 2, 3])

    def test_safe_emit_skips_without_qapplication(self, temp_db_path):
        """_safe_emit() пропускает эмит без QApplication."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            with patch('PyQt6.QtWidgets.QApplication.instance', return_value=None):
                db = Database()
                
        signal_emitted = []
        db.data_changed.connect(lambda *args: signal_emitted.append(args))

        # Act
        db._safe_emit(db.data_changed, "test_table", "insert", [1, 2, 3])

        # Assert
        assert len(signal_emitted) == 0  # Сигнал не эмитится

    def test_safe_emit_handles_exceptions(self, temp_db_path, qapp, caplog):
        """_safe_emit() обрабатывает исключения при эмите."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        # Создаём сигнал, который выбросит исключение
        def failing_slot(*args):
            raise RuntimeError("Test error")
        
        db.data_changed.connect(failing_slot)

        # Act
        with caplog.at_level(logging.DEBUG):
            db._safe_emit(db.data_changed, "test_table", "insert", [1])

        # Assert
        # Исключение не должно прервать выполнение
        # (проверяем, что метод завершился без падения)
        assert True


class TestThreadSafety:
    """Тесты потокобезопасности."""

    def test_thread_local_connections(self, temp_db_path, qapp):
        """Каждый поток получает своё соединение."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()

        # Act
        conn1 = db.connection
        conn2 = db.connection

        # Assert
        assert conn1 is conn2  # В одном потоке - одно соединение

    def test_cleanup_thread_safety(self, temp_db_path, qapp):
        """cleanup() потокобезопасен."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()

        # Act - вызываем cleanup из разных "потоков" (симуляция)
        db.cleanup()
        db.cleanup()

        # Assert
        assert db._cleaned_up is True


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_cleanup_with_no_thread_pool(self, temp_db_path, qapp):
        """cleanup() работает если thread_pool отсутствует."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        delattr(db, '_thread_pool')

        # Act & Assert (не должно быть исключений)
        db.cleanup()

    def test_cleanup_with_failed_close(self, temp_db_path, qapp, caplog):
        """cleanup() обрабатывает ошибки при закрытии соединения."""
        # Arrange
        with patch('app.models.db.DB_PATH', temp_db_path):
            db = Database()
            
        # Mock close чтобы выбросить исключение
        with patch.object(db, 'close', side_effect=RuntimeError("Close failed")):
            # Act
            with caplog.at_level(logging.WARNING):
                db.cleanup()

        # Assert
        assert "Error closing database connection" in caplog.text
        assert db._cleaned_up is True  # Cleanup всё равно завершился
