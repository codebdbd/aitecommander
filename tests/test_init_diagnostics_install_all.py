import logging
import pytest

from PyQt6.QtCore import QObject

from app.views.main_components.init_diagnostics import DiagnosticsInstaller


class DummyWindow(QObject):
    pass


class DummyInstaller(DiagnosticsInstaller):
    def __init__(self, window, fail_steps=None):
        super().__init__(window)
        self.fail_steps = set(fail_steps or [])
        self.calls = []

    def _maybe_fail(self, name):
        self.calls.append(name)
        if name in self.fail_steps:
            raise RuntimeError(f"boom in {name}")

    def _install_qt_message_filter(self) -> None:
        self._maybe_fail("_install_qt_message_filter")

    def _install_top_level_watcher(self) -> None:
        self._maybe_fail("_install_top_level_watcher")

    def _install_window_resize_logger(self) -> None:
        # Uses QObject checks; since DummyWindow is QObject, it's fine
        self._maybe_fail("_install_window_resize_logger")

    # Widget show hooks have been removed from install_all; keeping method here
    # to avoid AttributeError in case of legacy references, but it's not called.
    def _install_widget_show_hooks(self) -> None:
        self._maybe_fail("_install_widget_show_hooks")


@pytest.mark.parametrize(
    "failing_step, expected_called",
    [
        ("_install_qt_message_filter", [
            "_install_qt_message_filter",
            "_install_top_level_watcher",
            "_install_window_resize_logger",
        ]),
        ("_install_top_level_watcher", [
            "_install_qt_message_filter",
            "_install_top_level_watcher",
            "_install_window_resize_logger",
        ]),
        ("_install_window_resize_logger", [
            "_install_qt_message_filter",
            "_install_top_level_watcher",
            "_install_window_resize_logger",
        ]),
    ],
)
def test_install_all_isolates_errors_and_continues(caplog, failing_step, expected_called):
    caplog.set_level(logging.WARNING)
    inst = DummyInstaller(DummyWindow(), fail_steps={failing_step})

    inst.install_all()

    # All steps should be attempted in order, even if one fails
    assert inst.calls == expected_called

    # A warning must be logged for the failed step
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert f"DiagnosticsInstaller: {failing_step} failed" in msgs


def test_install_all_logs_multiple_failures(caplog):
    caplog.set_level(logging.WARNING)
    failing = {"_install_qt_message_filter", "_install_window_resize_logger"}
    inst = DummyInstaller(DummyWindow(), fail_steps=failing)

    inst.install_all()

    msgs = "\n".join(r.getMessage() for r in caplog.records)
    # Both failures should be logged
    assert "DiagnosticsInstaller: _install_qt_message_filter failed" in msgs
    assert "DiagnosticsInstaller: _install_window_resize_logger failed" in msgs

    # All steps still attempted
    assert inst.calls == [
        "_install_qt_message_filter",
        "_install_top_level_watcher",
        "_install_window_resize_logger",
    ]
