import sqlite3

import pytest

from app.models.category_model import CategoryModel
from app.models.db_base import DatabaseError
from app.models.section_model import SectionModel
from app.models.sphere_model import SphereModel


class _DummyMgr:
    connection = None


class FailingSphereModel(SphereModel):
    def __init__(self):
        super().__init__(_DummyMgr())

    def _execute_with_error_handling(self, query: str, params: tuple = (), fetch_method: str = None):  # type: ignore[override]
        # Любой SQL вызов в этом тестовом классе падает как будто от драйвера
        raise sqlite3.Error("simulated failure for sphere")


def test_insert_sphere_propagates_database_error_on_position_failure():
    m = FailingSphereModel()
    with pytest.raises(DatabaseError):
        m.insert_sphere({"name": "Test"})


class FailingSectionModel(SectionModel):
    def __init__(self):
        super().__init__(_DummyMgr())

    def _execute_with_error_handling(self, query: str, params: tuple = (), fetch_method: str = None):  # type: ignore[override]
        raise sqlite3.Error("simulated failure for section")


def test_insert_section_propagates_database_error_on_position_failure():
    m = FailingSectionModel()
    with pytest.raises(DatabaseError):
        m.insert_section({"name": "S", "sphere_id": 1})


class FailingCategoryModel(CategoryModel):
    def __init__(self):
        super().__init__(_DummyMgr())

    def _execute_with_error_handling(self, query: str, params: tuple = (), fetch_method: str = None):  # type: ignore[override]
        # Разрешаем первичную проверку на дубликаты имени категории вернуться как "не найдено",
        # чтобы код дошёл до вычисления позиции, где и должна произойти ошибка.
        if "SELECT id FROM category" in query:
            return None  # нет дубликатов
        # Эмулируем сбой ТОЛЬКО при вычислении позиции
        if "MAX(position)" in query:
            raise sqlite3.Error("simulated failure for category position")
        # Безопасный дефолт для любых других вызовов, если появятся
        return None


def test_insert_category_propagates_database_error_on_position_failure():
    m = FailingCategoryModel()
    with pytest.raises(DatabaseError):
        m.insert_category({"name": "C", "section_id": 1})
