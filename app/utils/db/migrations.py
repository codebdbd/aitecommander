import importlib.util
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from app.utils.db.synchronization import db_lock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    kind: str  # 'sql' or 'py'


class MigrationError(Exception):
    pass


class MigrationRunner:
    """Simple migration runner for SQLite based on ``PRAGMA user_version``.

    - Searches for migration files in ``migrations_dir``.
    - Supports ``.sql`` (via ``executescript``) and ``.py`` (expects ``migrate(conn, logger)``).
    - Applies migrations sequentially, incrementing ``user_version`` after success.
    - Thread safety is provided via ``db_lock`` (single critical section per batch).
    """

    def __init__(self, connection: sqlite3.Connection, migrations_dir: Path):
        self.connection = connection
        self.migrations_dir = migrations_dir

    def get_current_version(self) -> int:
        row = self.connection.execute("PRAGMA user_version").fetchone()
        try:
            return int(list(row)[0])
        except Exception:
            return 0

    def set_version(self, version: int) -> None:
        self.connection.execute(f"PRAGMA user_version = {version}")

    def discover(self) -> List[Migration]:
        if not self.migrations_dir.exists():
            return []
        migrations: List[Migration] = []
        for entry in sorted(self.migrations_dir.iterdir()):
            if not entry.is_file():
                continue
            name = entry.name
            if not name[:4].isdigit() or not name[4:5] == "_":
                continue
            try:
                version = int(name[:4])
            except ValueError:
                continue
            if entry.suffix.lower() == ".sql":
                kind = "sql"
            elif entry.suffix.lower() == ".py":
                kind = "py"
            else:
                continue
            migrations.append(Migration(version=version, name=name, path=entry, kind=kind))
     
        migrations.sort(key=lambda m: (m.version, m.name))
        return migrations

    def run_all_pending(self) -> int:
        """Apply all pending migrations starting from ``user_version + 1``.

        Returns the number of applied migrations.
        """
        with db_lock:
            applied = 0
            current = self.get_current_version()
            all_migs = self.discover()
            for mig in all_migs:
                if mig.version <= current:
                    continue
                logger.info("Migration v%04d: %s", mig.version, mig.name)
                self._apply_one(mig)
                self.set_version(mig.version)
                self.connection.commit()
                applied += 1
                current = mig.version
                logger.info("Migration v%04d applied", mig.version)
            return applied

    def _apply_one(self, mig: Migration) -> None:
        if mig.kind == "sql":
            sql = mig.path.read_text(encoding="utf-8")
            self.connection.executescript(sql)
        elif mig.kind == "py":
            self._run_python_migration(mig.path)
        else:
            raise MigrationError(f"Unknown migration type: {mig.kind}")

    def _run_python_migration(self, path: Path) -> None:
        spec = importlib.util.spec_from_file_location(path.stem, str(path))
        if spec is None or spec.loader is None:
            raise MigrationError(f"Failed to load migration: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore
        migrate_func: Optional[Callable] = getattr(module, "migrate", None)
        if not callable(migrate_func):
            raise MigrationError(
                f"Python migration {path.name} does not define migrate(conn, logger)"
            )
        migrate_func(self.connection, logger)
