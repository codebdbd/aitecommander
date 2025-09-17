import copy
import sqlite3
import pytest

from app.models.db import Database


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_categories_case.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    # Инициализация схемы через миграции на временной БД
    db.initialize_or_migrate()
    return db


def _get_categories_raw(conn):
    rows = conn.execute("SELECT id, name, section_id FROM category ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def test_insert_category_case_insensitive_duplicate(fresh_db: Database):
    db = fresh_db

    # Подготовим одну сферу/раздел, чтобы был валидный section_id
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})

    # 1) Первая вставка
    first_id = db.categories.insert_category({"name": "Work", "section_id": section_id})
    assert isinstance(first_id, int)

    # 2) Попытка вставить дубликат, отличающийся только регистром
    dup_id = db.categories.insert_category({"name": "work", "section_id": section_id})
    assert dup_id is None, "Вставка дубликата в другом регистре должна возвращать None"

    # 3) Попытка со строками с пробелами
    dup_id2 = db.categories.insert_category({"name": "  WORK  ", "section_id": section_id})
    assert dup_id2 is None, "Вставка дубликата с пробелами должна возвращать None"

    rows = _get_categories_raw(db.connection)
    assert len(rows) == 1
    assert rows[0]["name"] == "Work"


def test_has_duplicate_category_case_insensitive(fresh_db: Database):
    db = fresh_db

    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})

    cat_id = db.categories.insert_category({"name": "Work", "section_id": section_id})
    assert isinstance(cat_id, int)

    # Разные варианты регистра и пробелы
    assert db.categories.has_duplicate_category(section_id, "work") is True
    assert db.categories.has_duplicate_category(section_id, " WORK ") is True
    assert db.categories.has_duplicate_category(section_id, "WORK") is True

    # С исключением по id дубликата не должно находиться
    assert db.categories.has_duplicate_category(section_id, "work", exclude_id=cat_id) is False
