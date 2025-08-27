from __future__ import annotations

import pytest

from app.models.db import Database
from app.services.structure_service import StructureService


@pytest.fixture(autouse=True)
def _disable_model_validation(monkeypatch):
    """Отключает модельную валидацию на время тестов, чтобы избежать
    циклических импортов внутри app.utils.validators.* и сосредоточиться
    на проверке поведения БД/моделей.
    """
    from app.models import db_base as _db_base

    def _noop(self, data, required_fields, entity_name=""):
        return None

    monkeypatch.setattr(_db_base.DatabaseBase, "_validate_required_fields", _noop)

@pytest.fixture()
def db_in_memory():
    """
    Инициализирует чистую БД в памяти и схему без обращения к реальному файлу.
    Возвращает инстанс Database с установленной схемой.
    """
    db = Database()
    # Переназначаем путь на :memory: и создаём схему вручную
    db.db_path = ":memory:"
    # Доступ к connection инициирует соединение по новому пути
    _ = db.connection
    db._init_schema()
    yield db
    try:
        db.close()
    except Exception:
        pass


@pytest.fixture()
def service(db_in_memory: Database) -> StructureService:
    return StructureService(db_in_memory)


def create_structure(db: Database, *,
                     sphere_name: str = "S",
                     section_name: str = "SEC",
                     categories: list[str] = None) -> dict:
    """
    Утилита: создаёт сферу, раздел и набор категорий (по порядку),
    возвращает их идентификаторы.
    """
    if categories is None:
        categories = ["C1", "C2", "C3"]

    # Вставляем сферу
    sphere_id = db.spheres.insert_sphere({"name": sphere_name})
    # Вставляем раздел
    section_id = db.sections.insert_section({"name": section_name, "sphere_id": sphere_id})
    # Вставляем категории (позиции назначатся автоматически 0..)
    cat_ids = []
    for name in categories:
        cat_id = db.categories.insert_category({"name": name, "section_id": section_id})
        assert isinstance(cat_id, int) and cat_id > 0
        cat_ids.append(cat_id)
    return {"sphere_id": sphere_id, "section_id": section_id, "category_ids": cat_ids}


# --- Тесты batch counting ---

def test_count_links_by_categories_basic(service: StructureService, db_in_memory: Database):
    ids = create_structure(db_in_memory, categories=["A", "B", "C", "D"])  # 4 категории
    cids = ids["category_ids"]

    # Добавим по ссылкам: A:2, B:0, C:1, D:3
    def add_link(cat_id: int, name: str, url: str):
        return db_in_memory.links.upsert_link({
            "category_id": cat_id,
            "name": name,
            "url": url,
            "type": "web",
            "notes": "",
            "is_favorite": 0,
            "icon_path": "default.ico",
            "args": "",
            "browser_key": None,
        })

    # A
    add_link(cids[0], "a1", "https://a1")
    add_link(cids[0], "a2", "https://a2")
    # C
    add_link(cids[2], "c1", "https://c1")
    # D
    add_link(cids[3], "d1", "https://d1")
    add_link(cids[3], "d2", "https://d2")
    add_link(cids[3], "d3", "https://d3")

    result = service.count_links_by_categories(cids)
    # Проверяем точные значения
    assert result.get(cids[0], 0) == 2
    assert result.get(cids[1], 0) == 0
    assert result.get(cids[2], 0) == 1
    assert result.get(cids[3], 0) == 3


def test_count_links_by_categories_empty_and_invalid(service: StructureService, db_in_memory: Database):
    ids = create_structure(db_in_memory, categories=["X", "Y"])  # 2 категории
    cids = ids["category_ids"]

    # Пустой ввод
    assert service.count_links_by_categories([]) == {}

    # Ввод с невалидными значениями и несуществующими id: должны игнорироваться и не падать
    bogus_ids = [None, "1", -5, 0, 999999]
    res = service.count_links_by_categories(bogus_ids)  # type: ignore[arg-type]
    # Метод должен вернуть словарь только для реальных id, в данном кейсе пустой
    assert isinstance(res, dict)
    assert res == {}

    # Смешанный ввод: валидные + заведомо несуществующие
    mixed = [cids[0], 777777, cids[1]]
    res2 = service.count_links_by_categories(mixed)
    # Для существующих категорий пока 0 ссылок
    assert res2.get(cids[0], 0) == 0
    assert res2.get(cids[1], 0) == 0


# --- Тесты переиндексации после пакетного удаления категорий ---

def test_delete_categories_bulk_reindexes_positions(db_in_memory: Database):
    ids = create_structure(db_in_memory, categories=["C1", "C2", "C3", "C4", "C5"])  # 5 категорий
    section_id = ids["section_id"]
    cids = ids["category_ids"]

    # Убедимся, что позиции изначально 0..4
    rows = db_in_memory.categories.get_categories(section_id)
    assert [r["position"] for r in rows] == list(range(0, 5))

    # Удаляем C2 и C4 (по id из массива)
    to_delete = [cids[1], cids[3]]
    deleted = db_in_memory.categories.delete_categories_bulk(to_delete)
    assert deleted == 2

    # Проверяем, что остались 3 категории и позиции стали 0..2 без дырок
    rows_after = db_in_memory.categories.get_categories(section_id)
    assert len(rows_after) == 3
    assert [r["position"] for r in rows_after] == [0, 1, 2]

    # Порядок должен соответствовать исходному порядку минус удалённые
    remaining_expected = [cids[0], cids[2], cids[4]]
    assert [r["id"] for r in rows_after] == remaining_expected


def test_delete_categories_bulk_handles_duplicates_and_invalid_ids(db_in_memory: Database):
    ids = create_structure(db_in_memory, categories=["A", "B", "C"])  # 3 категории
    section_id = ids["section_id"]
    cids = ids["category_ids"]

    # Дубли и невалидные значения должны игнорироваться, не ломая транзакцию
    to_delete = [cids[0], cids[0], None, 0, -1, "x", cids[2]]  # type: ignore[list-item]
    deleted = db_in_memory.categories.delete_categories_bulk(to_delete)  # type: ignore[arg-type]
    assert deleted == 2

    rows_after = db_in_memory.categories.get_categories(section_id)
    # Осталась одна категория — должна иметь позицию 0
    assert len(rows_after) == 1
    assert rows_after[0]["id"] == cids[1]
    assert rows_after[0]["position"] == 0
