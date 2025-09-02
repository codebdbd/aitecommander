import types

import pytest

from app.controllers.ui.top_panels_controller import TopPanelsController


class _FakeSignal:
    def __init__(self):
        self._callback = None

    def connect(self, cb):
        self._callback = cb

    def emit(self):
        if self._callback:
            self._callback()


class FakeTimer:
    def __init__(self):
        self._active = False
        self.timeout = _FakeSignal()

    def setSingleShot(self, *_):
        pass

    def setInterval(self, *_):
        pass

    def isActive(self):
        return self._active

    def start(self, *_):
        # В тесте сразу эмулируем таймаут
        self._active = True
        # Вызываем callback синхронно, как будто сработал таймаут
        if self.timeout._callback:
            self.timeout._callback()

    def stop(self):
        self._active = False


class FakeFavWidget:
    def set_favorites(self, items):
        self._items = list(items)

    def clear_favorites(self):
        self._items = []


class FakeRecentsWidget:
    def set_recent_links(self, items):
        self._items = list(items)


class FakeLinksBusiness:
    def get_favorite_links(self):
        return []

    def get_recent_links(self, limit):
        return []

    def clear_favorites(self):
        pass


def test_structure_timer_stops_when_request_refresh_fails(monkeypatch):
    # Контроллер с фейковыми зависимостями
    ctrl = TopPanelsController(
        main_window=None,
        fav_widget=FakeFavWidget(),
        recent_links_widget=FakeRecentsWidget(),
        links_business=FakeLinksBusiness(),
    )

    # Подменяем таймер на фейковый и переподключаем слот
    ctrl._structure_refresh_timer = FakeTimer()
    ctrl._structure_refresh_timer.timeout.connect(ctrl._on_structure_refresh_timeout)

    # Эмулируем сбой в request_refresh
    def boom(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr(ctrl, "request_refresh", boom, raising=True)

    # schedule должен стартовать таймер, который немедленно вызовет timeout-обработчик,
    # внутри которого произойдёт ошибка и в finally таймер должен быть остановлен
    ctrl.schedule_structure_refresh()

    assert not ctrl._structure_refresh_timer.isActive(), "structure refresh timer must be stopped after failure"
