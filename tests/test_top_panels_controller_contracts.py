import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.top_panels_controller import TopPanelsController


class FavNoClear:
    def set_favorites(self, items):
        pass


class RecentLinksWidgetMock:
    def set_recent_links(self, items):
        pass


class LinksBusinessStub:
    def get_favorite_links(self):
        return []

    def get_recent_links(self, limit: int):
        return []


def test_init_requires_favorites_with_clear():
    with pytest.raises(TypeError):
        TopPanelsController(
            SimpleNamespace(),
            fav_widget=FavNoClear(),
            recent_links_widget=RecentLinksWidgetMock(),
            links_business=LinksBusinessStub(),
        )
