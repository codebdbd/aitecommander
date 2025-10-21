from app.startup import signal_handling


def test_should_install_signal_handlers_handles_none_streams(monkeypatch):
    # Simulate frozen/console-less environment: stdin/stdout may be None.
    monkeypatch.setattr(signal_handling.sys, "stdin", None, raising=False)
    monkeypatch.setattr(signal_handling.sys, "stdout", None, raising=False)
    monkeypatch.setattr(signal_handling.platform, "system", lambda: "Windows")

    assert signal_handling.should_install_signal_handlers() is True
