"""CLI для обслуживания базы данных: поиск/устранение дубликатов, индексы, бэкап.

Запуск:
    python -m app.tools.database_cli --help

Примечание:
- CLI вынесен из app/models/db.py для чистого разделения обязанностей.
- Поведение флагов сохранено.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List, Optional

from app.models.db import Database  # фасад остаётся прежним

logger = logging.getLogger(__name__)


def _log_duplicates_human(dups: dict) -> None:
    logger.info("== Дубликаты (регистронезависимые) ==")
    for table in ("sphere", "section", "category"):
        groups = dups.get(table, []) or []
        logger.info("%s: %s групп(ы)", table, len(groups))
        for g in groups:
            scope = g.get("scope")
            lname = g.get("lname")
            ids = ",".join(str(i) for i in g.get("ids", []))
            logger.info("  - scope=%s, lname='%s', ids=[%s]", scope, lname, ids)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.tools.database_cli",
        description=(
            "CLI для диагностики и устранения регистронезависимых дубликатов и обслуживания БД"
        ),
    )

    mx = parser.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--detect-duplicates",
        action="store_true",
        help="Найти case-insensitive дубликаты (sphere/section/category)",
    )
    mx.add_argument(
        "--resolve-duplicates",
        choices=["rename", "remove"],
        help="Разрешить дубликаты стратегией: rename (переименовать) или remove (удалить)",
    )
    mx.add_argument(
        "--create-indexes",
        action="store_true",
        help="Создать уникальные индексы с COLLATE NOCASE (если их нет)",
    )
    mx.add_argument(
        "--backup",
        action="store_true",
        help="Создать резервную копию БД",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод в JSON (для detect/resolve)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Путь к файлу БД (по умолчанию — из настроек приложения)",
    )
    parser.add_argument(
        "--create-indexes-after",
        action="store_true",
        help="После resolve запустить создание NOCASE-индексов",
    )

    args = parser.parse_args(argv)

    try:
        with Database() as db:
            if args.db_path:
                db.db_path = args.db_path

            if args.detect_duplicates:
                dups = db.detect_case_insensitive_duplicates()
                if args.json:
                    logger.info(json.dumps(dups, ensure_ascii=False, indent=2))
                else:
                    _log_duplicates_human(dups)
                return 0

            if args.resolve_duplicates:
                report = db.resolve_case_insensitive_duplicates(args.resolve_duplicates)
                if args.create_indexes_after:
                    db.create_nocase_unique_indexes()
                if args.json:
                    logger.info(json.dumps(report, ensure_ascii=False, indent=2))
                else:
                    logger.info("== Итог resolve ==")
                    for k, v in (report or {}).items():
                        logger.info("%s: %s", k, v)
                return 0

            if args.create_indexes:
                db.create_nocase_unique_indexes()
                logger.info("NOCASE-индексы созданы (если отсутствовали)")
                return 0

            if args.backup:
                db.backup()
                logger.info("Резервная копия создана")
                return 0

            parser.print_help()
            return 0
    except Exception as e:
        logger.error("CLI ошибка: %s", e)
        logger.error("Ошибка: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
