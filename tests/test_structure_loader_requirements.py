import logging
import pytest
from types import SimpleNamespace

from app.controllers.system.window_controllers_setup import _connect_structure_signals, SetupError


class SignalMock:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        if not callable(slot):
            raise TypeError("slot must be callable")
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for s in list(self._slots):
            s(*args, **kwargs)


class SpheresControllerMock:
    def update_active_sphere_button(self, *_):
        pass


class TopPanelsControllerMock:
    def schedule_structure_refresh(self):
        pass


def test_missing_structure_loader_methods_raise_setup_error_on_wiring():
    # structure_business без load_structure_async и load_structure
    structure_business = SimpleNamespace(
        active_sphere_changed=SignalMock(),
        structure_loaded=SignalMock(),
        current_sphere_id=None,
    )

    window = SimpleNamespace(
        structure_business=structure_business,
        spheres_controller=SpheresControllerMock(),
        structure=SimpleNamespace(
            item_changed=SignalMock(),
            item_added=SignalMock(),
        ),
        top_panels_controller=TopPanelsControllerMock(),
        _update_left_panel_style=lambda *args, **kwargs: None,
        # обработчики, которые подключает _connect_structure_signals
        on_structure_item_changed=lambda *args, **kwargs: None,
        on_structure_item_added=lambda *args, **kwargs: None,
        _structure_signals_connected=False,
    )

    # Ожидаем явную ошибка настройки при проводке
    with pytest.raises(SetupError):
        _connect_structure_signals(
            window,
            top_panels_controller=window.top_panels_controller,
            structure_business=window.structure_business,
            structure=window.structure,
            spheres_controller=window.spheres_controller,
        )
