import pytest

from app.models.db import Database


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_categories_move_bool_filter.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    db.initialize_or_migrate()
    return db


def _cat_section(conn, cid: int) -> int | None:
    row = conn.execute("SELECT section_id FROM category WHERE id=?", (cid,)).fetchone()
    return None if row is None else row[0]


def test_move_categories_bulk_ignores_bool_ids(fresh_db: Database):
    db = fresh_db

    # Подготовим две секции
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    sec1 = db.sections.insert_section({"name": "SEC1", "sphere_id": sphere_id})
    sec2 = db.sections.insert_section({"name": "SEC2", "sphere_id": sphere_id})

    # Вставим две категории в sec1
    cat1 = db.categories.insert_category({"name": "A", "section_id": sec1})
    cat2 = db.categories.insert_category({"name": "B", "section_id": sec1})

    # Попробуем перенести [True, cat2] в sec2 — переносится только cat2
    moved = db.categories.move_categories_to_section_bulk([True, cat2], sec2)
    assert moved == [cat2]

    # Проверим, что cat1 остался в sec1, а cat2 переехал в sec2
    assert _cat_section(db.connection, cat1) == sec1
    assert _cat_section(db.connection, cat2) == sec2
