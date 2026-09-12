from __future__ import annotations

import pytest

from app.core.worker_manager import Worker


def test_worker_run_success_emits_result_and_finished() -> None:
    events = []

    worker = Worker(lambda x: x * 2, (21,), {})
    worker.signals.result.connect(lambda res: events.append(("result", res)))
    worker.signals.error.connect(lambda err: events.append(("error", err)))
    worker.signals.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert ("result", 42) in events
    assert ("finished", None) in events
    assert not any(ev[0] == "error" for ev in events)


def test_worker_run_error_emits_error_and_finished() -> None:
    events = []

    def _failing():
        raise RuntimeError("test failure")

    worker = Worker(_failing, (), {})
    worker.signals.result.connect(lambda res: events.append(("result", res)))
    worker.signals.error.connect(lambda err: events.append(("error", err)))
    worker.signals.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert any(ev[0] == "error" for ev in events)
    assert ("finished", None) in events
    assert not any(ev[0] == "result" for ev in events)
