"""
Скрипт для проверки и анализа индексов в базе данных.

Использование:
    python scripts/check_db_indexes.py
    
Выводит:
- Список существующих индексов
- Отсутствующие индексы
- Размеры таблиц
- Рекомендации по оптимизации
"""

import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config_data import app_config

# Путь к БД
DB_PATH = app_config.paths.get_db_path()


def get_all_indexes(conn: sqlite3.Connection) -> List[Tuple[str, str, str]]:
    """Возвращает список всех индексов в БД."""
    cursor = conn.execute(
        """
        SELECT name, tbl_name, sql 
        FROM sqlite_master 
        WHERE type = 'index' 
        AND sql IS NOT NULL
        ORDER BY tbl_name, name
        """
    )
    return cursor.fetchall()


def get_table_info(conn: sqlite3.Connection, table_name: str) -> dict:
    """Возвращает информацию о таблице."""
    # Количество записей
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    
    # Структура таблицы
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    return {
        "count": count,
        "columns": [col[1] for col in columns],  # col[1] = имя колонки
    }


def analyze_query_plan(conn: sqlite3.Connection, query: str, params: tuple = ()) -> List[str]:
    """Анализирует план выполнения запроса."""
    cursor = conn.execute(f"EXPLAIN QUERY PLAN {query}", params)
    return [row[3] for row in cursor.fetchall()]  # row[3] = detail


def print_section(title: str):
    """Печатает заголовок секции."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def main():
    """Основная функция проверки индексов."""
    
    if not DB_PATH.exists():
        print(f"❌ База данных не найдена: {DB_PATH}")
        return 1
    
    print(f"📊 Анализ базы данных: {DB_PATH}\n")
    
    conn = sqlite3.connect(str(DB_PATH))
    
    try:
        # 1. Существующие индексы
        print_section("1. СУЩЕСТВУЮЩИЕ ИНДЕКСЫ")
        indexes = get_all_indexes(conn)
        
        if not indexes:
            print("⚠️  Индексы не найдены!")
        else:
            current_table = None
            for idx_name, tbl_name, sql in indexes:
                if tbl_name != current_table:
                    print(f"\n📋 Таблица: {tbl_name}")
                    current_table = tbl_name
                print(f"  ✓ {idx_name}")
                if sql:
                    # Форматируем SQL для читаемости
                    sql_short = sql.replace("\n", " ").replace("  ", " ")
                    if len(sql_short) > 80:
                        sql_short = sql_short[:77] + "..."
                    print(f"    {sql_short}")
        
        # 2. Размеры таблиц
        print_section("2. РАЗМЕРЫ ТАБЛИЦ")
        tables = ["sphere", "section", "category", "link"]
        for table in tables:
            info = get_table_info(conn, table)
            print(f"  {table:12} : {info['count']:>6} записей")
        
        # 3. Критичные запросы без индексов
        print_section("3. АНАЛИЗ КРИТИЧНЫХ ЗАПРОСОВ")
        
        critical_queries = [
            (
                "Загрузка ссылок по категории",
                "SELECT * FROM link WHERE category_id = ? ORDER BY position",
                (1,)
            ),
            (
                "Поиск избранного",
                "SELECT * FROM link WHERE is_favorite = 1",
                ()
            ),
            (
                "Недавние ссылки",
                "SELECT * FROM link WHERE last_used IS NOT NULL ORDER BY last_used DESC LIMIT 10",
                ()
            ),
            (
                "Поиск с JOIN",
                """SELECT l.* FROM link l 
                   JOIN category cat ON l.category_id = cat.id 
                   JOIN section sect ON cat.section_id = sect.id 
                   WHERE l.name LIKE ? LIMIT 10""",
                ("%test%",)
            ),
        ]
        
        for query_name, query, params in critical_queries:
            print(f"\n🔍 {query_name}:")
            try:
                plan = analyze_query_plan(conn, query, params)
                for line in plan:
                    # Проверяем наличие SCAN (плохо) vs SEARCH (хорошо)
                    if "SCAN" in line:
                        print(f"  ⚠️  {line}")
                    elif "SEARCH" in line and "USING INDEX" in line:
                        print(f"  ✅ {line}")
                    else:
                        print(f"     {line}")
            except sqlite3.OperationalError as e:
                print(f"  ❌ Ошибка анализа: {e}")
        
        # 4. Рекомендации
        print_section("4. РЕКОМЕНДАЦИИ")
        
        # Проверяем наличие критичных индексов
        index_names = [idx[0] for idx in indexes]
        
        recommendations = [
            ("idx_link_category_id", "Критичный индекс для загрузки ссылок по категории"),
            ("idx_link_is_favorite", "Для быстрой фильтрации избранного"),
            ("idx_link_last_used", "Для сортировки недавних ссылок"),
            ("idx_link_category_position", "Составной индекс для сортировки в категории"),
            ("idx_section_sphere_id", "Для загрузки разделов сферы"),
            ("idx_category_section_id", "Для загрузки категорий раздела"),
        ]
        
        missing = []
        for idx_name, description in recommendations:
            if idx_name not in index_names:
                missing.append((idx_name, description))
        
        if missing:
            print("\n⚠️  ОТСУТСТВУЮЩИЕ ИНДЕКСЫ:")
            for idx_name, description in missing:
                print(f"  ❌ {idx_name}")
                print(f"     └─ {description}")
            
            print("\n💡 Для создания индексов выполните миграцию:")
            print("   1. Перезапустите приложение (миграция 0005 выполнится автоматически)")
            print("   2. Или выполните вручную:")
            print(f"      sqlite3 {DB_PATH} < app/models/migrations/0005_add_performance_indexes.sql")
        else:
            print("\n✅ Все рекомендуемые индексы присутствуют!")
        
        # 5. Статистика оптимизатора
        print_section("5. СТАТИСТИКА ОПТИМИЗАТОРА")
        cursor = conn.execute("PRAGMA optimize")
        print("  Выполнение PRAGMA optimize...")
        
        cursor = conn.execute("SELECT * FROM sqlite_stat1 LIMIT 5")
        stats = cursor.fetchall()
        if stats:
            print("\n  Статистика sqlite_stat1 (первые 5 записей):")
            for row in stats:
                print(f"    {row}")
        else:
            print("\n  ⚠️  Статистика не собрана. Рекомендуется выполнить ANALYZE.")
            print("     sqlite3 {DB_PATH} 'ANALYZE'")
        
    finally:
        conn.close()
    
    print("\n" + "="*70)
    print("✅ Анализ завершён\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
