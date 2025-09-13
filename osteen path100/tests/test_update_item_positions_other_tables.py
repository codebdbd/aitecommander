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


def test_update_item_positions_sphere(db_in_memory: Database):
    # Создаём 5 сфер
    sids = [db_in_memory.spheres.insert_sphere({"name": f"S{i}"}) for i in range(5)]
    db_in_memory.connection.commit()

    rows = db_in_memory.spheres.get_spheres()
    assert [r["position"] for r in rows] == [0, 1, 2, 3, 4]

    new_order = [sids[3], sids[1], sids[4], sids[0], sids[2]]
    db_in_memory.update_item_positions("sphere", new_order)

    rows_after = db_in_memory.spheres.get_spheres()
    assert [r["position"] for r in rows_after] == [0, 1, 2, 3, 4]
    assert [r["id"] for r in rows_after] == new_order


def test_update_item_positions_section(db_in_memory: Database):
    # Сфера и 6 разделов
    sphere_id = db_in_memory.spheres.insert_sphere({"name": "S"})
    section_ids = [
        db_in_memory.sections.insert_section(
            {"name": f"SEC{i}", "sphere_id": sphere_id}
        )
        for i in range(6)
    ]
    db_in_memory.connection.commit()

    rows = db_in_memory.sections.get_sections(sphere_id)
    assert [r["position"] for r in rows] == list(range(6))

    new_order = [section_ids[i] for i in [5, 0, 2, 3, 4, 1]]
    db_in_memory.update_item_positions("section", new_order)

    rows_after = db_in_memory.sections.get_sections(sphere_id)
    assert [r["position"] for r in rows_after] == list(range(6))
    assert [r["id"] for r in rows_after] == new_order


essential_link_fields = {
    "type": "web",
    "notes": "",
    "is_favorite": 0,
    "icon_path": "default.ico",
    "args": "",
    "browser_key": None,
}


def test_update_item_positions_link(db_in_memory: Database):
    # Категория с 50 ссылками
    sphere_id = db_in_memory.spheres.insert_sphere({"name": "S"})
    section_id = db_in_memory.sections.insert_section(
        {"name": "SEC", "sphere_id": sphere_id}
    )
    category_id = db_in_memory.categories.insert_category(
        {"name": "CAT", "section_id": section_id}
    )

    link_ids = []
    for i in range(50):
        lid = db_in_memory.links.upsert_link(
            {
                "category_id": category_id,
                "name": f"L{i}",
                "url": f"https://example.com/{i}",
                **essential_link_fields,
            }
        )
        link_ids.append(lid)
    db_in_memory.connection.commit()

    rows = db_in_memory.links.get_links(category_id)
    assert [r["position"] for r in rows] == list(range(50))

    new_order = list(reversed(link_ids))
    db_in_memory.update_item_positions("link", new_order)

    rows_after = db_in_memory.links.get_links(category_id)
    assert [r["position"] for r in rows_after] == list(range(50))
    assert [r["id"] for r in rows_after] == new_order
