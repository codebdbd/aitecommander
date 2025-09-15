import importlib.util
import importlib.abc
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
    """Простой раннер миграций для SQLite на базе PRAGMA user_version.

    - Ищет файлы миграций в каталоге migrations_dir.
    - Поддерживает .sql (executescript) и .py (функция migrate(conn, logger)).
    - Применяет последовательно, повышая user_version после успешной миграции.
    - Потокобезопасность обеспечивается через db_lock (одна большая секция на миграции).
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
        # сортировка по version, а затем по имени (стабильность)
        migrations.sort(key=lambda m: (m.version, m.name))
        return migrations

    def run_all_pending(self) -> int:
        """Применяет все миграции с версии (user_version + 1) по последнюю.

        Возвращает количество фактически применённых миграций.
        """
        with db_lock:
            applied = 0
            current = self.get_current_version()
            all_migs = self.discover()
            for mig in all_migs:
                if mig.version <= current:
                    continue
                logger.info("Миграция v%04d: %s", mig.version, mig.name)
                self._apply_one(mig)
                self.set_version(mig.version)
                self.connection.commit()
                applied += 1
                current = mig.version
                logger.info("Миграция v%04d применена", mig.version)
            return applied

    def _apply_one(self, mig: Migration) -> None:
        if mig.kind == "sql":
            sql = mig.path.read_text(encoding="utf-8")
            self.connection.executescript(sql)
        elif mig.kind == "py":
            self._run_python_migration(mig.path)
        else:
            raise MigrationError(f"Неизвестный тип миграции: {mig.kind}")

    def _run_python_migration(self, path: Path) -> None:
        spec = importlib.util.spec_from_file_location(path.stem, str(path))
        if spec is None or spec.loader is None:
            raise MigrationError(f"Не удалось загрузить миграцию: {path}")
        module = importlib.util.module_from_spec(spec)
        loader = spec.loader
        # По контракту importlib, у loader должен быть метод exec_module
        if not isinstance(loader, importlib.abc.Loader):
            raise MigrationError(f"Некорректный loader для миграции: {path}")
        loader.exec_module(module)
        migrate_func: Optional[Callable] = getattr(module, "migrate", None)
        if not callable(migrate_func):
            raise MigrationError(f"В python-миграции {path.name} отсутствует функция migrate(conn, logger)")
        migrate_func(self.connection, logger)
