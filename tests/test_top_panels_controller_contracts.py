from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_init_does_not_require_clear_favorites():
    """Проверяет, что контроллер НЕ требует clear_favorites при инициализации."""
    # Контроллер теперь не должен требовать clear_favorites на этапе инициализации
    fav = SimpleNamespace(set_data=lambda x: None)  # Только set_data
    recent = SimpleNamespace(set_data=lambda x: None)
    # Не должно быть исключения
    TopPanelsController(
        main_window=MagicMock(),
        fav_widget=fav,
        recent_links_widget=recent,
        links_business=MagicMock(),
    )
