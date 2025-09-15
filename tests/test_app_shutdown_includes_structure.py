from app.controllers.system.app_shutdown_controller import AppShutdownController


class _DummyStructure:
    def __init__(self):
        self.closed = False

    def shutdown(self):
        self.closed = True


class _DummyWindow:
    def __init__(self):
        # Other controllers may be absent; only structure is required for this test
        self.structure = _DummyStructure()


def test_shutdown_controllers_calls_structure_shutdown():
    win = _DummyWindow()
    ctrl = AppShutdownController(win)

    # Directly invoke controllers shutdown stage
    ctrl._shutdown_controllers()

    assert win.structure.closed is True
