import pytest

from app.models.db import Database


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_link_search_order.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    db.initialize_or_migrate()
    return db


def _names(rows):
    return [r["name"] for r in rows]


def test_search_links_orders_case_insensitive(fresh_db: Database):
    db = fresh_db

    # Создаем структуру: сфера -> раздел -> категория
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})
    category_id = db.categories.insert_category({"name": "CAT", "section_id": section_id})

    # Вставляем ссылки в произвольном порядке и с разным регистром
    db.links.upsert_link({
        "category_id": category_id,
        "name": "Banana",
        "url": "http://b",
        "type": "web",
        "notes": "",
        "args": "",
        "is_favorite": 0,
    })
    db.links.upsert_link({
        "category_id": category_id,
        "name": "apple",
        "url": "http://a",
        "type": "web",
        "notes": "",
        "args": "",
        "is_favorite": 0,
    })

    # Поиск по подстроке 'a' должен вернуть apple перед Banana при сортировке без учета регистра
    rows = db.links.search_links("a")
    assert _names(rows)[:2] == ["apple", "Banana"]
