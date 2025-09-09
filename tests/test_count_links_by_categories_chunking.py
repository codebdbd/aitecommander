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


def _create_many_categories_with_one_link_each(db: Database, n: int):
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})
    # Поштучная вставка исключает вложенные транзакции
    for i in range(n):
        db.categories.insert_category({"name": f"C{i}", "section_id": section_id})
    # Достанем ids в порядке позиции
    cats = db.categories.get_categories(section_id)
    cat_ids = [c["id"] for c in cats]
    # Добавим по одной ссылке в каждую категорию
    for cid in cat_ids:
        db.links.upsert_link(
            {
                "category_id": cid,
                "name": f"L{cid}",
                "url": f"https://ex/{cid}",
                "type": "web",
                "notes": "",
                "is_favorite": 0,
                "icon_path": "default.ico",
                "args": "",
                "browser_key": None,
            }
        )
    db.connection.commit()
    return cat_ids


def test_count_links_by_categories_handles_more_than_sqlite_params_limit(
    db_in_memory: Database,
):
    # Создаём 1100 категорий (больше стандартного лимита 999 параметров)
    cat_ids = _create_many_categories_with_one_link_each(db_in_memory, 1100)

    counts = db_in_memory.links.count_links_by_categories(cat_ids)

    # Должны получить по 1 для каждой категории
    assert len(counts) == 1100
    assert all(counts.get(cid, 0) == 1 for cid in cat_ids)


def test_count_links_by_categories_empty_and_invalid(db_in_memory: Database):
    assert db_in_memory.links.count_links_by_categories([]) == {}
    # Невалидные и отрицательные игнорируются
    assert db_in_memory.links.count_links_by_categories([None, -1, 0, "x"]) == {}  # type: ignore[list-item]
