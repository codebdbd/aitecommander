"""CLI for database diagnostics and maintenance."""

import argparse
import json
import logging
import sys
from typing import Optional

from ..db import Database

logger = logging.getLogger(__name__)


def _log_duplicates_human(dups: dict) -> None:
    """Outputs duplicates in human-readable format."""
    logger.info("== Duplicates (case-insensitive) ==")
    for table in ("sphere", "section", "category"):
        groups = dups.get(table, []) or []
        logger.info("%s: %s group(s)", table, len(groups))
        for g in groups:
            scope = g.get("scope")
            lname = g.get("lname")
            ids = ",".join(str(i) for i in g.get("ids", []))
            logger.info("  - scope=%s, lname='%s', ids=[%s]", scope, lname, ids)


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI function for database operations."""
    parser = argparse.ArgumentParser(
        prog="python -m app.models.db",
        description="CLI for diagnostics and resolution of case-insensitive duplicates and DB maintenance",
    )

    mx = parser.add_mutually_exclusive_group(required=True)
    mx.add_argument(
        "--detect-duplicates",
        action="store_true",
        help="Find case-insensitive duplicates (sphere/section/category)",
    )
    mx.add_argument(
        "--resolve-duplicates",
        choices=["rename", "remove"],
        help="Resolve duplicates with strategy: rename or remove",
    )
    mx.add_argument(
        "--create-indexes",
        action="store_true",
        help="Create unique indexes with COLLATE NOCASE (if missing)",
    )
    mx.add_argument(
        "--backup",
        action="store_true",
        help="Create DB backup",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON (for detect/resolve)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to DB file (default — from app settings)",
    )
    parser.add_argument(
        "--create-indexes-after",
        action="store_true",
        help="After resolve run NOCASE index creation",
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
                    logger.info("== Resolve summary ==")
                    for k, v in (report or {}).items():
                        logger.info("%s: %s", k, v)
                return 0

            if args.create_indexes:
                db.create_nocase_unique_indexes()
                logger.info("NOCASE indexes created (if missing)")
                return 0

            if args.backup:
                db.backup()
                logger.info("Backup created")
                return 0

            parser.print_help()
            return 0
    except Exception as e:
        logger.error("CLI error: %s", e)
        logger.error("Error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
