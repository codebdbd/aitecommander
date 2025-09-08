import pytest

from app.models.db import Database
from app.models.db_base import ValidationError


@pytest.fixture()
def db_in_memory():
    """
    Инициализирует чистую in-memory БД и схему без доступа к файловой системе.
    Возвращает инстанс Database с установленной схемой.
    """
    db = Database()
    db.db_path = ":memory:"
    # Инициируем соединение по новому пути и создаём схему
    _ = db.connection
    db._init_schema()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


def _create_section_with_categories(db: Database, n: int):
    """
    Создаёт сферу, раздел и n категорий в этом разделе. Возвращает кортеж
    (sphere_id, section_id, category_ids:list[int]).
    """
    sphere_id = db.spheres.insert_sphere({"name": "S"})
    section_id = db.sections.insert_section({"name": "SEC", "sphere_id": sphere_id})
    cat_ids = []
    for i in range(n):
        cid = db.categories.insert_category({"name": f"C{i}", "section_id": section_id})
        cat_ids.append(cid)
    db.connection.commit()
    return sphere_id, section_id, cat_ids


def test_update_item_positions_small_ordering(db_in_memory: Database):
    _, section_id, cat_ids = _create_section_with_categories(db_in_memory, 5)
    # Проверим исходный порядок позиций 0..4
    rows = db_in_memory.categories.get_categories(section_id)
    assert [r["position"] for r in rows] == list(range(5))

    # Новый порядок (перестановка)
    new_order = [cat_ids[4], cat_ids[0], cat_ids[2], cat_ids[3], cat_ids[1]]
    db_in_memory.update_item_positions("category", new_order)

    rows_after = db_in_memory.categories.get_categories(section_id)
    # Позиции должны стать 0..4
    assert [r["position"] for r in rows_after] == list(range(5))
    # И порядок id по position должен совпасть с new_order
    assert [r["id"] for r in rows_after] == new_order


def test_update_item_positions_large_chunking_1200(db_in_memory: Database):
    # Большой набор для проверки чанкинга параметров и пакетного обновления
    _, section_id, cat_ids = _create_section_with_categories(db_in_memory, 1200)

    # Новый порядок — реверс, чтобы легко проверять
    new_order = list(reversed(cat_ids))
    db_in_memory.update_item_positions("category", new_order)

    rows_after = db_in_memory.categories.get_categories(section_id)
    assert len(rows_after) == 1200
    # Проверяем ids по возрастанию position
    assert [r["id"] for r in rows_after] == new_order
    # И позиции монотонные от 0 до 1199
    assert [r["position"] for r in rows_after] == list(range(1200))


def test_update_item_positions_validation_errors(db_in_memory: Database):
    _, section_id, cat_ids = _create_section_with_categories(db_in_memory, 3)

    # Дубликаты в списке id
    with pytest.raises(ValidationError):
        db_in_memory.update_item_positions("category", [cat_ids[0], cat_ids[0], cat_ids[2]])

    # Несуществующий id
    bogus = max(cat_ids) + 9999
    with pytest.raises(ValidationError):
        db_in_memory.update_item_positions("category", [cat_ids[0], bogus, cat_ids[2]])

    # Некорректный тип id
    with pytest.raises(ValidationError):
        db_in_memory.update_item_positions("category", [cat_ids[0], "x", cat_ids[2]])  # type: ignore[list-item]
