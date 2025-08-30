import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.top_panels_controller import TopPanelsController


class FavWidgetMock:
    def __init__(self):
        self.calls = []

    def update_favorites(self):
        self.calls.append("update_favorites")

    def clear_favorites(self):
        self.calls.append("clear_favorites")


class RecentLinksWidgetMock:
    def __init__(self):
        self.calls = []

    def update_recent_links(self):
        self.calls.append("update_recent_links")


def test_refresh_all_success(caplog):
    caplog.set_level(logging.DEBUG)
    fav = FavWidgetMock()
    recent = RecentLinksWidgetMock()
    ctrl = TopPanelsController(SimpleNamespace(), fav_widget=fav, recent_links_widget=recent)

    ctrl.refresh_all()

    assert fav.calls == ["update_favorites"]
    assert recent.calls == ["update_recent_links"]


def test_refresh_methods_log_on_errors(caplog):
    class ErrFav(FavWidgetMock):
        def update_favorites(self):  # type: ignore[override]
            raise RuntimeError("boom fav")

    class ErrRecent(RecentLinksWidgetMock):
        def update_recent_links(self):  # type: ignore[override]
            raise RuntimeError("boom recent")

    caplog.set_level(logging.ERROR)
    ctrl = TopPanelsController(SimpleNamespace(), fav_widget=ErrFav(), recent_links_widget=ErrRecent())

    ctrl.refresh_favorites()
    ctrl.refresh_recent()

    # И ошибки залогированы, и не вылетели наружу
    errs = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any("refresh_favorites" in rec.getMessage() for rec in errs)
    assert any("refresh_recent" in rec.getMessage() for rec in errs)


def test_clear_favorites_logs_on_error(caplog):
    class ErrFav(FavWidgetMock):
        def clear_favorites(self):  # type: ignore[override]
            raise RuntimeError("boom clear")

    caplog.set_level(logging.ERROR)
    ctrl = TopPanelsController(SimpleNamespace(), fav_widget=ErrFav(), recent_links_widget=RecentLinksWidgetMock())

    ctrl.clear_favorites()

    errs = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any("clear_favorites" in rec.getMessage() for rec in errs)


def test_init_requires_widgets():
    with pytest.raises(ValueError):
        TopPanelsController(SimpleNamespace(), fav_widget=None, recent_links_widget=RecentLinksWidgetMock())
    with pytest.raises(ValueError):
        TopPanelsController(SimpleNamespace(), fav_widget=FavWidgetMock(), recent_links_widget=None)
