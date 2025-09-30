"""
Скрипт для ручного применения миграции 0005 (индексы производительности).

Использование:
    python scripts/apply_migration_0005.py
"""

import sqlite3
import sys
from pathlib import Path

# Добавляем корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config_data import app_config

# Импортируем миграцию динамически, т.к. имя файла начинается с цифры
import importlib.util
spec = importlib.util.spec_from_file_location(
    "migration_0005",
    project_root / "app" / "models" / "migrations" / "0005_add_performance_indexes.py"
)
migration_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_module)
migrate = migration_module.migrate

# Путь к БД
DB_PATH = app_config.paths.get_db_path()


class SimpleLogger:
    """Простой логгер для миграции."""
    
    def info(self, msg, *args):
        print(f"ℹ️  {msg % args if args else msg}")
    
    def debug(self, msg, *args):
        print(f"🔍 {msg % args if args else msg}")
    
    def warning(self, msg, *args):
        print(f"⚠️  {msg % args if args else msg}")
    
    def error(self, msg, *args):
        print(f"❌ {msg % args if args else msg}")


def main():
    """Применяет миграцию 0005."""
    
    if not DB_PATH.exists():
        print(f"❌ База данных не найдена: {DB_PATH}")
        return 1
    
    print(f"📊 Применение миграции 0005 к БД: {DB_PATH}\n")
    
    conn = sqlite3.connect(str(DB_PATH))
    logger = SimpleLogger()
    
    try:
        # Проверяем текущую версию схемы
        cursor = conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]
        print(f"Текущая версия схемы: {current_version}\n")
        
        # Применяем миграцию
        print("="*70)
        print("  ПРИМЕНЕНИЕ МИГРАЦИИ 0005")
        print("="*70)
        
        migrate(conn, logger)
        
        # Сохраняем изменения
        conn.commit()
        
        print("\n" + "="*70)
        print("✅ Миграция успешно применена!")
        print("="*70)
        
        # Обновляем версию схемы (если нужно)
        if current_version < 5:
            conn.execute(f"PRAGMA user_version = 5")
            conn.commit()
            print(f"\n📌 Версия схемы обновлена: {current_version} → 5")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Ошибка применения миграции: {e}")
        conn.rollback()
        return 1
        
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
