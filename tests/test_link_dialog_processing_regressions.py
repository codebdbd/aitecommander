from __future__ import annotations

from types import SimpleNamespace

import app.views.windows.dialogs.link_dialog.handlers_mixins.link_processing_mixin as link_processing_mixin
from app.views.windows.dialogs.link_dialog.link_dialog_handlers import LinkDialogHandlers


class _LineEditStub:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def text(self) -> str:
        return self._value


class _SignalStub:
    def disconnect(self) -> None:
        return None


class _WorkerSignalsStub:
    def __init__(self) -> None:
        self.finished = _SignalStub()
        self.error = _SignalStub()


class _WorkerHandleStub:
    def __init__(self) -> None:
        self.signals = _WorkerSignalsStub()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _TimerStub:
    def stop(self) -> None:
        return None


class _DialogStub:
    def __init__(self) -> None:
        self.link_type = "file"
        self.link = {}
        self._is_closing = False
        self._processing_timer = _TimerStub()
        self.ui = SimpleNamespace(set_widget_value=lambda *_args, **_kwargs: None)
        self._args_le = _LineEditStub("")
        self._url_le = _LineEditStub("")
        self._name_le = _LineEditStub("")
        self.error_calls: list[dict[str, str]] = []

    def _get_args_le(self) -> _LineEditStub:
        return self._args_le

    def _get_url_le(self) -> _LineEditStub:
        return self._url_le

    def _get_name_le(self) -> _LineEditStub:
        return self._name_le

    def show_error(self, message: str, title: str, **kwargs) -> None:
        self.error_calls.append(
            {
                "message": message,
                "title": title,
                "details": kwargs.get("details", ""),
            }
        )

    def tr(self, text: str) -> str:
        return text


def test_same_path_can_retry_after_processing_error(monkeypatch):
    calls: list[str] = []
    handles: list[_WorkerHandleStub] = []

    def fake_run_db(*_args, **_kwargs):
        calls.append("run_db")
        handle = _WorkerHandleStub()
        handles.append(handle)
        return handle

    monkeypatch.setattr(link_processing_mixin, "run_db", fake_run_db)

    handlers = LinkDialogHandlers(_DialogStub())

    handlers.trigger_link_processing("https://example.com")
    assert calls == ["run_db"]
    assert handlers._last_processed_path == "https://example.com"

    handlers._on_link_info_error("network failed")

    assert handlers._last_processed_path == ""
    assert handlers._is_processing is False
    assert handlers._active_worker is None

    handlers.trigger_link_processing("https://example.com")

    assert calls == ["run_db", "run_db"]
    assert len(handles) == 2


def test_cancel_processing_clears_last_processed_path_and_processing_state():
    handlers = LinkDialogHandlers(_DialogStub())
    worker = _WorkerHandleStub()

    handlers._is_processing = True
    handlers._last_processed_path = "https://example.com"
    handlers._active_worker = worker

    handlers.cancel_processing()

    assert handlers._is_processing is False
    assert handlers._last_processed_path == ""
    assert handlers._active_worker is None
    assert worker.cancelled is True


def test_cancel_processing_ignores_late_link_info_signal(monkeypatch):
    handlers = LinkDialogHandlers(_DialogStub())
    calls: list[dict] = []

    monkeypatch.setattr(
        handlers,
        "_on_link_info_fetched",
        lambda info: calls.append(info),
    )

    handlers.cancel_processing()
    handlers.signals.link_info_finished.emit({"title": "late"})

    assert calls == []
