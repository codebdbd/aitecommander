import logging
import pytest
from types import SimpleNamespace

from app.controllers.ui.top_panels_controller import TopPanelsController
from app.controllers.system.window_controllers_setup import _on_structure_changed_schedule_refresh, SetupError


class TimerStubBase:
    def isActive(self):  # noqa: N802 (Qt style)
        return False

    def start(self):
        raise NotImplementedError

    def setSingleShot(self, *_):
        pass

    def setInterval(self, *_):
        pass


class RuntimeErrorTimer(TimerStubBase):
    def start(self):
        raise RuntimeError("qt runtime fail")


class KeyErrorTimer(TimerStubBase):
    def start(self):
        raise KeyError("unexpected")


class QObjectLike:
    pass


def make_ctrl_with_timer(timer):
    # Минимальные зависимости для TopPanelsController
    class Fav:
        def set_favorites(self, *_):
            pass
        def clear_favorites(self):
            pass

    class Recent:
        def set_recent_links(self, *_):
            pass

    links_business = SimpleNamespace(
        get_favorite_links=lambda: [],
        get_recent_links=lambda limit: [],  # noqa: ARG005
        clear_favorites=lambda: None,
    )

    ctrl = TopPanelsController(
        QObjectLike(), fav_widget=Fav(), recent_links_widget=Recent(), links_business=links_business
    )
    # Подменяем только структурный таймер
    ctrl._structure_refresh_timer = timer
    return ctrl


def test_schedule_structure_refresh_runtime_error_is_logged_and_not_raised(caplog):
    caplog.set_level(logging.ERROR)
    ctrl = make_ctrl_with_timer(RuntimeErrorTimer())
    # Не должно выбросить исключение
    ctrl.schedule_structure_refresh()
    assert any(
        "failed to start structure timer" in rec.getMessage() for rec in caplog.records
    )


def test_schedule_structure_refresh_unexpected_error_is_propagated(caplog):
    caplog.set_level(logging.ERROR)
    ctrl = make_ctrl_with_timer(KeyErrorTimer())
    with pytest.raises(KeyError):
        ctrl.schedule_structure_refresh()
    assert any(
        "unexpected error" in rec.getMessage() for rec in caplog.records
    )


def test_on_structure_changed_schedule_refresh_attribute_error_becomes_setup_error():
    class Stub:
        def schedule_structure_refresh(self):
            raise AttributeError("nope")
    with pytest.raises(SetupError):
        _on_structure_changed_schedule_refresh(Stub())


def test_on_structure_changed_schedule_refresh_unexpected_error_propagates():
    class Stub:
        def schedule_structure_refresh(self):
            raise KeyError("boom")
    with pytest.raises(KeyError):
        _on_structure_changed_schedule_refresh(Stub())
