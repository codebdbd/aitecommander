from types import SimpleNamespace

import pytest

from app.controllers.system.window_controllers_setup import (
    DatabaseEventHandler,
    SetupError,
)


def test_raises_when_links_missing():
    window = SimpleNamespace(
        links_actions=SimpleNamespace(links=None),
    )
    with pytest.raises(SetupError):
        DatabaseEventHandler._update_controllers_with_new_db(
            window, SimpleNamespace(links=object())
        )


def test_raises_when_links_interface_invalid():
    class BadLinks:
        # нет атрибута db
        def __init__(self):
            self.links = object()

    window = SimpleNamespace(
        links_actions=SimpleNamespace(links=BadLinks()),
    )
    with pytest.raises(SetupError):
        DatabaseEventHandler._update_controllers_with_new_db(
            window, SimpleNamespace(links=object())
        )


def test_raises_when_structure_business_missing_signal():
    class SBNoSignal:
        def __init__(self):
            self.db = None
            # нет spheres_loaded
            self.get_current_sphere_id = lambda: None
            self.set_current_sphere = lambda _x: None

    window = SimpleNamespace(
        structure_business=SBNoSignal(),
    )
    with pytest.raises(SetupError):
        DatabaseEventHandler._update_controllers_with_new_db(window, SimpleNamespace())


def test_raises_when_structure_business_signal_invalid():
    class DummySignal:
        # нет методов connect/disconnect
        pass

    class SBInvalidSignal:
        def __init__(self):
            self.db = None
            self.spheres_loaded = DummySignal()
            self.get_current_sphere_id = lambda: None
            self.set_current_sphere = lambda _x: None

    window = SimpleNamespace(
        structure_business=SBInvalidSignal(),
    )
    with pytest.raises(SetupError):
        DatabaseEventHandler._update_controllers_with_new_db(window, SimpleNamespace())
