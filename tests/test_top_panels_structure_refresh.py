import types
import pytest

from app.controllers.system.window_controllers_setup import (
    _connect_structure_signals,
    SetupError,
)


class DummySignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        if not callable(slot):
            raise TypeError("slot must be callable")
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for s in list(self._slots):
            s(*args, **kwargs)


class DummyTopPanelsController:
    def __init__(self):
        self.scheduled = 0
        self.requested = 0
        self.fail = False

    def schedule_structure_refresh(self):
        if self.fail:
            raise RuntimeError("scheduler boom")
        self.scheduled += 1

    def request_refresh(self):
        # Если вдруг будет вызван fallback — тест должен упасть
        self.requested += 1
        raise AssertionError("request_refresh must not be called by structure change handler")


class DummySpheresController:
    def update_active_sphere_button(self, *_):
        pass


class DummyStructureBusiness:
    def __init__(self):
        self.active_sphere_changed = DummySignal()
        self.structure_loaded = DummySignal()

    # Заглушки API, чтобы _connect_structure_signals не падал на обертках
    def load_structure(self):
        pass


class DummyStructure:
    def __init__(self):
        self.item_changed = DummySignal()
        self.item_added = DummySignal()


class DummyWindow:
    def __init__(self):
        self.structure_business = DummyStructureBusiness()
        self.spheres_controller = DummySpheresController()
        self._update_left_panel_style = lambda *args, **kwargs: None
        self.top_panels_controller = DummyTopPanelsController()
        self.structure = DummyStructure()

    # Хэндлеры, на которые производится подключение
    def on_structure_item_changed(self, *args, **kwargs):
        pass

    def on_structure_item_added(self, *args, **kwargs):
        pass


def test_schedule_only_called_on_structure_events():
    window = DummyWindow()
    _connect_structure_signals(window)

    # Эмитим события структуры
    window.structure_business.active_sphere_changed.emit()
    window.structure_business.structure_loaded.emit()

    assert window.top_panels_controller.scheduled == 2
    # Убедимся, что fallback не вызывался
    assert window.top_panels_controller.requested == 0


def test_setup_error_raised_when_scheduler_fails():
    window = DummyWindow()
    window.top_panels_controller.fail = True
    _connect_structure_signals(window)

    with pytest.raises(SetupError):
        window.structure_business.active_sphere_changed.emit()
