from __future__ import annotations

import sqlite3
from pathlib import Path
import shutil
import uuid

import pytest

from app.utils.db.migrations import MigrationError, MigrationRunner
from tests.conftest import build_test_temp_path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _workspace_temp_dir() -> Path:
    path = build_test_temp_path("migrations", f"migrations_{uuid.uuid4().hex}")
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_real_migrations_apply_and_required_indexes_exist() -> None:
    conn = _conn()
    runner = MigrationRunner(conn, Path("app/models/migrations"))

    applied = runner.run_all_pending()
    assert applied == 7
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7

    index_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    required = {
        "idx_link_category_id",
        "idx_link_is_favorite",
        "idx_link_last_used",
        "idx_link_category_position",
        "idx_link_favorite_position",
        "idx_link_category_name_url_args",
        "idx_link_type",
        "idx_section_sphere_id",
        "idx_section_sphere_position",
        "idx_category_section_id",
        "idx_category_section_position",
    }
    assert required.issubset(index_names)

    assert runner.run_all_pending() == 0


def test_runner_failure_does_not_advance_version_and_allows_recovery() -> None:
    migrations_dir = _workspace_temp_dir()
    try:
        (migrations_dir / "0001_init.sql").write_text(
            "CREATE TABLE a (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )
        (migrations_dir / "0002_fail.sql").write_text(
            "CREATE TABLE broken (", encoding="utf-8"
        )
        (migrations_dir / "0003_after.sql").write_text(
            "CREATE TABLE b (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )

        conn = _conn()
        runner = MigrationRunner(conn, migrations_dir)

        with pytest.raises(MigrationError):
            runner.run_all_pending()

        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='a'"
        ).fetchone()
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='b'"
            ).fetchone()
            is None
        )

        (migrations_dir / "0002_fail.sql").write_text(
            "CREATE TABLE fixed (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )

        assert runner.run_all_pending() == 2
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='b'"
        ).fetchone()
    finally:
        shutil.rmtree(migrations_dir, ignore_errors=True)


def test_python_migration_without_migrate_function_fails() -> None:
    migrations_dir = _workspace_temp_dir()
    try:
        (migrations_dir / "0001_init.sql").write_text(
            "CREATE TABLE a (id INTEGER PRIMARY KEY);", encoding="utf-8"
        )
        (migrations_dir / "0002_bad.py").write_text("x = 1\n", encoding="utf-8")

        conn = _conn()
        runner = MigrationRunner(conn, migrations_dir)

        with pytest.raises(MigrationError):
            runner.run_all_pending()

        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        shutil.rmtree(migrations_dir, ignore_errors=True)
