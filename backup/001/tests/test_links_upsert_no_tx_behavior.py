import sqlite3
import pytest

from app.models.link_model import LinkModel


class _ConnManager:
    """Простейший менеджер соединения для LinkModel с in-memory SQLite."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    @property
    def connection(self):
        return self._conn

    def _create_schema(self):
        self._conn.executescript(
            """
            CREATE TABLE link (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                name TEXT,
                url TEXT,
                type TEXT,
                notes TEXT,
                is_favorite INTEGER,
                last_used TEXT,
                icon_path TEXT,
                args TEXT,
                position INTEGER,
                browser_key TEXT,
                UNIQUE(category_id, name, url, args)
            );
            """
        )


@pytest.fixture()
def link_model():
    return LinkModel(_ConnManager())


def test_upsert_links_no_tx_per_record_inserts_and_ids_assigned(monkeypatch, link_model):
    """
    Проверяем, что для записей без id используются поштучные INSERT (не executemany),
    и что id присваиваются входным элементам и возвращаются в created_ids.
    """
    insert_counter = {"count": 0}

    # executemany не должен вызываться для вставок без id в этом сценарии
    def _forbid_executemany(*args, **kwargs):
        raise AssertionError("executemany should not be called for no-id inserts")

    monkeypatch.setattr(link_model, "_execute_many_with_error_handling", _forbid_executemany)

    orig_exec = link_model._execute_with_error_handling

    def _count_inserts(query: str, params=(), fetch_method=None):
        # Считаем только вставки без явного столбца id
        if query.strip().upper().startswith("INSERT INTO LINK (") and "(ID," not in query.upper():
            insert_counter["count"] += 1
        return orig_exec(query, params, fetch_method)

    monkeypatch.setattr(link_model, "_execute_with_error_handling", _count_inserts)

    items = [
        {"category_id": 1, "name": "A", "url": "u1", "args": "", "type": "web"},
        {"category_id": 1, "name": "B", "url": "u2", "args": "", "type": "web"},
        {"category_id": 1, "name": "C", "url": "u3", "args": "", "type": "web"},
    ]

    created_ids = link_model.batch_upsert_links(items)

    assert len(created_ids) == 3
    assert insert_counter["count"] == 3
    for it in items:
        assert isinstance(it.get("id"), int) and it["id"] > 0


def test_upsert_links_no_tx_duplicates_do_not_create_new(monkeypatch, link_model):
    """
    Проверяем, что дубликаты по (category_id,name,url,args) не создают новые записи:
    повторный апсерт возвращает существующие id, created_ids пуст.
    """
    items = [
        {"category_id": 2, "name": "X", "url": "ux", "args": "", "type": "web"},
        {"category_id": 2, "name": "Y", "url": "uy", "args": "", "type": "web"},
    ]
    created_first = link_model.batch_upsert_links(items)
    assert len(created_first) == 2
    ids_first = [it["id"] for it in items]

    # Повторяем те же записи (дубликаты)
    dupl = [
        {"category_id": 2, "name": "X", "url": "ux", "args": "", "type": "web"},
        {"category_id": 2, "name": "Y", "url": "uy", "args": "", "type": "web"},
    ]
    created_second = link_model.batch_upsert_links(dupl)

    assert created_second == []
    ids_second = [it["id"] for it in dupl]
    assert ids_second == ids_first
