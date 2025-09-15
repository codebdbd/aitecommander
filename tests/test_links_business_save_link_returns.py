from __future__ import annotations

import logging
import types

import pytest

from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database


class StubLinksOK:
    def __init__(self, ret_id: int = 123):
        self._ret_id = ret_id

    def create_or_update_link(self, data: dict) -> int:
        return self._ret_id


class StubLinksFail:
    def create_or_update_link(self, data: dict):
        raise RuntimeError("db boom")


def _valid_link_data(category_id: int = 1) -> dict:
    return {
        "id": None,
        "name": "Example",
        "url": "https://example.com",
        "type": "url",
        "category_id": category_id,
    }


@pytest.fixture()
def lb_instance():
    db = Database()
    logger = logging.getLogger("test.links_business")
    return LinksBusinessLogic(db, logger=logger)


def test_save_link_returns_id_on_success(lb_instance, monkeypatch):
    # Arrange: stub LinksService on instance
    lb_instance.links = StubLinksOK(777)

    # Act
    res = lb_instance.save_link(_valid_link_data())

    # Assert
    assert res == 777


def test_save_link_returns_none_on_handled_db_error(lb_instance, monkeypatch, caplog):
    # Arrange: make LinksService raise, and mark error as handled
    lb_instance.links = StubLinksFail()

    # Patch handle_db_error inside module to simulate handled error
    import app.controllers.business.links_business as lb_module

    monkeypatch.setattr(lb_module, "handle_db_error", lambda e, self: True)

    caplog.set_level(logging.ERROR)

    # Act
    result = lb_instance.save_link(_valid_link_data())

    # Assert: handled -> None, error was logged
    assert result is None
    assert any("Ошибка сохранения ссылки" in r.getMessage() for r in caplog.records)


def test_save_link_raises_on_unhandled_db_error(lb_instance, monkeypatch):
    # Arrange: make LinksService raise, and mark error as unhandled
    lb_instance.links = StubLinksFail()

    import app.controllers.business.links_business as lb_module

    monkeypatch.setattr(lb_module, "handle_db_error", lambda e, self: False)

    # Act / Assert
    with pytest.raises(RuntimeError):
        lb_instance.save_link(_valid_link_data())
