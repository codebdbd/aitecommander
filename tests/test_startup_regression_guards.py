from __future__ import annotations

from types import SimpleNamespace

import app.controllers.system.window_setup.coordinator as coordinator
import app.views.main_components.ui.topbar.top_bar_setup as top_bar_setup
from app.startup.initializer import ApplicationInitializer, StartupMode, application_context
from app.startup.runtime import _register_cleanup_handler


class _DummyWindow(SimpleNamespace):
    pass


class _DummyWindowInitializer:
    def __init__(self) -> None:
        self.window = _DummyWindow(top_panels_controller=None)
        self.db = object()


def test_window_controllers_setup_runs_public_setup_before_followup_steps(monkeypatch):
    calls: list[str] = []

    def fake_setup_controllers(window, controllers, db):
        calls.append("controllers")

    def fake_facade(self):
        calls.append("facade")

    def make_step(name):
        def _step(*args, **kwargs):
            calls.append(name)

        return _step

    monkeypatch.setattr(coordinator, "setup_controllers", fake_setup_controllers)
    monkeypatch.setattr(
        coordinator.WindowControllersSetup, "_init_window_facade", fake_facade
    )
    monkeypatch.setattr(coordinator, "setup_ui_elements", make_step("ui"))
    monkeypatch.setattr(
        coordinator, "setup_dependency_injection", make_step("dependency")
    )
    monkeypatch.setattr(coordinator, "setup_signal_connections", make_step("signals"))
    monkeypatch.setattr(coordinator, "setup_keyboard", make_step("keyboard"))

    setup = coordinator.WindowControllersSetup(_DummyWindowInitializer())
    setup.setup_controllers()

    assert calls == [
        "controllers",
        "facade",
        "ui",
        "dependency",
        "signals",
        "keyboard",
    ]


def test_initialize_spheres_uses_existing_controller(monkeypatch):
    class SpheresControllerStub:
        def __init__(self) -> None:
            self.init_calls: list[object] = []

        def init(self, startup_spheres=None):
            self.init_calls.append(startup_spheres)

    sc = SpheresControllerStub()
    window = _DummyWindow(spheres_controller=sc)
    setup = coordinator.WindowControllersSetup(
        SimpleNamespace(window=window, db=object())
    )

    setup.initialize_spheres()

    assert sc.init_calls == [None]


def test_initialize_spheres_creates_controller_when_missing(monkeypatch):
    created_with: list[object] = []

    class SpheresControllerStub:
        def __init__(self, window) -> None:
            created_with.append(window)
            self.init_calls: list[object] = []

        def init(self, startup_spheres=None):
            self.init_calls.append(startup_spheres)

    monkeypatch.setattr(
        "app.controllers.ui.structure.spheres_bar_controller.SpheresBarController",
        SpheresControllerStub,
    )

    window = _DummyWindow()
    setup = coordinator.WindowControllersSetup(
        SimpleNamespace(window=window, db=object())
    )

    setup.initialize_spheres()

    assert created_with == [window]
    assert isinstance(window.spheres_controller, SpheresControllerStub)
    assert window.spheres_controller.init_calls == [None]


