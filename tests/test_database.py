"""Тесты для работы с базой данных."""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


@pytest.fixture
def temp_db():
    """Создаёт временную БД для тестов."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Создаём схему
    conn = sqlite3.Connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sphere (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            position INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS section (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sphere_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (sphere_id) REFERENCES sphere(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS category (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            section_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (section_id) REFERENCES section(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            type TEXT DEFAULT 'web',
            icon TEXT,
            notes TEXT,
            args TEXT,
            is_favorite INTEGER DEFAULT 0,
            last_used TEXT,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES category(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def db_with_data(temp_db):
    """БД с тестовыми данными."""
    conn = sqlite3.Connection(temp_db)
    
    # Добавляем sphere
    conn.execute("INSERT INTO sphere (id, name, position) VALUES (1, 'Work', 0)")
    
    # Добавляем section
    conn.execute("INSERT INTO section (id, name, sphere_id, position) VALUES (1, 'Development', 1, 0)")
    
    # Добавляем category
    conn.execute("INSERT INTO category (id, name, section_id, position) VALUES (1, 'Python', 1, 0)")
    
    # Добавляем links
    conn.execute("""
        INSERT INTO link (id, name, url, category_id, type, is_favorite, position)
        VALUES (1, 'Python Docs', 'https://docs.python.org', 1, 'web', 1, 0)
    """)
    conn.execute("""
        INSERT INTO link (id, name, url, category_id, type, is_favorite, position)
        VALUES (2, 'PyQt6 Docs', 'https://pyqt6.com', 1, 'web', 0, 1)
    """)
    conn.execute("""
        INSERT INTO link (id, name, url, category_id, type, last_used, position)
        VALUES (3, 'Recent Link', 'https://recent.com', 1, 'web', '2025-09-30 12:00:00', 2)
    """)
    
    conn.commit()
    conn.close()
    
    return temp_db


class TestDatabaseSchema:
    """Тесты схемы базы данных."""
    
    def test_database_creation(self, temp_db):
        """Тест создания базы данных."""
        assert Path(temp_db).exists()
        
        conn = sqlite3.Connection(temp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        assert 'sphere' in tables
        assert 'section' in tables
        assert 'category' in tables
        assert 'link' in tables
        
        conn.close()
    
    def test_foreign_key_constraints(self, temp_db):
        """Тест внешних ключей."""
        conn = sqlite3.Connection(temp_db)
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Создаём sphere
        conn.execute("INSERT INTO sphere (id, name) VALUES (1, 'Test')")
        
        # Создаём section с валидным sphere_id
        conn.execute("INSERT INTO section (id, name, sphere_id) VALUES (1, 'Test Section', 1)")
        
        # Попытка создать section с невалидным sphere_id
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO section (name, sphere_id) VALUES ('Invalid', 999)")
        
        conn.close()
    
    def test_cascade_delete(self, db_with_data):
        """Тест каскадного удаления."""
        conn = sqlite3.Connection(db_with_data)
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Проверяем, что есть links
        cursor = conn.execute("SELECT COUNT(*) FROM link")
        count_before = cursor.fetchone()[0]
        assert count_before > 0
        
        # Удаляем sphere (должно удалить section, category, link)
        conn.execute("DELETE FROM sphere WHERE id = 1")
        conn.commit()
        
        # Проверяем, что links удалены
        cursor = conn.execute("SELECT COUNT(*) FROM link")
        count_after = cursor.fetchone()[0]
        assert count_after == 0
        
        conn.close()


class TestDatabaseQueries:
    """Тесты SQL запросов."""
    
    def test_select_all_links(self, db_with_data):
        """Тест выборки всех ссылок."""
        conn = sqlite3.Connection(db_with_data)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("SELECT * FROM link ORDER BY position")
        links = [dict(row) for row in cursor.fetchall()]
        
        assert len(links) == 3
        assert links[0]['name'] == 'Python Docs'
        
        conn.close()
    
    def test_select_favorite_links(self, db_with_data):
        """Тест выборки избранных ссылок."""
        conn = sqlite3.Connection(db_with_data)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("SELECT * FROM link WHERE is_favorite = 1")
        favorites = [dict(row) for row in cursor.fetchall()]
        
        assert len(favorites) == 1
        assert favorites[0]['name'] == 'Python Docs'
        
        conn.close()
    
    def test_select_recent_links(self, db_with_data):
        """Тест выборки недавних ссылок."""
        conn = sqlite3.Connection(db_with_data)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT * FROM link 
            WHERE last_used IS NOT NULL 
            ORDER BY last_used DESC 
            LIMIT 10
        """)
        recent = [dict(row) for row in cursor.fetchall()]
        
        assert len(recent) == 1
        assert recent[0]['name'] == 'Recent Link'
        
        conn.close()
    
    def test_search_links(self, db_with_data):
        """Тест поиска ссылок."""
        conn = sqlite3.Connection(db_with_data)
        conn.row_factory = sqlite3.Row
        
        query = "Python"
        cursor = conn.execute("""
            SELECT * FROM link 
            WHERE name LIKE ? OR url LIKE ? OR notes LIKE ?
        """, (f'%{query}%', f'%{query}%', f'%{query}%'))
        
        results = [dict(row) for row in cursor.fetchall()]
        
        assert len(results) >= 1
        assert any('Python' in link['name'] for link in results)
        
        conn.close()
    
    def test_update_link(self, db_with_data):
        """Тест обновления ссылки."""
        conn = sqlite3.Connection(db_with_data)
        
        # Обновляем имя
        conn.execute("UPDATE link SET name = ? WHERE id = ?", ('Updated Name', 1))
        conn.commit()
        
        # Проверяем обновление
        cursor = conn.execute("SELECT name FROM link WHERE id = 1")
        name = cursor.fetchone()[0]
        
        assert name == 'Updated Name'
        
        conn.close()
    
    def test_delete_link(self, db_with_data):
        """Тест удаления ссылки."""
        conn = sqlite3.Connection(db_with_data)
        
        # Подсчитываем до удаления
        cursor = conn.execute("SELECT COUNT(*) FROM link")
        count_before = cursor.fetchone()[0]
        
        # Удаляем
        conn.execute("DELETE FROM link WHERE id = 1")
        conn.commit()
        
        # Подсчитываем после
        cursor = conn.execute("SELECT COUNT(*) FROM link")
        count_after = cursor.fetchone()[0]
        
        assert count_after == count_before - 1
        
        conn.close()


