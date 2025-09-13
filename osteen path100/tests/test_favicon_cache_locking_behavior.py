import builtins
import types
import sys
from contextlib import contextmanager

import pytest


def _reload_module():
    import importlib
    from app.utils.links.parser import favicon_cache as fc
    return importlib.reload(fc)


def test_portalocker_timeout_logs_warning(monkeypatch, caplog, tmp_path):
    fc = _reload_module()

    # Force backend to portalocker
    monkeypatch.setattr(fc, "_get_lock_backend", lambda: "portalocker")

    # Create fake portalocker with Lock that raises LockException
    class LockException(Exception):
        pass

    class FakePortalocker:
        exceptions = types.SimpleNamespace(LockException=LockException)

        def __init__(self):
            pass

        class Lock:
            def __init__(self, *_a, **_k):
                pass

            def __enter__(self):
                raise LockException("timeout")

            def __exit__(self, exc_type, exc, tb):
                return False

    # Ensure import portalocker returns our fake
    monkeypatch.setitem(sys.modules, "portalocker", FakePortalocker())

    lock_path = str(tmp_path / "db.lock")
    caplog.set_level("WARNING")
    with fc._file_lock(lock_path, timeout=0.01):
        pass

    assert any("favicon lock timeout:" in rec.message for rec in caplog.records)


def test_filelock_timeout_logs_warning(monkeypatch, caplog, tmp_path):
    fc = _reload_module()

    # Force backend to filelock
    monkeypatch.setattr(fc, "_get_lock_backend", lambda: "filelock")

    # Fake filelock with Timeout
    class FileLockTimeout(Exception):
        pass

    class FakeFileLock:
        def __init__(self, *_a, **_k):
            pass

        def acquire(self, *_, **__):
            raise FileLockTimeout("timeout")

        def release(self):
            pass

    fake_module = types.SimpleNamespace(FileLock=FakeFileLock, Timeout=FileLockTimeout)
    monkeypatch.setitem(sys.modules, "filelock", fake_module)

    lock_path = str(tmp_path / "db.lock")
    caplog.set_level("WARNING")
    with fc._file_lock(lock_path, timeout=0.01):
        pass

    assert any("favicon lock timeout(filelock):" in rec.message for rec in caplog.records)


def test_no_backend_available_logs_warning_and_proceeds(monkeypatch, caplog, tmp_path):
    fc = _reload_module()

    # Force portalocker only, but make import fail by removing module
    monkeypatch.setattr(fc, "_get_lock_backend", lambda: "portalocker")
    # Ensure portalocker import fails even if installed: monkeypatch __import__
    real_import = __import__

    def fake_import(name, *a, **k):  # type: ignore
        if name == "portalocker" or name.startswith("portalocker."):
            raise ImportError("simulated missing portalocker")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", fake_import)

    lock_path = str(tmp_path / "db.lock")
    caplog.set_level("WARNING")
    with fc._file_lock(lock_path, timeout=0.01):
        pass

    assert any(
        "favicon lock backend unavailable" in rec.message for rec in caplog.records
    )
