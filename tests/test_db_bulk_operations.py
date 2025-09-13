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
    """Детерминированный тест ретенции без зависимости от ОС-локов.

    Проверяем, что при ошибке удаления самого старого файла ретенция всё равно
    укладывается в лимит, удалив другие кандидаты, либо помещая заблокированный
    файл в карантин (rename в .locked).
    """
    from app.utils.backup.backup_manager import apply_retention
    from pathlib import Path as _RealPath

    backups_dir = tmp_path / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    # Подготовим фейковые Path-объекты с контролируемым поведением unlink/rename/stat
    class FakePath:
        def __init__(self, dir_path: _RealPath, name: str, mtime: float, locked: bool = False):
            self._dir = dir_path
            self._name = name
            self._mtime = mtime
            self._exists = True
            self._locked = locked

        # Интерфейс, используемый apply_retention
        def exists(self):
            return self._exists

        def stat(self):
            class S:  # минимальный объект с st_mtime
                def __init__(self, mt):
                    self.st_mtime = mt

            return S(self._mtime)

        def unlink(self):
            if not self._exists:
                return
            if self._locked:
                raise PermissionError("locked file")
            self._exists = False

        def rename(self, target):
            # Разрешим карантин: *.db -> *.db.locked
            self._name = target.name
            # Пометим, что файл более не считается рабочим .db
            return self

        def resolve(self):
            return self

        @property
        def name(self):
            return self._name

        def with_name(self, new_name: str):
            return FakePath(self._dir, new_name, self._mtime, locked=False)

        # Для логов
        def __str__(self):
            return str(self._dir / self._name)

    # Сгенерируем 3 старых файла и 1 новый (keep)
    f1 = FakePath(backups_dir, "links_0001.db", 1.0, locked=True)   # самый старый и заблокирован
    f2 = FakePath(backups_dir, "links_0002.db", 2.0)
    f3 = FakePath(backups_dir, "links_0003.db", 3.0)
    new = FakePath(backups_dir, "links_0004.db", 4.0)

    # Подменяем glob("links_*.db") так, чтобы возвращался наш набор фейковых файлов
    def fake_glob(pattern):
        assert pattern == "links_*.db"
        return [p for p in [f1, f2, f3, new] if p.exists() and p.name.endswith(".db")]

    monkeypatch.setattr(type(backups_dir), "glob", lambda self, pat: fake_glob(pat), raising=True)

    caplog.clear()
    res = apply_retention(backups_dir, max_backups=3, keep={new}, attempts=2, sleep_sec=0.0, settle_sec=0.0)

    # Было предупреждение об ошибке удаления
    warnings = [rec for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("Не удалось удалить старую резервную копию" in (rec.getMessage() or "") for rec in warnings)

    # Итог: среди рабочих бэкапов (*.db) не более 3
    remaining = fake_glob("links_*.db")
    assert len(remaining) <= 3

    # Самый старый должен либо остаться заблокированным, но НЕ считаться рабочим (перенесён в .locked),
    # либо быть всё ещё среди существующих .db, но в пределах лимита за счёт удаления другой копии.
    # Наш фолбэк переименовывает заблокированный файл в .locked, поэтому .db его нет.
    assert all(p.name != "links_0001.db" for p in remaining)

    # Новый сохранён
    assert any(p.name == "links_0004.db" for p in remaining)


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
