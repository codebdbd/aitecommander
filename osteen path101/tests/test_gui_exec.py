# test_gui_exec.py
from __future__ import annotations

import threading

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except Exception:  # pragma: no cover - if PyQt6 not installed, test will be skipped
    QApplication = None  # type: ignore

from app.utils.ui.qt.gui_exec import is_gui_thread


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is not available")
def test_is_gui_thread_main_and_worker_threads():
    # Ensure QApplication exists
    _app = QApplication.instance() or QApplication([])

    # Main thread should be GUI thread
    assert is_gui_thread() is True

    # Worker thread should NOT be GUI thread
    result = []

    def worker():
        result.append(is_gui_thread())

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert result and result[0] is False

    # Avoid exiting without cleaning app if we created it
    # Note: do not call app.quit() to not affect other tests; letting gc handle is fine.
