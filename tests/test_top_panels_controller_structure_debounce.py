import logging
from types import SimpleNamespace

from app.controllers.ui.top_panels_controller import TopPanelsController


def test_structure_signals_debounce_to_single_refresh(monkeypatch, caplog, fav_widget_stub_min, rec_widget_stub_min, links_business_stub):
    caplog.set_level(logging.DEBUG)

    ctrl = TopPanelsController(
        SimpleNamespace(),
        fav_widget=fav_widget_stub_min,
        recent_links_widget=rec_widget_stub_min,
        links_business=links_business_stub,
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
