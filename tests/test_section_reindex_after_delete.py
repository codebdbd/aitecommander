import pytest

from app.models.db import Database


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_sections_reindex.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    db.initialize_or_migrate()
    return db


def _sections(conn, sphere_id: int):
    rows = conn.execute(
        "SELECT id, name, position FROM section WHERE sphere_id=? ORDER BY position, id",
        (sphere_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def test_delete_section_triggers_reindex_positions(fresh_db: Database):
    db = fresh_db

    # Создаём сферу и 3 раздела внутри неё
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    s1 = db.sections.insert_section({"name": "A", "sphere_id": sphere_id})  # pos 0
    s2 = db.sections.insert_section({"name": "B", "sphere_id": sphere_id})  # pos 1
    s3 = db.sections.insert_section({"name": "C", "sphere_id": sphere_id})  # pos 2

    rows = _sections(db.connection, sphere_id)
    assert [r["position"] for r in rows] == [0, 1, 2]

    # Удаляем средний раздел (позиция 1)
    db.sections.delete_section(s2)

    rows2 = _sections(db.connection, sphere_id)
    # Должны остаться 2 раздела с позициями 0 и 1 без «дыр»
    assert [r["position"] for r in rows2] == [0, 1]
    # Сохранились A и C в порядке позиций
    assert [r["name"] for r in rows2] == ["A", "C"]
