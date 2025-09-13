import logging
from types import SimpleNamespace

import pytest

from app.controllers.system.window_controllers_setup import (
    SetupError,
    _connect_structure_signals,
)


class SignalMock:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        if not callable(slot):
            raise TypeError("slot must be callable")
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for s in list(self._slots):
            try:
                s(*args, **kwargs)
            except TypeError:
                # Позволяем слотам без параметров
                s()


class SpheresControllerMock:
    def __init__(self):
        self.update_calls = []

    def update_active_sphere_button(self, sphere_id=None):
        self.update_calls.append(sphere_id)


class TopPanelsControllerMock:
    def __init__(self):
        self.scheduled = 0
        self.refreshed = 0

    def schedule_structure_refresh(self):
        self.scheduled += 1

    def request_refresh(self):
        self.refreshed += 1


@pytest.fixture()
def window_stub():
    sb = SimpleNamespace(
        active_sphere_changed=SignalMock(),
        structure_loaded=SignalMock(),
        current_sphere_id=None,
        load_structure=lambda: None,
    )
    win = SimpleNamespace(
        structure_business=sb,
        spheres_controller=SpheresControllerMock(),
        structure=SimpleNamespace(
            # Подключается, но в этих тестах не используется
            item_changed=SignalMock(),
            item_added=SignalMock(),
        ),
        # Заглушка обработчика изменений структуры, ожидаемая _connect_structure_signals
        on_structure_item_changed=lambda *args, **kwargs: None,
        on_structure_item_added=lambda *args, **kwargs: None,
        top_panels_controller=TopPanelsControllerMock(),
        _structure_signals_connected=False,
        _update_left_panel_style=lambda *args, **kwargs: None,
    )
    return win


def test_connect_structure_signals_wires_active_sphere_and_schedules_refresh(
    window_stub, caplog
):
    caplog.set_level(logging.DEBUG)

    _connect_structure_signals(
        window_stub,
        top_panels_controller=window_stub.top_panels_controller,
        structure_business=window_stub.structure_business,
        structure=window_stub.structure,
        spheres_controller=window_stub.spheres_controller,
    )

    # Эмитим смену активной сферы
    window_stub.structure_business.active_sphere_changed.emit(5)

    # Проверяем, что визуальное состояние кнопки обновлено
    assert window_stub.spheres_controller.update_calls, (
        "update_active_sphere_button должен быть вызван"
    )
    assert window_stub.spheres_controller.update_calls[-1] in (5, None)

    # Проверяем, что запланировано единое обновление верхних панелей
    assert window_stub.top_panels_controller.scheduled == 1


def test_initial_button_state_set_if_current_sphere_known(window_stub):
    # Если текущая сфера известна до подключения сигналов — кнопка должна обновиться сразу
    window_stub.structure_business.current_sphere_id = 3

    _connect_structure_signals(
        window_stub,
        top_panels_controller=window_stub.top_panels_controller,
        structure_business=window_stub.structure_business,
        structure=window_stub.structure,
        spheres_controller=window_stub.spheres_controller,
    )

    # После подключения сигналов выполняется первичная установка состояния кнопок
    assert window_stub.spheres_controller.update_calls, (
        "Ожидался первичный апдейт активной кнопки"
    )
    assert window_stub.spheres_controller.update_calls[-1] in (3, None)


def test_connect_structure_signals_requires_top_panels_controller():
    # Без TopPanelsController должен быть поднят SetupError (как в коде)
    sb = SimpleNamespace(
        active_sphere_changed=SignalMock(), structure_loaded=SignalMock()
    )
    win = SimpleNamespace(
        structure_business=sb,
        spheres_controller=SpheresControllerMock(),
        structure=SimpleNamespace(item_changed=SignalMock(), item_added=SignalMock()),
        top_panels_controller=None,
        _update_left_panel_style=lambda *args, **kwargs: None,
    )

    with pytest.raises(SetupError):
        _connect_structure_signals(
            win,
            top_panels_controller=win.top_panels_controller,
            structure_business=win.structure_business,
            structure=win.structure,
            spheres_controller=win.spheres_controller,
        )
