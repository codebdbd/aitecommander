import importlib


def test_suspend_updates_logs_error_on_restore_failure(caplog, monkeypatch):
    # Reload module to ensure clean logger
    from app.utils.ui import updates

    importlib.reload(updates)

    class Dummy:
        def __init__(self):
            self.calls = []

        def setUpdatesEnabled(self, enabled: bool):  # noqa: N802 - Qt-style API
            self.calls.append(enabled)
            if enabled is True:
                raise RuntimeError("boom")

    dummy = Dummy()

    caplog.set_level("ERROR")
    with updates.suspend_updates(dummy):
        pass

    # Expect two calls: False on enter, True on exit (failing)
    assert dummy.calls == [False, True]

    assert any(
        "Failed to restore updates via setUpdatesEnabled(True)" in rec.message
        for rec in caplog.records
    )
