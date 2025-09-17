import logging
from types import SimpleNamespace

from app.controllers.system.window_controllers_setup import (
    _connect_top_panels_signals_explicit,
)
from app.controllers.ui.top_panels_controller import TopPanelsController


class SignalStub:
    def __init__(self):
        self._subs = []

    def connect(self, cb):
        self._subs.append(cb)

    def emit(self, *args, **kwargs):
        for cb in list(self._subs):
            cb(*args, **kwargs)

    # Поддержка синтаксиса signal[int]
    def __getitem__(self, _):
        return self


class FavWidgetStub:
    def __init__(self):
        self.refreshRequested = SignalStub()
        self.clearRequested = SignalStub()
        self.linkClicked = SignalStub()

    def set_favorites(self, items):
        pass

    def clear_favorites(self):
        pass


class RecWidgetStub:
    def __init__(self):
        self.refreshRequested = SignalStub()
        self.linkClicked = SignalStub()

    def set_recent_links(self, items):
        pass


class LinksBusinessStub:
    def get_favorite_links(self):
        return []

    def get_recent_links(self, limit: int):
        return []


def test_top_panels_signals_are_debounced(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    fav = FavWidgetStub()
    rec = RecWidgetStub()

    # Минимальный window-стаб
    window = SimpleNamespace()
    window.fav_widget = fav
    window.recent_links_widget = rec
    window.links_actions = SimpleNamespace(open_link=lambda *_: None)

    # Контроллер верхних панелей
    ctrl = TopPanelsController(
        window,
        fav_widget=fav,
        recent_links_widget=rec,
        links_business=LinksBusinessStub(),
    )
    window.top_panels_controller = ctrl

    # Подключаем сигналы (проверяем, что идут в request_* методы) — явный вызов
    _connect_top_panels_signals_explicit(
        top_panels_controller=window.top_panels_controller,
        links_actions=window.links_actions,
        fav_widget=window.fav_widget,
        recent_links_widget=window.recent_links_widget,
        quick_add_widget=None,
        auto_hide_tree_filter=None,
        topbar_manager=None,
    )

    fav_calls = []
    rec_calls = []

    def fake_refresh_favorites():
        fav_calls.append(1)

    def fake_refresh_recent():
        rec_calls.append(1)

    # Подменяем фактические методы, которые вызываются после таймаута
    ctrl.refresh_favorites = fake_refresh_favorites  # type: ignore[assignment]
    ctrl.refresh_recent = fake_refresh_recent  # type: ignore[assignment]

    # Эмитим серию запросов refreshRequested — должны схлопнуться в один
    fav.refreshRequested.emit()
    fav.refreshRequested.emit()
    fav.refreshRequested.emit()

    rec.refreshRequested.emit(10)
    rec.refreshRequested.emit(5)

    # Исполняем таймауты вручную
    ctrl._on_fav_refresh_timeout()
    ctrl._on_recent_refresh_timeout()

    assert len(fav_calls) == 1, (
        "Должен быть один вызов refresh_favorites при серии refreshRequested"
    )
    assert len(rec_calls) == 1, (
        "Должен быть один вызов refresh_recent при серии refreshRequested"
    )
