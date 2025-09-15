from __future__ import annotations

import logging
import pytest

from app.controllers.business.structure_signals import StructureSignalsManager


class _DummySignal:
    def __init__(self, err: Exception | None = None):
        self.err = err
        self.connected = False

    def connect(self, handler):  # noqa: D401 - simple stub
        if self.err is not None:
            raise self.err
        self.connected = True


class _OwnerAllOk:
    def __init__(self):
        self.item_added = _DummySignal()
        self.item_updated = _DummySignal()
        self.item_deleted = _DummySignal()
        self.items_batch_deleted = _DummySignal()
        self.structure_loaded = _DummySignal()


class _OwnerMissingSome:
    def __init__(self):
        # missing item_updated, items_batch_deleted, structure_loaded
        self.item_added = _DummySignal()
        self.item_deleted = _DummySignal()


class _OwnerWithExpectedErrors:
    def __init__(self):
        # connect raises AttributeError/RuntimeError (expected) for different signals
        self.item_added = _DummySignal(AttributeError("boom"))
        self.item_updated = _DummySignal(RuntimeError("boom"))
        self.item_deleted = _DummySignal()  # ok
        self.items_batch_deleted = _DummySignal()  # ok
        self.structure_loaded = _DummySignal(AttributeError("boom"))


class _OwnerWithUnexpectedError:
    def __init__(self):
        # unexpected during connect -> should propagate
        self.item_added = _DummySignal(ValueError("unexpected"))
        self.item_updated = _DummySignal()
        self.item_deleted = _DummySignal()
        self.items_batch_deleted = _DummySignal()
        self.structure_loaded = _DummySignal()


def test_connect_all_ok_logs_info(caplog):
    owner = _OwnerAllOk()
    mgr = StructureSignalsManager(owner, logger=logging.getLogger("signals_test"))
    with caplog.at_level(logging.INFO):
        mgr.connect()
    # all mandatory connected
    assert owner.item_added.connected
    assert owner.item_updated.connected
    assert owner.item_deleted.connected
    assert owner.items_batch_deleted.connected
    # optional connected too
    assert owner.structure_loaded.connected
    # info line present
    assert any("Handlers connected" in r.getMessage() for r in caplog.records)


def test_connect_missing_signals_logs_debug_and_continues(caplog):
    owner = _OwnerMissingSome()
    mgr = StructureSignalsManager(owner, logger=logging.getLogger("signals_test"))
    with caplog.at_level(logging.DEBUG):
        mgr.connect()
    # existing ones connected
    assert owner.item_added.connected
    assert owner.item_deleted.connected
    # debug entries for missing attr
    assert any("connect: failed (expected)" in r.getMessage() for r in caplog.records)


def test_connect_expected_errors_on_connect_logged_and_suppressed(caplog):
    owner = _OwnerWithExpectedErrors()
    mgr = StructureSignalsManager(owner, logger=logging.getLogger("signals_test"))
    with caplog.at_level(logging.DEBUG):
        mgr.connect()
    # item_deleted and items_batch_deleted should be connected
    assert owner.item_deleted.connected
    assert owner.items_batch_deleted.connected
    # expected failures logged at debug
    msgs = [r.getMessage() for r in caplog.records]
    assert any("connect: failed (expected)" in m for m in msgs)
    # optional structure_loaded also logs debug failure
    assert any("structure_loaded" in m or "прогрев кэша" in m for m in msgs)


def test_connect_unexpected_error_is_propagated(caplog):
    owner = _OwnerWithUnexpectedError()
    mgr = StructureSignalsManager(owner, logger=logging.getLogger("signals_test"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ValueError):
            mgr.connect()
    # ensure an exception-level log was recorded
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
