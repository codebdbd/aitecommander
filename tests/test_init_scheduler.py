from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from app.views.main_components.initialization.init_scheduler import AsyncStepRunner


class DummyMetrics:
    @contextmanager
    def time_span(self, name: str):
        yield


_qapp_instance = None


def _get_qapp():
    global _qapp_instance
    if _qapp_instance is None:
        _qapp_instance = QApplication.instance() or QApplication([])
    return _qapp_instance


def test_async_step_runner_executes_steps() -> None:
    qapp = _get_qapp()
    metrics = DummyMetrics()
    status_messages = []
    executed_steps = []

    runner = AsyncStepRunner(
        metrics=metrics,
        set_status_message=lambda msg: status_messages.append(msg),
    )

    def step1():
        executed_steps.append("step1")

    def step2():
        executed_steps.append("step2")

    steps = [
        ("Step 1", step1),
        ("Step 2", step2),
    ]

    cell = [0]
    completed_cell = [False]

    runner.run(
        steps=steps,
        index_getter=lambda: cell[0],
        index_setter=lambda v: cell.__setitem__(0, v),
        on_completed=lambda: completed_cell.__setitem__(0, True),
    )

    # Process events to let QTimer.singleShot fire
    for _ in range(10):
        qapp.processEvents()

    assert completed_cell[0] is True
    assert "step1" in executed_steps
    assert "step2" in executed_steps
    assert "Step 1" in status_messages
    assert "Step 2" in status_messages


def test_async_step_runner_stops_when_app_closing_down() -> None:
    _get_qapp()
    metrics = DummyMetrics()
    runner = AsyncStepRunner(
        metrics=metrics,
        set_status_message=lambda msg: None,
    )

    executed = []
    steps = [("Step 1", lambda: executed.append(1))]
    idx = [0]
    completed = [False]

    with patch("app.views.main_components.initialization.init_scheduler.QCoreApplication.instance") as mock_instance:
        mock_app = MagicMock()
        mock_app.closingDown.return_value = True
        mock_instance.return_value = mock_app

        runner._execute_next(
            steps=steps,
            index_getter=lambda: idx[0],
            index_setter=lambda v: idx.__setitem__(0, v),
            on_completed=lambda: completed.__setitem__(0, True),
            on_error=None,
            special_hooks=None,
        )

    # Should not execute step when closing down
    assert len(executed) == 0
    assert completed[0] is False


def test_async_step_runner_handles_error() -> None:
    _get_qapp()
    metrics = DummyMetrics()
    runner = AsyncStepRunner(
        metrics=metrics,
        set_status_message=lambda msg: None,
    )

    def failing_step():
        raise RuntimeError("Initialization failure")

    errors = []
    idx = [0]
    completed = [False]
    steps = [("Failing Step", failing_step)]

    runner._execute_next(
        steps=steps,
        index_getter=lambda: idx[0],
        index_setter=lambda v: idx.__setitem__(0, v),
        on_completed=lambda: completed.__setitem__(0, True),
        on_error=lambda e: errors.append(e),
        special_hooks=None,
    )

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert completed[0] is False


def test_async_step_runner_stops_when_bound_window_is_deleted() -> None:
    _get_qapp()
    metrics = DummyMetrics()
    runner = AsyncStepRunner(
        metrics=metrics,
        set_status_message=lambda msg: None,
    )

    class Owner:
        def __init__(self):
            self.window = object()
            self.executed = False

        def step(self):
            self.executed = True

    owner = Owner()
    idx = [0]
    completed = [False]

    with patch(
        "app.views.main_components.initialization.init_scheduler._is_qobject_deleted",
        side_effect=lambda obj: obj is owner.window,
    ):
        runner._execute_next(
            steps=[("Deleted window step", owner.step)],
            index_getter=lambda: idx[0],
            index_setter=lambda v: idx.__setitem__(0, v),
            on_completed=lambda: completed.__setitem__(0, True),
            on_error=None,
            special_hooks=None,
        )

    assert owner.executed is False
    assert idx[0] == 0
    assert completed[0] is False
