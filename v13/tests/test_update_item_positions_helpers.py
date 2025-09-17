import pytest

from app.models.db import Database, ValidationError


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_update_positions_helpers.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    db.initialize_or_migrate()
    return db


# --- Tests for _validate_ids ---

def test_validate_ids_empty_returns_empty(fresh_db: Database):
    db = fresh_db
    assert db._validate_ids([]) == []


def test_validate_ids_rejects_invalid_types_and_values(fresh_db: Database):
    db = fresh_db
    with pytest.raises(ValidationError):
        db._validate_ids([1, -2])  # negative
    with pytest.raises(ValidationError):
        db._validate_ids([1, True])  # bool is invalid
    with pytest.raises(ValidationError):
        db._validate_ids([1, "2"])  # non-int


def test_validate_ids_rejects_duplicates(fresh_db: Database):
    db = fresh_db
    with pytest.raises(ValidationError):
        db._validate_ids([1, 2, 2])


def test_validate_ids_valid_list_passes(fresh_db: Database):
    db = fresh_db
    assert db._validate_ids([0, 1, 2]) == [0, 1, 2]


# --- Tests for _ensure_ids_exist ---

def test_ensure_ids_exist_ok_and_missing_detected(fresh_db: Database):
    db = fresh_db

    # Подготовим несколько сфер (простая таблица для проверки существования)
    s1 = db.spheres.insert_sphere({"name": "S1"})
    s2 = db.spheres.insert_sphere({"name": "S2"})

    # Не должно бросать для существующих id
    db._ensure_ids_exist("sphere", [s1, s2])

    # Должно бросить для отсутствующих id
    with pytest.raises(ValidationError):
        db._ensure_ids_exist("sphere", [s1, 999_999])
