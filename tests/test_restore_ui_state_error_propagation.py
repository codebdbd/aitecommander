import logging
from types import SimpleNamespace

import pytest

from app.controllers.system.window_controllers_setup import DatabaseEventHandler


class LinksTableControllerStub:
    def __init__(self):
        self.called_with = None

    def reload(self, category_id):
        raise RuntimeError("reload failed")


class LinksBusinessStub:
    def load_links(self, category_id):  # noqa: ARG002
        raise RuntimeError("business load failed")


def test_restore_ui_state_logs_and_raises_on_table_reload_error(caplog):
    caplog.set_level(logging.ERROR)
    window = SimpleNamespace(
        get_current_category_id=lambda: 42,
        links_table_controller=LinksTableControllerStub(),
        links_business=LinksBusinessStub(),
    )

    with pytest.raises(RuntimeError):
        DatabaseEventHandler._restore_ui_state(window)

    # Проверяем, что было логирование ошибки
    assert any(
        "_restore_ui_state: unexpected error during table reload" in rec.getMessage()
        for rec in caplog.records
    )


def test_restore_ui_state_logs_and_raises_on_business_load_error_when_no_table(caplog):
    caplog.set_level(logging.ERROR)
    window = SimpleNamespace(
        get_current_category_id=lambda: 42,
        links_table_controller=None,  # нет контроллера таблицы
        links_business=LinksBusinessStub(),
    )

    with pytest.raises(RuntimeError):
        DatabaseEventHandler._restore_ui_state(window)

    assert any(
        "_restore_ui_state: unexpected error during business load_links" in rec.getMessage()
        for rec in caplog.records
    )