def test_topbar_builder_prefills_before_manager(monkeypatch):
    class LayoutStub:
        def __init__(self):
            self.add_calls = []

        def addWidget(self, widget):
            self.add_calls.append(widget)

        def parentWidget(self):
            return None

    class WindowStub(SimpleNamespace):
        def centralWidget(self):
            return object()

    class FakeAction:
        def __init__(self, *_args, **_kwargs):
            self.visible = True

        def setVisible(self, value):
            self.visible = value

    class FakeToolBar:
        def __init__(self, *_args, **_kwargs):
            self.actions = []

        def setObjectName(self, *_args, **_kwargs):
            pass

        def setMovable(self, *_args, **_kwargs):
            pass

        def setFloatable(self, *_args, **_kwargs):
            pass

        def setToolButtonStyle(self, *_args, **_kwargs):
            pass

        def setIconSize(self, *_args, **_kwargs):
            pass

        def setSizePolicy(self, *_args, **_kwargs):
            pass

        def setFixedHeight(self, *_args, **_kwargs):
            pass

        def setContentsMargins(self, *_args, **_kwargs):
            pass

        def addSeparator(self):
            token = object()
            self.actions.append(token)
            return token

        def addAction(self, action):
            self.actions.append(action)

        def setStyleSheet(self, *_args, **_kwargs):
            pass

    class FakeHBoxLayout:
        def __init__(self):
            self.widgets = []

        def setContentsMargins(self, *_args, **_kwargs):
            pass

        def setSpacing(self, *_args, **_kwargs):
            pass

        def setAlignment(self, *_args, **_kwargs):
            pass

        def addWidget(self, widget):
            self.widgets.append(widget)

        def addSpacing(self, *_args, **_kwargs):
            pass

    class FakeSizePolicy:
        class Policy:
            Minimum = 0
            Fixed = 1

    class FakeQt:
        class AlignmentFlag:
            AlignVCenter = 0

        class ToolButtonStyle:
            ToolButtonIconOnly = 0

    class QuickAddStub:
        def __init__(self, *args, **kwargs):
            pass

    class LinksStub:
        def __init__(self, *args, **kwargs):
            pass

    class SeparatorControllerStub:
        def __init__(self, *args, **kwargs):
            pass

    class ConfigStub:
        @staticmethod
        def get_top_bar_widgets_side_spacing():
            return 8

        @staticmethod
        def get_top_panel_icon_size():
            return (16, 16)

        @staticmethod
        def get_top_bar_height():
            return 32

        @staticmethod
        def get_top_bar_buttons_spacing():
            return 4

        @staticmethod
        def get_top_panel_button_size():
            return 32

    host = object()
    layout = LayoutStub()
    window = WindowStub()
    prefill_called = {"value": False}

    ui = SimpleNamespace(
        window=window,
        main_layout=layout,
        _create_top_bar_host=lambda parent, top_bar: host,
        _create_vertical_separator=lambda: object(),
        setup_search_widget=lambda top_bar: None,
        _init_and_schedule_topbar_manager=lambda: None,
        _prefill_topbar_widgets_before_manager=lambda: prefill_called.__setitem__(
            "value", True
        ),
    )

    monkeypatch.setattr(top_bar_setup, "QAction", FakeAction)
    monkeypatch.setattr(top_bar_setup, "QToolBar", FakeToolBar)
    monkeypatch.setattr(top_bar_setup, "QHBoxLayout", FakeHBoxLayout)
    monkeypatch.setattr(top_bar_setup, "QSize", lambda w, h: (w, h))
    monkeypatch.setattr(top_bar_setup, "QSizePolicy", FakeSizePolicy)
    monkeypatch.setattr(top_bar_setup, "Qt", FakeQt)
    monkeypatch.setattr(top_bar_setup, "QuickAddToolbarAdapter", QuickAddStub)
    monkeypatch.setattr(top_bar_setup, "LinksToolbarAdapter", LinksStub)
    monkeypatch.setattr(
        top_bar_setup, "ToolbarSeparatorController", SeparatorControllerStub
    )
    monkeypatch.setattr(top_bar_setup.app_config, "ui", ConfigStub())

    builder = top_bar_setup.TopBarBuilder(ui)
    builder.build()

    assert prefill_called["value"] is True
    assert layout.add_calls == [host]
    assert window.top_bar_host is host


def test_cleanup_runs_even_when_shutdown_controller_exists(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)
    initializer._shutdown_controller = object()
    calls: list[str] = []

    def fake_cleanup_sync():
        calls.append("cleanup")
        initializer._cleanup_done = True

    monkeypatch.setattr(initializer, "_cleanup_sync", fake_cleanup_sync)

    assert initializer.cleanup(async_cleanup=False) is True
    assert calls == ["cleanup"]


def test_shutdown_controller_cleanup_marks_ownership_and_calls_sync(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)
    calls: list[str] = []

    def fake_cleanup_sync():
        calls.append("cleanup")
        initializer._cleanup_done = True

    monkeypatch.setattr(initializer, "_cleanup_sync", fake_cleanup_sync)

    assert initializer._cleanup_via_shutdown_controller(3000) is True
    assert initializer._shutdown_cleanup_started is True
    assert calls == ["cleanup"]