class TestDatabaseIndexes:
    """Тесты индексов базы данных (миграция 0005)."""
    
    def test_create_indexes(self, temp_db):
        """Тест создания индексов."""
        conn = sqlite3.Connection(temp_db)
        
        # Создаём индексы
        conn.execute("CREATE INDEX IF NOT EXISTS idx_link_category_id ON link(category_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_link_last_used ON link(last_used DESC) WHERE last_used IS NOT NULL")
        
        # Проверяем создание
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='link'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        
        assert 'idx_link_category_id' in indexes
        assert 'idx_link_is_favorite' in indexes
        assert 'idx_link_last_used' in indexes
        
        conn.close()
    
    def test_index_improves_query(self, db_with_data):
        """Тест улучшения производительности запроса с индексом."""
        conn = sqlite3.Connection(db_with_data)
        
        # Создаём индекс
        conn.execute("CREATE INDEX idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1")
        
        # Проверяем план запроса
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM link WHERE is_favorite = 1")
        plan = cursor.fetchall()
        
        # План должен использовать индекс (содержит "SEARCH" или "INDEX")
        plan_text = str(plan).upper()
        assert "INDEX" in plan_text or "SEARCH" in plan_text
        
        conn.close()


class TestDatabaseTransactions:
    """Тесты транзакций."""
    
    def test_commit_saves_changes(self, temp_db):
        """Тест сохранения изменений при commit."""
        conn = sqlite3.Connection(temp_db)
        
        conn.execute("INSERT INTO sphere (name) VALUES ('Test Sphere')")
        conn.commit()
        
        # Проверяем в новом подключении
        conn2 = sqlite3.Connection(temp_db)
        cursor = conn2.execute("SELECT COUNT(*) FROM sphere WHERE name = 'Test Sphere'")
        count = cursor.fetchone()[0]
        
        assert count == 1
        
        conn.close()
        conn2.close()
    
    def test_rollback_discards_changes(self, temp_db):
        """Тест отмены изменений при rollback."""
        conn = sqlite3.Connection(temp_db)
        
        conn.execute("INSERT INTO sphere (name) VALUES ('Temp Sphere')")
        conn.rollback()
        
        # Проверяем, что изменений нет
        cursor = conn.execute("SELECT COUNT(*) FROM sphere WHERE name = 'Temp Sphere'")
        count = cursor.fetchone()[0]
        
        assert count == 0
        
        conn.close()
    
    def test_transaction_isolation(self, db_with_data):
        """Тест изоляции транзакций."""
        conn1 = sqlite3.Connection(db_with_data)
        conn2 = sqlite3.Connection(db_with_data)
        
        # conn1 начинает транзакцию и обновляет
        conn1.execute("BEGIN")
        conn1.execute("UPDATE link SET name = 'Changed' WHERE id = 1")
        
        # conn2 не видит изменений до commit
        cursor = conn2.execute("SELECT name FROM link WHERE id = 1")
        name = cursor.fetchone()[0]
        assert name != 'Changed'
        
        # conn1 делает commit
        conn1.commit()
        
        # Теперь conn2 видит изменения
        cursor = conn2.execute("SELECT name FROM link WHERE id = 1")
        name = cursor.fetchone()[0]
        assert name == 'Changed'
        
        conn1.close()
        conn2.close()


