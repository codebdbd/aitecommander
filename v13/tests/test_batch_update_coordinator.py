from __future__ import annotations

from app.controllers.structure_modules.batch_manager import BatchUpdateCoordinator


def test_batch_update_coordinator_flows_callbacks_are_called(monkeypatch):
    calls = {"load": [], "invalidate": 0, "reload": []}

    def on_load_categories(sid: int):
        calls["load"].append(sid)

    def on_invalidate():
        calls["invalidate"] += 1

    def on_schedule_reload(delay: int):
        calls["reload"].append(delay)

    bm = BatchUpdateCoordinator(
        on_load_categories=on_load_categories,
        on_invalidate=on_invalidate,
        on_schedule_reload=on_schedule_reload,
    )

    bm.begin()
    assert bm.in_batch is True
    bm.touch_section(1)
    bm.touch_section(2)
    bm.touch_section(None)  # ignored
    bm.end()

    # Load once per touched section
    assert sorted(calls["load"]) == [1, 2]
    # One invalidate and one consolidated reload
    assert calls["invalidate"] == 1
    assert calls["reload"] == [0]
