import sys

import pytest

from app.controllers.system import db_init
from app.startup.initializer import StartupMode
from app.startup.runtime import ExitCode, StartupOptions, run


@pytest.mark.qt_no_exception_capture
def test_headless_runtime_quick_exit(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["test_app"])
    monkeypatch.setattr(
        db_init.DatabaseInitializer,
        "initialize_async",
        lambda self, *args, **kwargs: None,
    )

    options = StartupOptions(mode=StartupMode.HEADLESS, auto_quit=True, quit_after_ms=0)
    exit_code = run(options)

    assert exit_code == ExitCode.SUCCESS
