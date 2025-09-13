"""
migrations.py — инициализация/миграции БД через MigrationRunner и первичная
инициализация дефолтных данных. Перенос из app/models/db.py без изменения
поведения.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def initialize_or_migrate(
    *,
    db: Any,
    migrations_dir: Path,
    db_path: Path,
    db_lock,
    logger,
    MigrationRunnerClass,
) -> None:
    """Запускает миграции и инициализирует дефолтные данные для новой БД.

    Параметры соответствуют прежнему поведению Database.initialize_or_migrate().
    """
    is_new = not db_path.exists()

    # Запускаем миграции (создаст схему через 0001_init при необходимости)
    with db_lock:
        runner = MigrationRunnerClass(db.connection, migrations_dir)
        applied = runner.run_all_pending()
        logger.info("Миграции применены: %d", applied)

    # Инициализация дефолтных данных для новой базы (после миграций)
    if is_new:
        try:
            db.spheres.initialize_default_spheres()
        except Exception as init_err:
            logger.warning(
                "Не удалось инициализировать дефолтные сферы: %s",
                init_err,
                exc_info=True,
            )
