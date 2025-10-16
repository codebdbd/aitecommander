import contextlib
import re

import pytest

from app.models.category_model import CategoryModel


class DummyConnMgr:
    connection = None


class DummyModel(CategoryModel):
    def __init__(self):
        super().__init__(DummyConnMgr())

    @contextlib.contextmanager
    def transaction(self):  # type: ignore[override]
        yield

    def _execute_with_error_handling(self, query: str, params: tuple = (), fetch_method: str = None):  # type: ignore[override]
        # 0) affected sections query
        if query.strip().startswith("SELECT DISTINCT section_id FROM category WHERE id IN"):
            return []
        # 1) delete links
        if query.strip().startswith("DELETE FROM link WHERE category_id IN"):
            return None
        # 2) pre-count categories before delete
        if query.strip().startswith("SELECT COUNT(*) as cnt FROM category WHERE id IN") and fetch_method == "one":
            # count number of placeholders by params length
            return {"cnt": len(params)}
        # 3) delete categories, return cursor without rowcount attribute
        if query.strip().startswith("DELETE FROM category WHERE id IN"):
            return type("NoRowCountCursor", (), {})()
        # default
        return None


def test_delete_categories_bulk_logs_when_rowcount_missing(monkeypatch, caplog):
    model = DummyModel()

    caplog.set_level("WARNING")
    deleted = model.delete_categories_bulk([1, 2, 2, -1, 0])

    # Expect two unique positive IDs -> pre-count 2
    assert deleted == 2

    assert any(
        "delete_categories_bulk: cursor.rowcount not available" in rec.message
        for rec in caplog.records
    ), "Expected warning when rowcount is not available"
