import types

from app.controllers.ui.structure.icon_handling import IconHandling


class _DummyTree:
    def model(self):
        return None


class _DummyBusiness:
    pass


class _DummyController:
    def __init__(self):
        self.tree = _DummyTree()
        self.business = _DummyBusiness()


def test_icon_handling_close_resets_shared_executor(monkeypatch):
    # Ensure clean state
    try:
        IconHandling._shared_executor = None
    except Exception:
        pass

    ctrl = _DummyController()
    ih1 = IconHandling(ctrl)
    exec1 = getattr(IconHandling, "_shared_executor", None)
    assert exec1 is not None, "Executor must be created during first IconHandling init"

    # Closing should nullify shared executor
    ih1.close()
    assert getattr(IconHandling, "_shared_executor", None) is None

    # New instance should create a new executor (different object)
    ih2 = IconHandling(ctrl)
    exec2 = getattr(IconHandling, "_shared_executor", None)
    assert exec2 is not None and exec2 is not exec1

    # Cleanup
    ih2.close()
    assert getattr(IconHandling, "_shared_executor", None) is None


def test_icon_handling_close_is_idempotent():
    # Ensure clean state
    try:
        IconHandling._shared_executor = None
    except Exception:
        pass

    ctrl = _DummyController()
    ih = IconHandling(ctrl)
    # First close
    ih.close()
    # Second close should not raise and keep executor None
    ih.close()
    assert getattr(IconHandling, "_shared_executor", None) is None


def test_reload_icons_after_close_with_new_instance(monkeypatch):
    # Ensure clean state
    try:
        IconHandling._shared_executor = None
    except Exception:
        pass

    ctrl = _DummyController()
    ih1 = IconHandling(ctrl)
    ih1.close()

    # New instance should work and reload_icons should not raise
    ih2 = IconHandling(ctrl)
    ih2.reload_icons()  # with Dummy tree.model() -> None, should be a no-op
    ih2.close()
