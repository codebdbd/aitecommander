import pytest
from app.models.db import Database


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_conn_self_heal.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    db.initialize_or_migrate()
    return db


def test_connection_reopens_after_close(fresh_db: Database):
    db = fresh_db

    # Убеждаемся, что соединение открыто и работает
    _ = db.spheres.get_spheres()

    # Закрываем соединение вручную через API БД
    db.close()

    # Следующий вызов должен самовосстановить соединение и не упасть
    spheres = db.spheres.get_spheres()
    assert isinstance(spheres, list)

    # Дополнительно проверим, что низкоуровневый доступ тоже работает
    row = db.connection.execute("SELECT 1").fetchone()
    assert row is not None
