from __future__ import annotations

import logging

from app.controllers.ui.top_panels_controller import TopPanelsController


class FavWidgetStub:
    def __init__(self):
        self.data = None

    def set_data(self, items):  # noqa: D401 - simple stub
        self.data = list(items)


class RecentWidgetWithBadLimit:
    def __init__(self, value):
        self._value = value
        self.data = None

    def get_limit(self):  # returns invalid type/value
        return self._value

    def set_data(self, items):  # noqa: D401 - simple stub
        self.data = list(items)


class RecentWidgetRaisingLimit:
    def __init__(self, exc):
        self._exc = exc
        self.data = None

    def get_limit(self):  # raises
        raise self._exc

    def set_data(self, items):  # noqa: D401 - simple stub
        self.data = list(items)


class LinksBusinessSpy:
    def __init__(self):
        self.last_limit = None
        self.recent_links = [
            {"id": 1},
        ]

    def get_recent_links(self, limit: int):  # noqa: D401 - spy
        self.last_limit = int(limit)
        return list(self.recent_links)


class DummyMain:
    pass


def _make_controller(recent_widget, caplog):
    fav = FavWidgetStub()
    lb = LinksBusinessSpy()
    ctrl = TopPanelsController(
        DummyMain(), fav_widget=fav, recent_links_widget=recent_widget, links_business=lb
    )
    caplog.set_level(logging.WARNING)
    ctrl.refresh_recent()
    return ctrl, lb


def test_refresh_recent_uses_default_limit_when_get_limit_returns_invalid(caplog):
    # invalid values: string and non-positive int
    for bad_val in ("ten", 0, -5):
        recent = RecentWidgetWithBadLimit(bad_val)
        _ctrl, lb = _make_controller(recent, caplog)
        # default is 10
        assert lb.last_limit == 10
    # at least one warning recorded about invalid value
    assert any("invalid get_limit() value" in r.getMessage() for r in caplog.records)


def test_refresh_recent_uses_default_limit_and_logs_when_get_limit_raises(caplog):
    recent = RecentWidgetRaisingLimit(TypeError("boom"))
    _ctrl, lb = _make_controller(recent, caplog)
    assert lb.last_limit == 10
    # warning logged about TypeError/ValueError in get_limit
    assert any("get_limit() raised TypeError/ValueError" in r.getMessage() for r in caplog.records)