def test_shutdown_controller_cleanup_returns_false_when_cleanup_not_done(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)
    calls: list[str] = []

    def fake_cleanup_sync():
        calls.append("cleanup")

    monkeypatch.setattr(initializer, "_cleanup_sync", fake_cleanup_sync)

    assert initializer._cleanup_via_shutdown_controller(3000) is False
    assert initializer._shutdown_cleanup_started is False
    assert initializer._cleanup_done is False
    assert calls == ["cleanup"]


def test_application_context_finally_performs_cleanup_with_shutdown_controller(monkeypatch):
    calls: list[str] = []

    def fake_initialize_all(self):
        self._shutdown_controller = object()
        return True

    def fake_cleanup_sync(self):
        calls.append("cleanup")
        self._cleanup_done = True

    monkeypatch.setattr(ApplicationInitializer, "initialize_all", fake_initialize_all)
    monkeypatch.setattr(ApplicationInitializer, "_cleanup_sync", fake_cleanup_sync)

    with application_context(mode=StartupMode.HEADLESS):
        pass

    assert calls == ["cleanup"]


def test_failed_shutdown_controller_cleanup_allows_followup_direct_cleanup(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)
    calls: list[str] = []

    def fake_cleanup_sync():
        calls.append("cleanup")
        if len(calls) == 1:
            return
        initializer._cleanup_done = True

    monkeypatch.setattr(initializer, "_cleanup_sync", fake_cleanup_sync)

    assert initializer._cleanup_via_shutdown_controller(3000) is False
    assert initializer._shutdown_cleanup_started is False
    assert initializer._cleanup_done is False

    assert initializer.cleanup(async_cleanup=False) is True
    assert initializer._cleanup_done is True
    assert calls == ["cleanup", "cleanup"]


def test_about_to_quit_handler_invokes_initializer_cleanup(monkeypatch):
    calls: list[str] = []

    class _Signal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def disconnect(self, callback=None):
            if callback is None:
                self._callbacks.clear()
                return
            self._callbacks = [cb for cb in self._callbacks if cb is not callback]

        def emit(self):
            for callback in list(self._callbacks):
                callback()

    class _App:
        def __init__(self) -> None:
            self.aboutToQuit = _Signal()

    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)

    def fake_cleanup(async_cleanup: bool = False, timeout: float = 5.0):
        calls.append(f"cleanup:{async_cleanup}")
        return True

    monkeypatch.setattr(initializer, "cleanup", fake_cleanup)

    app = _App()
    assert _register_cleanup_handler(app, initializer) is True

    app.aboutToQuit.emit()

    assert calls == ["cleanup:False"]
    assert hasattr(app, "_about_to_quit_cleanup")


def test_cleanup_failure_does_not_mark_done_and_reports_failure(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)

    def fail_cleanup():
        raise RuntimeError("cleanup resource failure")

    monkeypatch.setattr(initializer._resource_manager, "cleanup_all", fail_cleanup)

    assert initializer.cleanup(async_cleanup=False) is False
    assert initializer._cleanup_done is False
    assert initializer._cleanup_failed is True
    assert initializer._last_cleanup_error == "cleanup resource failure"


def test_cleanup_can_retry_after_partial_failure(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)
    calls: list[str] = []

    def flaky_cleanup():
        calls.append("cleanup")
        if len(calls) == 1:
            raise RuntimeError("first cleanup failed")

    monkeypatch.setattr(initializer._resource_manager, "cleanup_all", flaky_cleanup)

    assert initializer.cleanup(async_cleanup=False) is False
    assert initializer._cleanup_done is False
    assert initializer._cleanup_failed is True

    assert initializer.cleanup(async_cleanup=False) is True
    assert initializer._cleanup_done is True
    assert initializer._cleanup_failed is False
    assert initializer._last_cleanup_error is None
    assert calls == ["cleanup", "cleanup"]


def test_get_status_reports_cleanup_failure_state(monkeypatch):
    initializer = ApplicationInitializer(mode=StartupMode.HEADLESS)

    def fail_cleanup():
        raise RuntimeError("status cleanup failed")

    monkeypatch.setattr(initializer._resource_manager, "cleanup_all", fail_cleanup)

    assert initializer.cleanup(async_cleanup=False) is False

    status = initializer.get_status()
    assert status["cleanup_done"] is False
    assert status["cleanup_in_progress"] is False
    assert status["cleanup_failed"] is True
    assert status["last_cleanup_error"] == "status cleanup failed"
