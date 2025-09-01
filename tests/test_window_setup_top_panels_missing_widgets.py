import pytest

from app.controllers.system.window_controllers_setup import _connect_top_panels_signals, SetupError


class WindowStub:
    def __init__(self):
        # имитируем наличие top_panels_controller и links_actions для более поздних проверок, но целимся в отсутствие виджетов
        self.top_panels_controller = object()
        self.links_actions = type("LA", (), {"open_link": lambda *a, **k: None})()


def test_missing_favorites_widget_raises_setup_error():
    w = WindowStub()
    with pytest.raises(SetupError):
        _connect_top_panels_signals(w, controllers={})


def test_missing_recent_links_widget_raises_setup_error():
    # С фаворитами всё есть, но нет recent_links_widget
    class W(WindowStub):
        def __init__(self):
            super().__init__()
            # добавим fav_widget c нужными сигналами-стабами
            class _Sig:
                def connect(self, *_):
                    pass
            self.fav_widget = type(
                "FavW",
                (),
                {
                    "linkClicked": _Sig(),
                    "refresh_requested": _Sig(),
                    "clear_requested": _Sig(),
                },
            )()
    w = W()
    with pytest.raises(SetupError):
        _connect_top_panels_signals(w, controllers={})
