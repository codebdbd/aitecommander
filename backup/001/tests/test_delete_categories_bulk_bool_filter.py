import pytest

from app.models.db import Database


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_categories_bool_filter.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    db.initialize_or_migrate()
    return db


def _exists_category(conn, cid: int) -> bool:
    row = conn.execute("SELECT 1 FROM category WHERE id=?", (cid,)).fetchone()
    return row is not None


def test_delete_categories_bulk_ignores_bool_ids(fresh_db: Database):
    db = fresh_db

    # Подготовим валидный section_id
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})

    # Вставим две категории
    cat1_id = db.categories.insert_category({"name": "A", "section_id": section_id})
    cat2_id = db.categories.insert_category({"name": "B", "section_id": section_id})
    assert isinstance(cat1_id, int) and isinstance(cat2_id, int)

    # Удаляем, передав список с булевым значением и валидным ID
    deleted = db.categories.delete_categories_bulk([True, cat1_id])

    # Должна удалиться только одна запись (cat1_id); True должен быть проигнорирован
    assert deleted == 1
    assert _exists_category(db.connection, cat1_id) is False
    assert _exists_category(db.connection, cat2_id) is True


def test_delete_categories_bulk_only_invalid_bool_and_nonpositive(fresh_db: Database):
    db = fresh_db

    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})

    # Просто создадим одну категорию, чтобы таблица не была пустой
    _ = db.categories.insert_category({"name": "A", "section_id": section_id})

    # Передаем только невалидные значения: булевы и неположительные
    deleted = db.categories.delete_categories_bulk([False, True, 0, -5])
    assert deleted == 0
