import importlib
import os



def reload_ls():
    from app.startup import logging_setup as ls

    importlib.reload(ls)
    return ls


def test_setup_logging_env_level_invalid_logs_warning(monkeypatch, caplog):
    ls = reload_ls()

    # Stub out global reconfiguration side effects
    class DummyAL:
        def __init__(self, *_a, **_k):
            pass

    class DummyEH:
        def __init__(self, *_a, **_k):
            pass

    monkeypatch.setattr(ls, "ApplicationLogger", DummyAL)
    monkeypatch.setattr(ls, "ExceptionHandler", DummyEH)

    # Simulate invalid env variable by making os.getenv raise
    def bad_getenv(key, default=None):
        raise OSError("env fail")

    monkeypatch.setattr(os, "getenv", bad_getenv)

    caplog.set_level("WARNING")
    ls.setup_logging(log_level=10)
    assert any("APP_LOG_LEVEL read failed" in rec.message for rec in caplog.records)


def test_setup_logging_noisy_loggers_adjust_failure_logs_warning(monkeypatch, caplog):
    ls = reload_ls()

    # Stub out global reconfiguration side effects
    class DummyAL:
        def __init__(self, *_a, **_k):
            pass

    class DummyEH:
        def __init__(self, *_a, **_k):
            pass

    monkeypatch.setattr(ls, "ApplicationLogger", DummyAL)
    monkeypatch.setattr(ls, "ExceptionHandler", DummyEH)

    # Patch Logger.setLevel so that only specific noisy loggers raise
    orig_set_level = ls.logging.Logger.setLevel

    def bad_set_level(self, level):
        if getattr(self, "name", "") in ("asyncio", "urllib3", "PIL"):
            raise RuntimeError("set level fail")
        return orig_set_level(self, level)

    monkeypatch.setattr(ls.logging.Logger, "setLevel", bad_set_level, raising=False)

    caplog.set_level("WARNING")
    ls.setup_logging(log_level=20)
    assert any("failed to adjust noisy loggers" in rec.message for rec in caplog.records)


def test_log_system_info_handles_log_level_check_failure(monkeypatch, caplog):
    ls = reload_ls()

    # Use a temporary module logger to avoid touching shared logger instance
    import logging
    temp_logger = logging.getLogger("test_logging_setup.temp")
    monkeypatch.setattr(ls, "logger", temp_logger)
    # Make only isEnabledFor raise on this temp logger
    monkeypatch.setattr(ls.logger, "isEnabledFor", lambda *_: (_ for _ in ()).throw(AttributeError("no attr")), raising=False)

    captured_msgs = []

    def fake_warning(msg, *args, **kwargs):
        captured_msgs.append(str(msg))

    # Stub warning to avoid it calling isEnabledFor again
    monkeypatch.setattr(ls.logger, "warning", fake_warning, raising=False)

    ls.log_system_info()
    assert any("Failed to check log level" in m for m in captured_msgs)
