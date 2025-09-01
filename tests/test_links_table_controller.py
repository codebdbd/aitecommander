import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.links.table_controller import LinksTableController


class BusinessMock:
    def __init__(self):
        self.calls = []
        self.ctrl = None  # will be set from test

    def load_links(self, category_id: int):
        self.calls.append(("load_links", category_id))


class ReentrantBusinessMock(BusinessMock):
    def __init__(self, second_category: int):
        super().__init__()
        self.second_category = second_category

    def load_links(self, category_id: int):  # type: ignore[override]
        # Вызовем перезагрузку с другой категорией пока идёт первая,
        # чтобы проверить постановку в очередь и обработку в finally
        super().load_links(category_id)
        assert self.ctrl is not None
        self.ctrl.reload(self.second_category)


class TableMock:
    def __init__(self, raise_on_update: Exception | None = None):
        self.calls = []
        self._err = raise_on_update

    def update_link_by_id(self, link_dict):
        self.calls.append(("update", dict(link_dict)))
        if self._err:
            raise self._err

    # Добавлено для соответствия LinksTableLike
    def populate(self, links, mode: str = "default"):
        self.calls.append(("populate", mode, list(links) if links is not None else []))


def make_controller(table=None, business=None):
    # main_window=None, чтобы QObject не требовал валидного родителя
    return LinksTableController(None, table=table, links_business=business)


def test_reload_success_calls_business(caplog):
    caplog.set_level(logging.DEBUG)
    biz = BusinessMock()
    ctrl = make_controller(table=TableMock(), business=biz)

    ctrl.reload(10)

    assert biz.calls == [("load_links", 10)]


def test_reload_queues_second_request_and_processes(caplog):
    caplog.set_level(logging.DEBUG)
    biz = ReentrantBusinessMock(second_category=20)
    ctrl = make_controller(table=TableMock(), business=biz)
    biz.ctrl = ctrl

    ctrl.reload(10)

    # Ожидаем, что сначала загрузили 10, в процессе поставили в очередь 20 и затем обработали её
    assert biz.calls == [("load_links", 10), ("load_links", 20)]


def test_reload_ignores_invalid_category(caplog):
    caplog.set_level(logging.DEBUG)
    biz = BusinessMock()
    ctrl = make_controller(table=TableMock(), business=biz)

    ctrl.reload(0)
    ctrl.reload(None)  # type: ignore[arg-type]

    assert biz.calls == []


def test_update_row_success():
    table = TableMock()
    biz = BusinessMock()
    ctrl = make_controller(table=table, business=biz)

    ctrl.update_row({"id": 1, "name": "x"})

    assert table.calls == [("update", {"id": 1, "name": "x"})]


def test_update_row_handles_errors(caplog):
    caplog.set_level(logging.WARNING)
    table = TableMock(raise_on_update=RuntimeError("boom"))
    ctrl = make_controller(table=table, business=BusinessMock())

    ctrl.update_row({"id": 1})

    # Ошибка не выброшена наружу, но залогирована
    assert any("LinksTableController.update_row" in rec.getMessage() for rec in caplog.records)


def test_reload_handles_unexpected_error(caplog):
    caplog.set_level(logging.ERROR)

    class ErrBusiness:
        def load_links(self, category_id: int):
            raise RuntimeError("boom")

    ctrl = make_controller(table=TableMock(), business=ErrBusiness())

    ctrl.reload(5)

    # Лог должен присутствовать, падения нет
    assert any("unexpected error" in rec.getMessage() for rec in caplog.records)
