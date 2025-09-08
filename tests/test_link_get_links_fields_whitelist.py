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


def _seed_one_link(db: Database):
    sph = db.spheres.insert_sphere({"name": "S"})
    sec = db.sections.insert_section({"name": "SEC", "sphere_id": sph})
    cat = db.categories.insert_category({"name": "CAT", "section_id": sec})
    lid = db.links.upsert_link({
        "category_id": cat,
        "name": "L1",
        "url": "https://ex/1",
        "type": "web",
        "notes": "",
        "is_favorite": 0,
        "icon_path": "default.ico",
        "args": "",
        "browser_key": None,
    })
    db.connection.commit()
    return cat, lid


def test_get_links_fields_whitelist_filters_invalid_and_logs(db_in_memory: Database, caplog):
    cat_id, _ = _seed_one_link(db_in_memory)

    with caplog.at_level("WARNING"):
        rows = db_in_memory.links.get_links(cat_id, fields=[
            "id", "category_id", "name", "position", "__bad__", "url; DROP TABLE link; --"
        ])

    # Должна появиться запись об игнорировании недопустимых полей
    assert any("игнорированы недопустимые поля" in rec.message for rec in caplog.records)

    # Выборка успешна и возвращает только допустимые поля
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]
    # Поля из белого списка присутствуют
    for fld in ("id", "category_id", "name", "position"):
        assert fld in row
    # Недопустимые поля не попали в результат
    assert "__bad__" not in row
    assert "url; DROP TABLE link; --" not in row


def test_get_links_empty_fields_fallbacks_to_default(db_in_memory: Database):
    cat_id, _ = _seed_one_link(db_in_memory)
    # Все поля невалидные -> должен сработать откат к дефолтному набору
    rows = db_in_memory.links.get_links(cat_id, fields=["__x__", "__y__"], all_fields=False)
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]
    # Должны присутствовать дефолтные поля (подмножество)
    for fld in ("id", "category_id", "name", "url", "position"):
        assert fld in row
