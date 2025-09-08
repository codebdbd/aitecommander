from __future__ import annotations

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


def _create_full_tree(db: Database, spheres: int = 2, sections_per_sphere: int = 2, categories_per_section: int = 3, links_per_category: int = 4):
    sphere_ids = []
    for si in range(spheres):
        sid = db.spheres.insert_sphere({"name": f"S{si}"})
        sphere_ids.append(sid)
        for seci in range(sections_per_sphere):
            secid = db.sections.insert_section({"name": f"SEC{si}-{seci}", "sphere_id": sid})
            for ci in range(categories_per_section):
                catid = db.categories.insert_category({"name": f"CAT{si}-{seci}-{ci}", "section_id": secid})
                for li in range(links_per_category):
                    db.links.upsert_link({
                        "category_id": catid,
                        "name": f"L{si}-{seci}-{ci}-{li}",
                        "url": f"https://ex/{si}/{seci}/{ci}/{li}",
                        "type": "web",
                        "notes": "",
                        "is_favorite": 0,
                        "icon_path": "default.ico",
                        "args": "",
                        "browser_key": None,
                    })
    db.connection.commit()
    return sphere_ids


def test_export_full_structure_bulk_builds_correct_hierarchy_and_order(db_in_memory: Database):
    _create_full_tree(db_in_memory, spheres=2, sections_per_sphere=2, categories_per_section=3, links_per_category=4)

    exported = db_in_memory.export_full_structure()
    assert isinstance(exported, dict)
    spheres = exported.get("spheres")
    assert isinstance(spheres, list)

    # Проверка числа элементов и порядка по position для каждого уровня
    assert len(spheres) == 2
    assert [s["position"] for s in spheres] == [0, 1]

    for s_idx, s in enumerate(spheres):
        assert "sections" in s
        sections = s["sections"]
        assert len(sections) == 2
        assert [sec["position"] for sec in sections] == [0, 1]
        assert all(sec["sphere_id"] == s["id"] for sec in sections)

        for sec_idx, sec in enumerate(sections):
            assert "categories" in sec
            cats = sec["categories"]
            assert len(cats) == 3
            assert [c["position"] for c in cats] == [0, 1, 2]
            assert all(c["section_id"] == sec["id"] for c in cats)

            for c_idx, cat in enumerate(cats):
                assert "links" in cat
                links = cat["links"]
                assert len(links) == 4
                assert [link["position"] for link in links] == [0, 1, 2, 3]
                assert all(link["category_id"] == cat["id"] for link in links)


def test_export_full_structure_empty(db_in_memory: Database):
    exported = db_in_memory.export_full_structure()
    assert exported == {"spheres": []}
