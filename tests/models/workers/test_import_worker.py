"""Tests for ImportStructureWorker."""
import tempfile
import sqlite3
import pytest

from app.models.workers import ImportStructureWorker


@pytest.fixture
def temp_db():
    """Создает временную тестовую БД со схемой."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    
    # Создаем схему
    conn.execute("""
        CREATE TABLE sphere (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon_path TEXT DEFAULT '',
            position INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE section (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sphere_id INTEGER NOT NULL,
            icon_path TEXT DEFAULT '',
            position INTEGER DEFAULT 0,
            FOREIGN KEY (sphere_id) REFERENCES sphere(id)
        )
    """)
    conn.execute("""
        CREATE TABLE category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            section_id INTEGER NOT NULL,
            icon_path TEXT DEFAULT '',
            position INTEGER DEFAULT 0,
            FOREIGN KEY (section_id) REFERENCES section(id)
        )
    """)
    conn.execute("""
        CREATE TABLE link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            args TEXT DEFAULT '',
            type TEXT DEFAULT 'web',
            browser_key TEXT DEFAULT '',
            icon_path TEXT DEFAULT '',
            position INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES category(id)
        )
    """)
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    from pathlib import Path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def test_data():
    """Тестовые данные для импорта."""
    return [
        {
            "name": "Test Sphere",
            "icon_path": "test.ico",
            "position": 0,
            "sections": [
                {
                    "name": "Test Section",
                    "icon_path": "",
                    "position": 0,
                    "categories": [
                        {
                            "name": "Test Category",
                            "icon_path": "",
                            "position": 0,
                            "links": [
                                {
                                    "name": "Test Link",
                                    "url": "https://test.com",
                                    "args": "",
                                    "type": "web",
                                    "browser_key": "",
                                    "icon_path": "",
                                    "position": 0
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]


def test_import_worker_success(temp_db, test_data):
    """Тест успешного импорта структуры."""
    worker = ImportStructureWorker(temp_db, test_data)
    connection = worker.create_connection()
    
    result = worker.do_work(connection)
    
    # Проверяем статистику
    assert result['spheres'] == 1
    assert result['sections'] == 1
    assert result['categories'] == 1
    assert result['links'] == 1
    
    # Проверяем что данные действительно в БД
    cursor = connection.execute("SELECT COUNT(*) FROM sphere")
    assert cursor.fetchone()[0] == 1
    
    cursor = connection.execute("SELECT COUNT(*) FROM link")
    assert cursor.fetchone()[0] == 1
    
    connection.close()


def test_import_worker_empty_data(temp_db):
    """Тест импорта пустых данных."""
    worker = ImportStructureWorker(temp_db, [])
    connection = worker.create_connection()
    
    result = worker.do_work(connection)
    
    # Должны быть нулевые значения
    assert result['spheres'] == 0
    assert result['sections'] == 0
    assert result['categories'] == 0
    assert result['links'] == 0
    
    connection.close()


def test_import_worker_cancelled(temp_db, test_data):
    """Тест отмены импорта."""
    worker = ImportStructureWorker(temp_db, test_data)
    
    # Отменяем сразу
    worker.cancel()
    
    connection = worker.create_connection()
    result = worker.do_work(connection)
    
    # При отмене должен вернуть пустой dict
    assert result == {}
    
    # Данных в БД не должно быть
    cursor = connection.execute("SELECT COUNT(*) FROM sphere")
    assert cursor.fetchone()[0] == 0
    
    connection.close()


def test_import_worker_clears_existing_data(temp_db, test_data):
    """Тест что импорт очищает существующие данные."""
    conn = sqlite3.connect(temp_db)
    
    # Добавляем существующие данные
    conn.execute("INSERT INTO sphere (name) VALUES ('Old Sphere')")
    conn.commit()
    conn.close()
    
    # Импортируем новые данные
    worker = ImportStructureWorker(temp_db, test_data)
    connection = worker.create_connection()
    result = worker.do_work(connection)
    
    # Проверяем что старые данные удалены
    cursor = connection.execute("SELECT name FROM sphere")
    names = [row[0] for row in cursor.fetchall()]
    assert 'Old Sphere' not in names
    assert 'Test Sphere' in names
    
    connection.close()
