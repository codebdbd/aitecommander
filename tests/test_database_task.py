from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.utils.db.tasks.base import DatabaseTask


def test_task_executes_simple_callable_once() -> None:
    calls = 0

    def my_func():
        nonlocal calls
        calls += 1
        return 'success'

    task = DatabaseTask(my_func)
    finished_mock = MagicMock()
    error_mock = MagicMock()
    task.signals.finished.connect(finished_mock)
    task.signals.error.connect(error_mock)

    task.run()

    assert calls == 1
    finished_mock.assert_called_once_with('success')
    error_mock.assert_not_called()


def test_task_passes_progress_reporter_when_supported() -> None:
    calls = 0
    passed_reporter = None

    def my_func(reporter):
        nonlocal calls, passed_reporter
        calls += 1
        passed_reporter = reporter
        reporter(50)
        return 'done'

    task = DatabaseTask(my_func)
    progress_mock = MagicMock()
    finished_mock = MagicMock()
    task.signals.progress.connect(progress_mock)
    task.signals.finished.connect(finished_mock)

    task.run()

    assert calls == 1
    assert callable(passed_reporter)
    progress_mock.assert_called_once_with(50)
    finished_mock.assert_called_once_with('done')


def test_value_error_inside_task_does_not_trigger_reexecution() -> None:
    calls = 0

    def fail_with_value_error():
        nonlocal calls
        calls += 1
        raise ValueError('Invalid user argument or state')

    task = DatabaseTask(fail_with_value_error)
    finished_mock = MagicMock()
    error_mock = MagicMock()
    task.signals.finished.connect(finished_mock)
    task.signals.error.connect(error_mock)

    task.run()

    # AUD-029: Must be called EXACTLY ONCE, not retried without arguments
    assert calls == 1
    finished_mock.assert_not_called()
    error_mock.assert_called_once()
    exc = error_mock.call_args[0][0]
    assert isinstance(exc, ValueError)
    assert 'Invalid user argument or state' in str(exc)


def test_signature_value_error_falls_back_to_no_args_call() -> None:
    calls = 0

    def c_like_func():
        nonlocal calls
        calls += 1
        return 42

    task = DatabaseTask(c_like_func)
    finished_mock = MagicMock()
    error_mock = MagicMock()
    task.signals.finished.connect(finished_mock)
    task.signals.error.connect(error_mock)

    with patch('inspect.signature', side_effect=ValueError('no signature')):
        task.run()

    assert calls == 1
    finished_mock.assert_called_once_with(42)
    error_mock.assert_not_called()