class TestDatabaseMigrations:
    """Тесты миграций базы данных."""
    
    def test_migration_version_tracking(self, temp_db):
        """Тест отслеживания версии схемы."""
        conn = sqlite3.Connection(temp_db)
        
        # Устанавливаем версию
        conn.execute("PRAGMA user_version = 5")
        
        # Проверяем версию
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        
        assert version == 5
        
        conn.close()
    
    def test_migration_0005_indexes(self, temp_db):
        """Тест применения миграции 0005 (индексы)."""
        conn = sqlite3.Connection(temp_db)
        
        # Симулируем миграцию 0005
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_link_category_id ON link(category_id)",
            "CREATE INDEX IF NOT EXISTS idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1",
            "CREATE INDEX IF NOT EXISTS idx_link_last_used ON link(last_used DESC) WHERE last_used IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_link_category_position ON link(category_id, position)",
            "CREATE INDEX IF NOT EXISTS idx_link_type ON link(type)",
        ]
        
        for index_sql in indexes:
            conn.execute(index_sql)
        
        # Обновляем версию
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
        
        # Проверяем версию
        cursor = conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version == 5
        
        # Проверяем индексы
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='link'
        """)
        indexes_created = [row[0] for row in cursor.fetchall()]
        
        assert len(indexes_created) >= 5
        
        conn.close()


class TestDatabasePerformance:
    """Тесты производительности базы данных."""
    
    def test_bulk_insert_performance(self, temp_db):
        """Тест производительности массовой вставки."""
        import time
        
        conn = sqlite3.Connection(temp_db)
        
        # Создаём sphere и section для FK
        conn.execute("INSERT INTO sphere (id, name) VALUES (1, 'Test')")
        conn.execute("INSERT INTO section (id, name, sphere_id) VALUES (1, 'Test', 1)")
        conn.execute("INSERT INTO category (id, name, section_id) VALUES (1, 'Test', 1)")
        conn.commit()
        
        # Вставляем 1000 ссылок
        start_time = time.time()
        
        conn.execute("BEGIN")
        for i in range(1000):
            conn.execute("""
                INSERT INTO link (name, url, category_id, position)
                VALUES (?, ?, ?, ?)
            """, (f'Link {i}', f'https://example.com/{i}', 1, i))
        conn.commit()
        
        elapsed = time.time() - start_time
        
        # Должно занять < 1 секунды
        assert elapsed < 1.0
        
        # Проверяем количество
        cursor = conn.execute("SELECT COUNT(*) FROM link")
        count = cursor.fetchone()[0]
        assert count == 1000
        
        conn.close()
    
    @pytest.mark.slow
    def test_query_performance_with_index(self, temp_db):
        """Тест производительности запроса с индексом."""
        import time
        
        conn = sqlite3.Connection(temp_db)
        
        # Подготовка данных
        conn.execute("INSERT INTO sphere (id, name) VALUES (1, 'Test')")
        conn.execute("INSERT INTO section (id, name, sphere_id) VALUES (1, 'Test', 1)")
        conn.execute("INSERT INTO category (id, name, section_id) VALUES (1, 'Test', 1)")
        
        # Вставляем 10000 ссылок
        conn.execute("BEGIN")
        for i in range(10000):
            is_fav = 1 if i % 10 == 0 else 0
            conn.execute("""
                INSERT INTO link (name, url, category_id, is_favorite, position)
                VALUES (?, ?, ?, ?, ?)
            """, (f'Link {i}', f'https://example.com/{i}', 1, is_fav, i))
        conn.commit()
        
        # Создаём индекс
        conn.execute("CREATE INDEX idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1")
        
        # Измеряем скорость запроса
        start_time = time.time()
        cursor = conn.execute("SELECT * FROM link WHERE is_favorite = 1")
        favorites = cursor.fetchall()
        elapsed = time.time() - start_time
        
        # Должно быть быстро (< 0.1 секунды)
        assert elapsed < 0.1
        assert len(favorites) == 1000  # Каждый 10-й = 1000 из 10000
        
        conn.close()
