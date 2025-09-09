import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.top_panels_controller import TopPanelsController


class FavWidgetMock:
    def __init__(self):
        self.calls = []

    def set_favorites(self, items):  # новый основной путь
        self.calls.append(("set_favorites", items))

    def clear_favorites(self):
        self.calls.append("clear_favorites")


class RecentLinksWidgetMock:
    def __init__(self):
        self.calls = []

    def set_recent_links(self, items):  # новый основной путь
        self.calls.append(("set_recent_links", items))


class LinksBusinessStub:
    def get_favorite_links(self):
        return [{"id": 1}, {"id": 2}]

    def get_recent_links(self, limit: int):
        # Убедимся, что лимит применяется
        return [{"id": i} for i in range(min(limit, 10))]


def test_refresh_all_success(caplog):
    caplog.set_level(logging.DEBUG)
    fav = FavWidgetMock()
    recent = RecentLinksWidgetMock()
    ctrl = TopPanelsController(
        SimpleNamespace(),
        fav_widget=fav,
        recent_links_widget=recent,
        links_business=LinksBusinessStub(),
    )

    ctrl.refresh_all()

    # Проверяем, что данные установлены через set_*
    assert len(fav.calls) == 1 and fav.calls[0][0] == "set_favorites"
    assert len(recent.calls) == 1 and recent.calls[0][0] == "set_recent_links"


def test_refresh_methods_log_on_errors(caplog):
    class ErrFav(FavWidgetMock):
        def set_favorites(self, items):  # type: ignore[override]
            raise RuntimeError("boom fav")

    class ErrRecent(RecentLinksWidgetMock):
        def set_recent_links(self, items):  # type: ignore[override]
            raise RuntimeError("boom recent")

    caplog.set_level(logging.ERROR)
    ctrl = TopPanelsController(
        SimpleNamespace(),
        fav_widget=ErrFav(),
        recent_links_widget=ErrRecent(),
        links_business=LinksBusinessStub(),
    )

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
    ctrl = TopPanelsController(
        SimpleNamespace(),
        fav_widget=ErrFav(),
        recent_links_widget=RecentLinksWidgetMock(),
        links_business=LinksBusinessStub(),
    )

    ctrl.clear_favorites()

    errs = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any("clear_favorites" in rec.getMessage() for rec in errs)


def test_init_requires_widgets():
    with pytest.raises(ValueError):
        TopPanelsController(
            SimpleNamespace(),
            fav_widget=None,
            recent_links_widget=RecentLinksWidgetMock(),
            links_business=LinksBusinessStub(),
        )
    with pytest.raises(ValueError):
        TopPanelsController(
            SimpleNamespace(),
            fav_widget=FavWidgetMock(),
            recent_links_widget=None,
            links_business=LinksBusinessStub(),
        )


def test_refresh_favorites_requires_set_method():
    class NoSetFav:
        pass

    with pytest.raises(TypeError):
        TopPanelsController(
            SimpleNamespace(),
            fav_widget=NoSetFav(),
            recent_links_widget=RecentLinksWidgetMock(),
            links_business=LinksBusinessStub(),
        )


def test_refresh_recent_requires_set_method():
    class NoSetRecent:
        limit = 5

    with pytest.raises(TypeError):
        TopPanelsController(
            SimpleNamespace(),
            fav_widget=FavWidgetMock(),
            recent_links_widget=NoSetRecent(),
            links_business=LinksBusinessStub(),
        )
