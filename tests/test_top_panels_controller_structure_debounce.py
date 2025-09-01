import logging
from types import SimpleNamespace

from app.controllers.ui.top_panels_controller import TopPanelsController


def test_structure_signals_debounce_to_single_refresh(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    class _Fav:
        def set_favorites(self, items):
            pass

    class _Rec:
        def set_recent_links(self, items):
            pass

    class LinksBusinessStub:
        def get_favorite_links(self):
            return []

        def get_recent_links(self, limit: int):
            return []

    ctrl = TopPanelsController(
        SimpleNamespace(),
        fav_widget=_Fav(),
        recent_links_widget=_Rec(),
        links_business=LinksBusinessStub(),
    )

    calls: list[int] = []

    def fake_refresh_all():
        calls.append(1)

    # Подменяем метод, который будет вызван основным таймером обновления
    ctrl.refresh_all = fake_refresh_all  # type: ignore[assignment]

    # Многократные структурные события должны слиться в один запуск
    ctrl.schedule_structure_refresh()
    ctrl.schedule_structure_refresh()
    ctrl.schedule_structure_refresh()

    # Симулируем срабатывание таймера структурных событий
    ctrl._on_structure_refresh_timeout()

    # А затем срабатывание основного таймера обновления панелей
    ctrl._on_refresh_timeout()

    assert len(calls) == 1, "Серия структурных событий должна приводить к одному refresh_all"
