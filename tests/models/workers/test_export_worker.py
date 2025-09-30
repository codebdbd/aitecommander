"""Tests for ExportStructureWorker."""
import tempfile
import sqlite3
import pytest

from app.models.workers import ExportStructureWorker


@pytest.fixture
def temp_db_with_data():
    """Создает временную БД с тестовыми данными."""
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
    
    # Добавляем тестовые данные
    conn.execute("INSERT INTO sphere (name, icon_path, position) VALUES ('Test Sphere', 'test.ico', 0)")
    sphere_id = conn.lastrowid
    
    conn.execute("INSERT INTO section (name, sphere_id, icon_path, position) VALUES ('Test Section', ?, '', 0)", (sphere_id,))
    section_id = conn.lastrowid
    
    conn.execute("INSERT INTO category (name, section_id, icon_path, position) VALUES ('Test Category', ?, '', 0)", (section_id,))
    category_id = conn.lastrowid
    
    conn.execute("""
        INSERT INTO link (category_id, name, url, args, type, browser_key, icon_path, position)
        VALUES (?, 'Test Link', 'https://test.com', '', 'web', '', '', 0)
    """, (category_id,))
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    from pathlib import Path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def empty_db():
    """Создает пустую БД."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    conn = sqlite3.connect(db_path)
    
    # Создаем схему без данных
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT, icon_path TEXT, position INTEGER)")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, name TEXT, sphere_id INTEGER, icon_path TEXT, position INTEGER)")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, name TEXT, section_id INTEGER, icon_path TEXT, position INTEGER)")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, url TEXT, args TEXT, type TEXT, browser_key TEXT, icon_path TEXT, position INTEGER)")
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    from pathlib import Path
    Path(db_path).unlink(missing_ok=True)


def test_export_worker_success(temp_db_with_data):
    """Тест успешного экспорта структуры."""
    worker = ExportStructureWorker(temp_db_with_data)
    connection = worker.create_connection()
    
    result = worker.do_work(connection)
    
    # Проверяем структуру результата
    assert result is not None
    assert 'spheres' in result
    assert 'sections' in result
    assert 'categories' in result
    assert 'links' in result
    
    # Проверяем количество записей
    assert len(result['spheres']) == 1
    assert len(result['sections']) == 1
    assert len(result['categories']) == 1
    assert len(result['links']) == 1
    
    # Проверяем содержимое
    sphere = result['spheres'][0]
    assert sphere['name'] == 'Test Sphere'
    assert sphere['icon_path'] == 'test.ico'
    
    link = result['links'][0]
    assert link['name'] == 'Test Link'
    assert link['url'] == 'https://test.com'
    
    connection.close()


def test_export_worker_empty_database(empty_db):
    """Тест экспорта пустой БД."""
    worker = ExportStructureWorker(empty_db)
    connection = worker.create_connection()
    
    result = worker.do_work(connection)
    
    # Проверяем что структура есть, но пустая
    assert result is not None
    assert len(result['spheres']) == 0
    assert len(result['sections']) == 0
    assert len(result['categories']) == 0
    assert len(result['links']) == 0
    
    connection.close()


def test_export_worker_cancelled(temp_db_with_data):
    """Тест отмены экспорта."""
    worker = ExportStructureWorker(temp_db_with_data)
    
    # Отменяем операцию
    worker.cancel()
    
    connection = worker.create_connection()
    result = worker.do_work(connection)
    
    # При отмене должен вернуть пустой dict
    assert result == {}
    
    connection.close()


def test_export_worker_progress_updates(temp_db_with_data):
    """Тест что worker отправляет обновления прогресса."""
    worker = ExportStructureWorker(temp_db_with_data)
    
    progress_calls = []
    
    # Подключаемся к сигналу прогресса
    worker.signals.progress.connect(
        lambda c, t, m: progress_calls.append((c, t, m))
    )
    
    connection = worker.create_connection()
    result = worker.do_work(connection)
    
    # Проверяем что были вызовы прогресса
    assert len(progress_calls) > 0
    
    # Проверяем финальный прогресс
    final_call = progress_calls[-1]
    assert final_call[0] == final_call[1]  # current == total
    assert "завершен" in final_call[2].lower()
    
    connection.close()


def test_export_worker_large_dataset(temp_db_with_data):
    """Тест экспорта большого набора данных."""
    # Добавляем больше данных
    conn = sqlite3.connect(temp_db_with_data)
    
    # Добавляем 10 сфер
    for i in range(10):
        conn.execute(f"INSERT INTO sphere (name, icon_path, position) VALUES ('Sphere {i}', '', {i})")
    
    # Добавляем 50 разделов
    for i in range(50):
        sphere_id = (i % 10) + 1  # Распределяем по сферам
        conn.execute(f"INSERT INTO section (name, sphere_id, position) VALUES ('Section {i}', {sphere_id}, {i})")
    
    conn.commit()
    conn.close()
    
    worker = ExportStructureWorker(temp_db_with_data)
    connection = worker.create_connection()
    
    result = worker.do_work(connection)
    
    # Проверяем что экспортировано много данных
    assert len(result['spheres']) >= 10
    assert len(result['sections']) >= 50
    
    connection.close()
