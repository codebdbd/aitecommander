import pytest

from app.models.db import Database


@pytest.fixture()
def db_in_memory():
    db = Database()
    db.db_path = ":memory:"
    _ = db.connection
    db._init_schema()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


def _create_many_categories(db: Database, n: int):
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})
    # Вставляем поштучно, чтобы избежать вложенных транзакций внутри теста
    for i in range(n):
        db.categories.insert_category({"name": f"C{i}", "section_id": section_id})
    db.connection.commit()
    # Достанем ids в порядке позиции
    rows = db.categories.get_categories(section_id)
    ids = [r["id"] for r in rows]
    assert len(ids) == n
    return section_id, ids


def test_delete_categories_bulk_handles_more_than_sqlite_params_limit(db_in_memory: Database):
    # создадим 1200 категорий (больше лимита 999)
    section_id, ids = _create_many_categories(db_in_memory, 1200)

    # удаляем все одним вызовом — метод должен разбить на чанки и успешно завершить
    deleted = db_in_memory.categories.delete_categories_bulk(ids)
    assert deleted == 1200

    # категории секции должны быть пусты и без ошибок
    rows_after = db_in_memory.categories.get_categories(section_id)
    assert rows_after == []

    # повторный вызов на уже удалённые id безопасен
    deleted2 = db_in_memory.categories.delete_categories_bulk(ids)
    assert deleted2 == 0
