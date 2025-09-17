import logging
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QTimer

from app.controllers.ui.top_panels_controller import SetupError, TopPanelsController


class FavWidgetMock:
    def set_favorites(self, items):
        pass

    def clear_favorites(self):
        pass


class RecentLinksWidgetMock:
    def set_recent_links(self, items):
        pass


class LinksBusinessStub:
    def get_favorite_links(self):
        return []

    def get_recent_links(self, limit: int):
        return []


def test_init_raises_setup_error_when_timer_interval_setup_fails(monkeypatch, caplog):
    # Force QTimer.setInterval to fail to ensure SetupError is raised and logged
    def boom(self, *_args, **_kwargs):  # noqa: ARG002
        raise RuntimeError("interval fail")

    monkeypatch.setattr(QTimer, "setInterval", boom, raising=True)

    caplog.set_level(logging.ERROR)

    with pytest.raises(SetupError):
        TopPanelsController(
            SimpleNamespace(),
            fav_widget=FavWidgetMock(),
            recent_links_widget=RecentLinksWidgetMock(),
            links_business=LinksBusinessStub(),
        )

    assert any(
        "failed to set structure timer interval" in rec.getMessage().lower()
        for rec in caplog.records
    )
