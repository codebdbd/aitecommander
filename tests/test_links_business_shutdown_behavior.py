from __future__ import annotations

import logging
import pytest

from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database


class _StubPoolOK:
    def waitForDone(self, timeout: int):  # noqa: N802 - Qt-like API
        return None


class _StubPoolRuntimeError:
    def waitForDone(self, timeout: int):  # noqa: N802 - Qt-like API
        raise RuntimeError("boom")


class _StubPoolUnexpected:
    def waitForDone(self, timeout: int):  # noqa: N802 - Qt-like API
        raise ValueError("unexpected")


class _StubScheduler:
    def __init__(self, pool):
        self._pool = pool

    def get_thread_pool(self):
        return self._pool


@pytest.fixture()
def lb_instance():
    db = Database()
    logger = logging.getLogger("test.links_business.shutdown")
    return LinksBusinessLogic(db, logger=logger)


def test_shutdown_success_returns_true(lb_instance):
    lb_instance.scheduler = _StubScheduler(_StubPoolOK())
    assert lb_instance.shutdown(1) is True


def test_shutdown_runtime_error_returns_false_and_logs(lb_instance, caplog):
    lb_instance.scheduler = _StubScheduler(_StubPoolRuntimeError())
    with caplog.at_level(logging.ERROR):
        assert lb_instance.shutdown(1) is False
    assert any("shutdown (expected)" in r.getMessage() for r in caplog.records)


def test_shutdown_unexpected_error_is_propagated(lb_instance):
    lb_instance.scheduler = _StubScheduler(_StubPoolUnexpected())
    with pytest.raises(ValueError):
        lb_instance.shutdown(1)
