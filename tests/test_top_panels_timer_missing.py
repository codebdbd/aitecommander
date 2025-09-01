import types
import pytest

from app.controllers.ui.top_panels_controller import TopPanelsController, SetupError


class FavWidget:
    def set_favorites(self, items):
        pass
    def clear_favorites(self):
        pass


class RecentsWidget:
    def set_recent_links(self, items):
        pass


class LinksBusiness:
    def get_favorite_links(self):
        return []

    def get_recent_links(self, limit):
        return []


class MainWindow:
    # минимальный объект окна, чтобы назначить родителя таймеров без ошибок
    def setUpdatesEnabled(self, *_):
        pass


def make_controller():
    return TopPanelsController(
        MainWindow(),
        fav_widget=FavWidget(),
        recent_links_widget=RecentsWidget(),
        links_business=LinksBusiness(),
    )


def test_schedule_structure_refresh_raises_setup_error_when_timer_missing():
    ctrl = make_controller()
    # Эмулируем отсутствие таймера
    ctrl._structure_refresh_timer = None
    with pytest.raises(SetupError, match=r"Structure refresh timer is not configured"):
        ctrl.schedule_structure_refresh()
