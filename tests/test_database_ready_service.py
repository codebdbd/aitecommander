from __future__ import annotations

from PyQt6.QtCore import QSignalSpy
from PyQt6.QtWidgets import QApplication

from app.startup.database_ready_service import DatabaseReadyService


def test_database_ready_service_emits_ready_only_once() -> None:
    app = QApplication.instance() or QApplication([])
    service = DatabaseReadyService(parent=app)
    spy = QSignalSpy(service.ready)

    service.mark_ready()
    service.mark_ready()

    assert len(spy) == 1
    assert service.is_ready


def test_database_ready_service_emits_failed_once() -> None:
    app = QApplication.instance() or QApplication([])
    service = DatabaseReadyService(parent=app)
    spy = QSignalSpy(service.failed)
    error = RuntimeError("db init failed")

    service.mark_failed(error)
    service.mark_failed(RuntimeError("second failure"))

    assert len(spy) == 1
    assert service.error is error
