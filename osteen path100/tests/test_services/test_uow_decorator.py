from __future__ import annotations

import pytest

from app.services.uow import unit_of_work


class _Tx:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        self.state["enter"] += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.state["exit"] += 1
        # Do not suppress exceptions
        return False


class DummyDB:
    def __init__(self):
        self.state = {"enter": 0, "exit": 0}

    def transaction(self):
        return _Tx(self.state)


class DummyService:
    def __init__(self, db):
        self.db = db

    @unit_of_work
    def do_something(self, value: int) -> int:
        # Simulate some logic and return a value
        return value * 2

    @unit_of_work
    def raise_error(self):
        raise RuntimeError("boom")


def test_unit_of_work_wraps_method_in_transaction():
    db = DummyDB()
    svc = DummyService(db)

    result = svc.do_something(21)

    assert result == 42
    assert db.state["enter"] == 1
    assert db.state["exit"] == 1


def test_unit_of_work_propagates_exceptions_and_exits_transaction():
    db = DummyDB()
    svc = DummyService(db)

    with pytest.raises(RuntimeError, match="boom"):
        svc.raise_error()

    assert db.state["enter"] == 1
    assert db.state["exit"] == 1
