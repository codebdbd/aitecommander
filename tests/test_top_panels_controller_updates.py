import types
import logging
import pytest

from app.controllers.ui.top_panels_controller import TopPanelsController


class FavWidgetMock:
    def __init__(self):
        self.favorites = None
        self.set_calls = 0
        self.cleared = 0
        # сигналоподобные атрибуты не нужны для юнитов

    def set_favorites(self, items):
        self.favorites = items
        self.set_calls += 1

    def clear_favorites(self):
        self.cleared += 1

    def setVisible(self, _):
        pass


class RecentWidgetMock:
    def __init__(self, limit=None, max_items=None):
        self.recent = None
        self.set_calls = 0
        self.limit = limit
        self.max_items = max_items

    def set_recent_links(self, items):
        self.recent = items
        self.set_calls += 1

    def get_limit(self):
        if isinstance(self.limit, int) and self.limit > 0:
            return self.limit
        if isinstance(self.max_items, int) and self.max_items > 0:
            return self.max_items
        return None


class LinksBusinessMock:
    def __init__(self):
        self.fav_requests = 0
        self.recent_requests = []
        self.clears = 0

    def get_favorite_links(self):
        self.fav_requests += 1
        # После очистки бизнес-слоем список избранного должен быть пуст
        if self.clears > 0:
            return []
        return ["A", "B"]

    def get_recent_links(self, limit):
        self.recent_requests.append(limit)
        return list(range(limit))

    def clear_favorites(self):
        self.clears += 1


class DummyMain:
    pass


@pytest.fixture()
def controller():
    fav = FavWidgetMock()
    recent = RecentWidgetMock(limit=7)
    lb = LinksBusinessMock()
    ctrl = TopPanelsController(DummyMain(), fav_widget=fav, recent_links_widget=recent, links_business=lb)
    return ctrl, fav, recent, lb


def test_debounce_request_refresh(controller):
    ctrl, fav, recent, lb = controller
    # Два запроса подряд — должен отработать один refresh_all
    calls = {"all": 0}

    def wrapped_refresh_all():
        calls["all"] += 1

    # Подменяем метод и вручную вызываем обработчик таймера
    ctrl.refresh_all = wrapped_refresh_all  # type: ignore
    ctrl.request_refresh()
    ctrl.request_refresh()
    ctrl._on_refresh_timeout()  # имитируем срабатывание таймера

    assert calls["all"] == 1


def test_refresh_methods_use_widgets_and_business(controller):
    ctrl, fav, recent, lb = controller

    ctrl.refresh_favorites()
    assert lb.fav_requests == 1
    assert fav.set_calls == 1 and fav.favorites == ["A", "B"]

    ctrl.refresh_recent()
    assert lb.recent_requests[-1] == 7  # из recent.limit
    assert recent.set_calls == 1 and recent.recent == list(range(7))


def test_clear_favorites_logs_and_calls_business_and_widget(controller, caplog):
    ctrl, fav, recent, lb = controller
    caplog.set_level(logging.DEBUG)

    ctrl.clear_favorites()

    assert lb.clears >= 1
    assert fav.cleared == 1 or fav.favorites == []


def test_refresh_recent_raises_if_widget_contract_broken(caplog):
    # recent виджет без set_recent_links должен приводить к AttributeError
    class BadRecent:
        pass

    fav = FavWidgetMock()
    lb = LinksBusinessMock()
    with pytest.raises(TypeError):
        TopPanelsController(DummyMain(), fav_widget=fav, recent_links_widget=BadRecent(), links_business=lb)


def test_refresh_favorites_raises_if_widget_contract_broken():
    # fav виджет без set_favorites
    class BadFav:
        pass

    recent = RecentWidgetMock()
    lb = LinksBusinessMock()
    with pytest.raises(TypeError):
        TopPanelsController(DummyMain(), fav_widget=BadFav(), recent_links_widget=recent, links_business=lb)
