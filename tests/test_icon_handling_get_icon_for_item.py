import logging
from PyQt6.QtGui import QIcon

import app.controllers.ui.structure.icon_handling as ih_mod
from app.controllers.ui.structure.icon_handling import IconHandling


class _DummyController:
    def __init__(self):
        # tree/business не требуются для _get_icon_for_item
        self.tree = None
        self.business = None


def test_get_icon_for_item_success(monkeypatch):
    ctrl = _DummyController()
    ih = IconHandling(ctrl)

    # Успешный резолв и создание QIcon
    monkeypatch.setattr(ih_mod, "resolve_icon_for_link", lambda d: "resolved/path.ico")
    monkeypatch.setattr(ih_mod, "create_icon_from_path", lambda p: QIcon())

    icon = ih._get_icon_for_item("section", "my_icon")
    assert isinstance(icon, QIcon)


def test_get_icon_for_item_filesystem_error_logs_warning_and_returns_empty(monkeypatch, caplog):
    ctrl = _DummyController()
    ih = IconHandling(ctrl)

    caplog.set_level(logging.WARNING)

    # Резолв успешен, но создание QIcon вызывает ожидаемую ошибку
    monkeypatch.setattr(ih_mod, "resolve_icon_for_link", lambda d: "resolved/path.ico")

    class _FsError(OSError):
        pass

    def _raise_fs(_p):
        raise _FsError("fs error")

    monkeypatch.setattr(ih_mod, "create_icon_from_path", _raise_fs)

    icon = ih._get_icon_for_item("category", "icon")
    # Должен вернуть пустой QIcon и записать warning
    assert isinstance(icon, QIcon)
    assert any("filesystem/value error creating icon" in r.message for r in caplog.records)


def test_get_icon_for_item_unexpected_exception_logs_exception_and_returns_empty(monkeypatch, caplog):
    ctrl = _DummyController()
    ih = IconHandling(ctrl)

    caplog.set_level(logging.ERROR)

    # Неожиданное исключение при резолве
    def _boom(_):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(ih_mod, "resolve_icon_for_link", _boom)

    icon = ih._get_icon_for_item("section", "broken")
    assert isinstance(icon, QIcon)
    # Проверяем, что exception залогирован
    assert any("unexpected error resolving icon" in r.message for r in caplog.records)
