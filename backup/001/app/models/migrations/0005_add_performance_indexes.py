"""
Миграция 0005: Добавление индексов для повышения производительности запросов.

Создаёт индексы на часто запрашиваемых колонках для ускорения:
- Загрузки ссылок по категории
- Фильтрации избранного
- Сортировки недавних ссылок
- Поиска по структуре
- Фильтрации по типу и аргументам
"""

import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Создаёт индексы для повышения производительности запросов."""
    
    # Индексы для таблицы link
    indexes = [
        # Самый критичный: загрузка ссылок по категории
        # Используется в: get_links(), get_links_count(), batch операции
        (
            "idx_link_category_id",
            "CREATE INDEX IF NOT EXISTS idx_link_category_id ON link(category_id)"
        ),
        
        # Для быстрой фильтрации избранного
        # Используется в: get_favorite_links(), count_favorites(), clear_favorites()
        (
            "idx_link_is_favorite",
            "CREATE INDEX IF NOT EXISTS idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1"
        ),
        
        # Для сортировки недавних ссылок (partial index для NOT NULL)
        # Используется в: get_recent_links()
        (
            "idx_link_last_used",
            "CREATE INDEX IF NOT EXISTS idx_link_last_used ON link(last_used DESC) WHERE last_used IS NOT NULL"
        ),
        
        # Составной индекс для загрузки ссылок категории с сортировкой по position
        # Покрывает самый частый запрос: SELECT ... WHERE category_id = ? ORDER BY position
        (
            "idx_link_category_position",
            "CREATE INDEX IF NOT EXISTS idx_link_category_position ON link(category_id, position)"
        ),
        
        # Для поиска дубликатов и проверки уникальности
        # Используется в: find_duplicate(), get_link_by_unique_key()
        (
            "idx_link_category_name_url_args",
            "CREATE INDEX IF NOT EXISTS idx_link_category_name_url_args ON link(category_id, name, url, args)"
        ),
        
        # Для фильтрации по типу ссылки
        # Используется в: get_links_by_args_pattern() (type = 'web')
        (
            "idx_link_type",
            "CREATE INDEX IF NOT EXISTS idx_link_type ON link(type)"
        ),
        
        # Индексы для таблицы section
        # Используется в: get_sections_by_sphere(), get_section_order()
        (
            "idx_section_sphere_id",
            "CREATE INDEX IF NOT EXISTS idx_section_sphere_id ON section(sphere_id)"
        ),
        
        # Составной индекс для загрузки разделов сферы с сортировкой
        (
            "idx_section_sphere_position",
            "CREATE INDEX IF NOT EXISTS idx_section_sphere_position ON section(sphere_id, position)"
        ),
        
        # Индексы для таблицы category
        # Используется в: get_categories_by_section(), get_categories_by_sections()
        (
            "idx_category_section_id",
            "CREATE INDEX IF NOT EXISTS idx_category_section_id ON category(section_id)"
        ),
        
        # Составной индекс для загрузки категорий раздела с сортировкой
        (
            "idx_category_section_position",
            "CREATE INDEX IF NOT EXISTS idx_category_section_position ON category(section_id, position)"
        ),
    ]
    
    created_count = 0
    for index_name, sql in indexes:
        try:
            conn.execute(sql)
            created_count += 1
            logger.debug(f"Миграция 0005: создан индекс {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(
                f"Миграция 0005: не удалось создать индекс {index_name}: {e}"
            )
            # Продолжаем создание других индексов, даже если один упал
    
    logger.info(
        f"Миграция 0005: создано {created_count}/{len(indexes)} индексов производительности"
    )
    
    # Анализируем таблицы для обновления статистики оптимизатора
    try:
        conn.execute("ANALYZE")
        logger.info("Миграция 0005: статистика БД обновлена (ANALYZE)")
    except sqlite3.OperationalError as e:
        logger.warning(f"Миграция 0005: не удалось выполнить ANALYZE: {e}")


def rollback(conn: sqlite3.Connection, logger: Any) -> None:
    """Откатывает миграцию, удаляя созданные индексы."""
    
    indexes_to_drop = [
        "idx_link_category_id",
        "idx_link_is_favorite",
        "idx_link_last_used",
        "idx_link_category_position",
        "idx_link_category_name_url_args",
        "idx_link_type",
        "idx_section_sphere_id",
        "idx_section_sphere_position",
        "idx_category_section_id",
        "idx_category_section_position",
    ]
    
    dropped_count = 0
    for index_name in indexes_to_drop:
        try:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            dropped_count += 1
            logger.debug(f"Rollback 0005: удалён индекс {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Rollback 0005: не удалось удалить индекс {index_name}: {e}")
    
    logger.info(f"Rollback 0005: удалено {dropped_count}/{len(indexes_to_drop)} индексов")
