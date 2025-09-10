import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.models.db import Database


def _legacy_schema_sql():
    return (
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS sphere (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL UNIQUE,
            position   INTEGER NOT NULL DEFAULT 0,
            icon_path  TEXT    DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS section (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sphere_id  INTEGER NOT NULL REFERENCES sphere(id) ON DELETE CASCADE,
            name       TEXT    NOT NULL,
            icon_path  TEXT    DEFAULT '',
            position   INTEGER NOT NULL DEFAULT 0,
            UNIQUE(sphere_id, name)
        );
        CREATE TABLE IF NOT EXISTS category (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL REFERENCES section(id) ON DELETE CASCADE,
            name       TEXT    NOT NULL,
            icon_path  TEXT    DEFAULT '',
            position   INTEGER NOT NULL DEFAULT 0,
            UNIQUE(section_id, name)
        );
        CREATE TABLE IF NOT EXISTS link (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id  INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
            name         TEXT    NOT NULL,
            url          TEXT    NOT NULL,
            type         TEXT    NOT NULL CHECK(type IN ('web','file','program','script','chromeapp','folder')),
            notes        TEXT    DEFAULT '',
            is_favorite  INTEGER NOT NULL CHECK(is_favorite IN (0,1)) DEFAULT 0,
            last_used    TEXT    DEFAULT NULL,
            icon_path    TEXT    NOT NULL DEFAULT 'default.ico',
            args         TEXT    DEFAULT '',
            position     INTEGER NOT NULL DEFAULT 0,
            UNIQUE(category_id, url, args, type)
        );
        """
    )


@pytest.fixture()
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_migrations.sqlite"


def test_fresh_database_migrates_to_latest(temp_db_path: Path):
    # БД не существует — создадим через Database.initialize_or_migrate()
    assert not temp_db_path.exists()
    with Database() as db:
        db.db_path = str(temp_db_path)
        db.initialize_or_migrate()

        # Проверка версии схемы
        row = db.connection.execute("PRAGMA user_version").fetchone()
        ver = int(list(row)[0])
        assert ver >= 4  # до 0004

        # Проверка наличия колонок в link
        cols = db.connection.execute("PRAGMA table_info('link')").fetchall()
        names = {str(dict(r)["name"]) for r in cols}
        assert "browser_key" in names

        # Проверка NOCASE индексов (могут отсутствовать, если есть дубликаты; в свежей БД — должны быть)
        idx_rows = db.connection.execute("PRAGMA index_list('sphere')").fetchall()
        idx_names = {str(dict(r)["name"]) for r in idx_rows}
        assert "idx_sphere_name_nocase" in idx_names


def test_legacy_database_upgrades_and_preserves_data(temp_db_path: Path):
    # Создаём legacy-схему вручную
    with sqlite3.connect(str(temp_db_path)) as conn:
        conn.executescript(_legacy_schema_sql())
        # Секция/категория для ссылки
        conn.execute("INSERT INTO sphere(name, position) VALUES(?, ?)", ("S", 0))
        conn.execute(
            "INSERT INTO section(name, sphere_id, position) VALUES(?, ?, ?)",
            ("Sec", 1, 0),
        )
        conn.execute(
            "INSERT INTO category(name, section_id, position) VALUES(?, ?, ?)",
            ("Cat", 1, 0),
        )
        conn.execute(
            "INSERT INTO link(category_id, name, url, type, args, position) VALUES(?, ?, ?, ?, ?, ?)",
            (1, "L", "http://x", "web", "", 0),
        )
        conn.commit()

    # Прогон инициализации/миграций
    with Database() as db:
        db.db_path = str(temp_db_path)
        db.initialize_or_migrate()

        # Данные сохранились
        row = db.connection.execute("SELECT COUNT(*) FROM link").fetchone()
        assert int(list(row)[0]) == 1

        # Новая колонка появилась
        cols = db.connection.execute("PRAGMA table_info('link')").fetchall()
        names = {str(dict(r)["name"]) for r in cols}
        assert "browser_key" in names

        # Уникальность теперь по (category_id, name, url, args)
        # Проверим, что дубль по старому набору полей с другим type не вставится, если name совпадает
        with pytest.raises(sqlite3.IntegrityError):
            db.connection.execute(
                "INSERT INTO link(category_id, name, url, type, args, position) VALUES(?, ?, ?, ?, ?, ?)",
                (1, "L", "http://x", "program", "", 1),
            )

        # Версия поднялась
        vrow = db.connection.execute("PRAGMA user_version").fetchone()
        assert int(list(vrow)[0]) >= 4
