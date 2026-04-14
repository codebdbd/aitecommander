"""CLI for database diagnostics and maintenance."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TypedDict

from app.core.database_manager import DatabaseManager

from ..db import Database
from ..types.constants import DUPLICATE_CHECK_TABLES

logger = logging.getLogger(__name__)


class DuplicateGroup(TypedDict):
    """Structure for duplicate group information."""
    scope: str
    lname: str
    ids: list[int]


DuplicatesReport = dict[str, list[DuplicateGroup]]


def _log_duplicates_human(dups: DuplicatesReport) -> None:
    """Outputs duplicates in human-readable format."""
    logger.info("== Duplicates (case-insensitive) ==")
    for table in DUPLICATE_CHECK_TABLES:
        groups = dups.get(table, [])
        logger.info("%s: %s group(s)", table, len(groups))
        for g in groups:
            # TypedDict guarantees these keys exist
            scope = g["scope"]
            lname = g["lname"]
            ids = ",".join(str(i) for i in g["ids"])
            logger.info("  - scope=%s, lname='%s', ids=[%s]", scope, lname, ids)


def _show_duplicates(db: Database, as_json: bool) -> None:
    """Show duplicates in requested format (JSON or human-readable).
    
    Args:
        db: Database instance
        as_json: If True, output JSON to stdout; otherwise use logger
    """
    dups = db.detect_case_insensitive_duplicates()
    if as_json:
        print(json.dumps(dups, ensure_ascii=False, indent=2))
    else:
        _log_duplicates_human(dups)


def _setup_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging level based on flags."""
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )


def _validate_db_path_arg(db_path_str: str | None) -> Path | None:
    """Validate --db-path, returning resolved Path or None on missing/invalid."""
    if not db_path_str:
        return None
    db_path = Path(db_path_str)
    if not db_path.exists():
        logger.error("Database file not found: %s", db_path)
        return None
    if not db_path.is_file():
        logger.error("Path is not a file: %s", db_path)
        return None
    return db_path.resolve()


def _configure_database(validated_path: Path | None) -> None:
    """Configure DatabaseManager with optional path."""
    if validated_path:
        DatabaseManager.configure(validated_path)
    else:
        DatabaseManager.configure()


def _confirm_destructive_remove(args) -> bool:
    """Ask for confirmation for destructive remove unless --yes passed."""
    if args.resolve_duplicates == "remove" and not args.yes:
        try:
            confirm = input("\u26a0\ufe0f  This will DELETE duplicate records. Continue? [y/N]: ")
            if confirm.lower() != "y":
                logger.info("Operation cancelled by user")
                return False
        except (EOFError, KeyboardInterrupt):
            logger.info("\nOperation cancelled by user")
            return False
    return True


def _run_cli_action(args, db: Database) -> int:
    """Dispatch action based on parsed args."""
    if args.detect_duplicates:
        _show_duplicates(db, args.json)
        return 0

    if args.resolve_duplicates:
        if args.dry_run:
            logger.info(
                "DRY RUN: Would resolve duplicates with strategy '%s'",
                args.resolve_duplicates,
            )
            _show_duplicates(db, as_json=False)
            logger.info("Use without --dry-run to apply changes")
            return 0

        if not _confirm_destructive_remove(args):
            return 0

        report = db.resolve_case_insensitive_duplicates(args.resolve_duplicates)
        if args.create_indexes_after:
            db.create_nocase_unique_indexes()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
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
        logger.info("Creating backup...")
        result = db.backup()
        logger.info("Backup created: %s", result)
        return 0

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI function for database operations."""
    parser = argparse.ArgumentParser(
        prog="python -m app.models.db",
        description=(
            "CLI for diagnostics and resolution of case-insensitive duplicates and DB maintenance"
        ),
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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (DEBUG level)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Show what would be done without making changes (for resolve operations)"
        ),
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts (use with caution)",
    )

    args = parser.parse_args(argv)

    _setup_logging(args.verbose, args.quiet)

    validated_db_path = _validate_db_path_arg(args.db_path)
    if args.db_path and validated_db_path is None:
        return 1

    _configure_database(validated_db_path)

    try:
        with Database() as db:
            if validated_db_path:
                db.db_path = str(validated_db_path)  # type: ignore[assignment]

            rc = _run_cli_action(args, db)
            if rc != 0 or any(
                (
                    args.detect_duplicates,
                    args.resolve_duplicates,
                    args.create_indexes,
                    args.backup,
                )
            ):
                return rc

            parser.print_help()
            return 0
    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user")
        return 130  # Standard exit code for Ctrl+C
    except PermissionError as e:
        logger.error("Permission denied: %s", e)
        logger.error("Check file permissions and try again")
        return 1
    except FileNotFoundError as e:
        logger.error("File not found: %s", e)
        logger.error("Database file may have been moved or deleted")
        return 1
    except OSError as e:
        logger.error("OS error: %s", e)
        return 1
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
