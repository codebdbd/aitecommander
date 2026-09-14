from __future__ import annotations

from unittest.mock import patch

import pytest

from app.utils.ui.qt.gui_exec import (
    run_in_gui_thread_sync,
)


def test_run_in_gui_thread_sync_direct_when_no_app() -> None:
    with patch("app.utils.ui.qt.gui_exec.QApplication.instance", return_value=None):
        with patch("app.utils.ui.qt.gui_exec.is_gui_thread", return_value=False):
            result = run_in_gui_thread_sync(lambda: 42)
            assert result == 42


def test_run_in_gui_thread_sync_direct_when_in_gui_thread() -> None:
    with patch("app.utils.ui.qt.gui_exec.is_gui_thread", return_value=True):
        result = run_in_gui_thread_sync(lambda: "hello")
        assert result == "hello"


def test_run_in_gui_thread_sync_timeout_raises_error() -> None:
    mock_app = object()
    with patch("app.utils.ui.qt.gui_exec.is_gui_thread", return_value=False), \
         patch("app.utils.ui.qt.gui_exec.QApplication.instance", return_value=mock_app), \
         patch("app.utils.ui.qt.gui_exec.QTimer.singleShot"):  # does nothing, simulates locked/busy GUI
        with pytest.raises(TimeoutError, match="Timed out waiting for GUI thread"):
            run_in_gui_thread_sync(lambda: 123, timeout=0.05)


def test_run_in_gui_thread_sync_propagates_exception() -> None:
    mock_app = object()

    def dummy_single_shot(delay, callback):
        callback()

    with patch("app.utils.ui.qt.gui_exec.is_gui_thread", return_value=False), \
         patch("app.utils.ui.qt.gui_exec.QApplication.instance", return_value=mock_app), \
         patch("app.utils.ui.qt.gui_exec.QTimer.singleShot", side_effect=dummy_single_shot):
        def _failing():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_in_gui_thread_sync(_failing, timeout=1.0)
