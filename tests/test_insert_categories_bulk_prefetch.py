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


def _seed_sections_and_categories(db: Database):
    """Создаёт 2 раздела в одной сфере и по 2 категории в первый раздел, 1 в второй.
    Возвращает (sphere_id, section_ids[list], existing_by_section: dict[int, list[str]]).
    """
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    sec1 = db.sections.insert_section({"name": "SEC-1", "sphere_id": sphere_id})
    sec2 = db.sections.insert_section({"name": "SEC-2", "sphere_id": sphere_id})

    # В sec1 уже есть A, B
    db.categories.insert_category({"name": "A", "section_id": sec1})
    db.categories.insert_category({"name": "B", "section_id": sec1})
    # В sec2 уже есть X
    db.categories.insert_category({"name": "X", "section_id": sec2})
    db.connection.commit()

    return sphere_id, [sec1, sec2], {sec1: ["A", "B"], sec2: ["X"]}


def test_insert_categories_bulk_prefetches_names_once_and_inserts_correctly(db_in_memory: Database, monkeypatch):
    _, (sec1, sec2), _ = _seed_sections_and_categories(db_in_memory)

    # Мониторим вызовы _execute_with_error_handling
    calls = []
    original = db_in_memory.categories._execute_with_error_handling

    def spy(query, params=None, fetch_method=None):
        calls.append((query, tuple(params or []), fetch_method))
        return original(query, params, fetch_method)

    monkeypatch.setattr(db_in_memory.categories, "_execute_with_error_handling", spy)

    # Пакет: часть имён новые, часть дубли БД, часть дубли внутри пакета
    items = [
        {"name": "A", "section_id": sec1},   # дубль БД (sec1)
        {"name": "C", "section_id": sec1},   # новый (sec1)
        {"name": "C", "section_id": sec1},   # дубль в пакете (sec1)
        {"name": "X", "section_id": sec2},   # дубль БД (sec2)
        {"name": "Y", "section_id": sec2},   # новый (sec2)
    ]

    result = db_in_memory.categories.insert_categories_bulk(items)

    # Проверяем, что категории добавились корректно: по section_id и position
    # Для sec1 было: A(0), B(1) -> добавился C(2)
    rows_sec1 = db_in_memory.categories.get_categories(sec1)
    assert [r["name"] for r in rows_sec1] == ["A", "B", "C"]
    assert [r["position"] for r in rows_sec1] == [0, 1, 2]

    # Для sec2 было: X(0) -> добавился Y(1)
    rows_sec2 = db_in_memory.categories.get_categories(sec2)
    assert [r["name"] for r in rows_sec2] == ["X", "Y"]
    assert [r["position"] for r in rows_sec2] == [0, 1]

    # Возвращаемый результат включает все уникальные пары из входа по (section_id, name)
    # (как новые, так и существующие в БД) и отсортирован по section_id, position
    assert isinstance(result, list)
    assert [ (r["section_id"], r["name"]) for r in result ] == [
        (sec1, "A"), (sec1, "C"),
        (sec2, "X"), (sec2, "Y"),
    ]

    # Убедимся, что предзагрузка имён была одним запросом по IN (...)
    select_name_in_calls = [q for (q, p, fm) in calls if isinstance(q, str) and "SELECT section_id, LOWER(name) AS lname FROM category" in q]
    assert len(select_name_in_calls) == 1

    # И отсутствуют старые per-section запросы WHERE section_id = ? на имена
    per_section_calls = [q for (q, p, fm) in calls if isinstance(q, str) and "SELECT LOWER(name) AS name FROM category WHERE section_id = ?" in q]
    assert len(per_section_calls) == 0


def test_insert_categories_bulk_empty_input_returns_empty_and_no_selects(db_in_memory: Database, monkeypatch):
    calls = []
    original = db_in_memory.categories._execute_with_error_handling

    def spy(query, params=None, fetch_method=None):
        calls.append((query, tuple(params or []), fetch_method))
        return original(query, params, fetch_method)

    monkeypatch.setattr(db_in_memory.categories, "_execute_with_error_handling", spy)

    result = db_in_memory.categories.insert_categories_bulk([])
    assert result == []
    # Никаких SELECT по именам не должно быть
    name_select_calls = [q for (q, p, fm) in calls if isinstance(q, str) and ("LOWER(name)" in q or " FROM category " in q)]
    # В пустом случае _execute_with_error_handling вообще не должен вызываться
    assert len(name_select_calls) == 0
    assert len(calls) == 0
