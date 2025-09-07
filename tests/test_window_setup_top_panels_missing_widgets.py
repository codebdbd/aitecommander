import pytest

from app.controllers.system.window_controllers_setup import (
    SetupError,
    _connect_top_panels_signals_explicit,
)


class WindowStub:
    def __init__(self):
        # имитируем наличие top_panels_controller и links_actions для более поздних проверок, но целимся в отсутствие виджетов
        self.top_panels_controller = object()
        self.links_actions = type("LA", (), {"open_link": lambda *a, **k: None})()


def test_missing_favorites_widget_raises_setup_error():
    w = WindowStub()
    with pytest.raises(SetupError):
        _connect_top_panels_signals_explicit(
            top_panels_controller=w.top_panels_controller,
            links_actions=w.links_actions,
            fav_widget=getattr(w, "fav_widget", None),
            recent_links_widget=getattr(w, "recent_links_widget", None),
            links=None,
            quick_add_widget=None,
            auto_hide_tree_filter=None,
            topbar_manager=None,
        )


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
        _connect_top_panels_signals_explicit(
            top_panels_controller=w.top_panels_controller,
            links_actions=w.links_actions,
            fav_widget=getattr(w, "fav_widget", None),
            recent_links_widget=getattr(w, "recent_links_widget", None),
            links=None,
            quick_add_widget=None,
            auto_hide_tree_filter=None,
            topbar_manager=None,
        )
