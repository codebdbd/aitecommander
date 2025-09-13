import os
import sqlite3
import copy
import pytest

from app.models.db import Database, DB_PATH as ORIGINAL_DB_PATH


@pytest.fixture()
def temp_db_path(tmp_path, monkeypatch):
    db_file = tmp_path / "test_links.db"
    # Переназначаем путь к БД в модуле app.models.db
    from app.models import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    yield db_file


@pytest.fixture()
def fresh_db(temp_db_path):
    db = Database()
    # Инициализация схемы через миграции на временной БД
    db.initialize_or_migrate()
    return db


def _export_names(struct):
    spheres = struct.get("spheres", []) if isinstance(struct, dict) else (struct or [])
    names = []
    for s in spheres:
        names.append(("sphere", s.get("name")))
        for sec in s.get("sections", []):
            names.append(("section", sec.get("name")))
            for cat in sec.get("categories", []):
                names.append(("category", cat.get("name")))
                for ln in cat.get("links", []):
                    names.append(("link", ln.get("name")))
    return names


def test_get_full_structure_bulk_basic(fresh_db: Database):
    db = fresh_db
    # Готовим структуру с явными ID для детерминизма и порядка
    struct = [
        {
            "id": 1,
            "name": "S1",
            "position": 0,
            "icon_path": "",
            "sections": [
                {
                    "id": 11,
                    "name": "Sec1",
                    "sphere_id": 1,
                    "position": 0,
                    "icon_path": "",
                    "categories": [
                        {
                            "id": 111,
                            "name": "Cat1",
                            "section_id": 11,
                            "position": 0,
                            "icon_path": "",
                            "links": [
                                {
                                    "id": 1111,
                                    "category_id": 111,
                                    "name": "L1",
                                    "url": "http://a",
                                    "type": "web",
                                    "notes": "",
                                    "is_favorite": 0,
                                    "last_used": None,
                                    "icon_path": "",
                                    "args": "",
                                    "browser_key": None,
                                    "position": 0,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]

    db.import_full_structure(copy.deepcopy(struct))

    res = db.get_full_structure()
    # get_full_structure возвращает список сфер
    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0]["name"] == "S1"
    assert res[0]["sections"][0]["name"] == "Sec1"
    assert res[0]["sections"][0]["categories"][0]["name"] == "Cat1"
    assert res[0]["sections"][0]["categories"][0]["links"][0]["name"] == "L1"


def test_import_full_structure_bulk_and_fallback(fresh_db: Database):
    db = fresh_db

    # 1) BULK: у всех заданы валидные id и связи
    bulk_struct = [
        {
            "id": 2,
            "name": "SB",
            "position": 0,
            "icon_path": "",
            "sections": [
                {
                    "id": 21,
                    "name": "SecB",
                    "sphere_id": 2,
                    "position": 0,
                    "icon_path": "",
                    "categories": [
                        {
                            "id": 211,
                            "name": "CatB",
                            "section_id": 21,
                            "position": 0,
                            "icon_path": "",
                            "links": [
                                {
                                    "id": 2111,
                                    "category_id": 211,
                                    "name": "LB",
                                    "url": "http://b",
                                    "type": "web",
                                    "position": 0,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    db.import_full_structure(copy.deepcopy(bulk_struct))
    exp1 = db.export_full_structure()
    assert _export_names(exp1) == [
        ("sphere", "SB"),
        ("section", "SecB"),
        ("category", "CatB"),
        ("link", "LB"),
    ]

    # 2) Fallback per-row: нет id у части объектов
    fallback_struct = [
        {
            "name": "SF",
            "sections": [
                {
                    "name": "SecF",
                    "categories": [
                        {
                            "name": "CatF",
                            "links": [
                                {
                                    "name": "LF",
                                    "url": "http://f",
                                    "type": "web",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    db.import_full_structure(copy.deepcopy(fallback_struct))
    exp2 = db.export_full_structure()
    assert ("sphere", "SF") in _export_names(exp2)
    assert ("section", "SecF") in _export_names(exp2)
    assert ("category", "CatF") in _export_names(exp2)
    assert ("link", "LF") in _export_names(exp2)


def test_backup_cleanup_continues_on_error(tmp_path, monkeypatch, caplog):
    # Переназначаем пути БД и каталога бэкапов
    from app.models import db as db_module
    db_file = tmp_path / "links.db"
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)
    monkeypatch.setattr(db_module, "BACKUP_DIR", backups_dir, raising=True)

    db = Database()
    db.initialize_or_migrate()

    # Ограничим максимум до 3 бэкапов
    monkeypatch.setattr(Database, "_get_max_backups", lambda self: 3, raising=True)

    # Создаем 3 бэкапа (в пределах лимита)
    for _ in range(3):
        db.backup()

    files_before = sorted(backups_dir.glob("links_*.db"))
    assert len(files_before) == 3

    # Смоделируем ошибку удаления для самого старого файла
    oldest = files_before[0]
    original_unlink = type(oldest).unlink

    def failing_unlink(self):
        if self == oldest:
            raise PermissionError("locked file")
        return original_unlink(self)

    monkeypatch.setattr(type(oldest), "unlink", failing_unlink)

    caplog.clear()
    # Создаем еще один бэкап, что должно запустить очистку
    db.backup()

    # Проверяем, что было предупреждение о неудачном удалении
    warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("Не удалось удалить старую резервную копию" in (rec.getMessage() or "") for rec in warnings)
    
    # Проверяем, что система попыталась удалить файлы и продолжила работу
    files_after = sorted(backups_dir.glob("links_*.db"))
    
    # Должно остаться 4 файла: 3 старых (один заблокирован) + 1 новый
    # Система должна была попытаться удалить 1 файл, но не смогла из-за блокировки
    assert len(files_after) == 4
    
    # Проверяем, что самый старый файл все еще существует (заблокирован)
    assert oldest in files_after
    
    # Проверяем, что новый файл был создан
    newest_file = max(files_after, key=lambda f: f.stat().st_mtime)
    assert newest_file not in files_before


def test_sql_execute_retry_on_closed_connection(tmp_path, monkeypatch):
    # Настраиваем временную БД
    from app.models import db as db_module
    db_file = tmp_path / "links_retry.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_file, raising=True)

    db = Database()
    db.initialize_or_migrate()

    # Первый вызов — соединение активно
    _ = db.spheres.get_spheres()

    # Закрываем соединение вручную
    db.close()

    # Повторный вызов должен сработать за счёт авто-ретрая в _execute_with_error_handling
    res = db.spheres.get_spheres()
    assert isinstance(res, list)
