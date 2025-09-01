import logging
from types import SimpleNamespace

from app.controllers.ui.top_panels_controller import TopPanelsController


def test_request_refresh_debounce(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    # Минимальные совместимые стабовые виджеты
    class _Fav:
        def set_favorites(self, items):
            pass
        def clear_favorites(self):
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

    # Подменяем метод, который будет вызван таймером
    ctrl.refresh_all = fake_refresh_all  # type: ignore[assignment]

    # Два запроса подряд должны слиться в один
    ctrl.request_refresh(delay_ms=50)
    ctrl.request_refresh(delay_ms=50)

    # Симулируем срабатывание таймера один раз
    ctrl._on_refresh_timeout()

    assert len(calls) == 1, "Повторные запросы в окне задержки не должны давать повторных обновлений"

    # После срабатывания флаг должен быть сброшен, следующий запрос должен запланироваться
    ctrl.request_refresh(delay_ms=0)
    ctrl._on_refresh_timeout()

    assert len(calls) == 2, "После завершения предыдущего обновления следующий запрос должен выполниться"
