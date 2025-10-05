"""Regression tests for business logic thread safety and shutdown."""

from __future__ import annotations

import logging
import threading
from typing import Any, Tuple
from unittest.mock import MagicMock

import pytest

from PyQt6.QtCore import QTimer

from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.business.structure_business import StructureBusinessLogic
from app.models import Database


@pytest.fixture
def mock_db() -> MagicMock:
    """Provide a database stub."""
    db = MagicMock(spec=Database)
    db.links = MagicMock()
    db.links.get_link_by_id = MagicMock(return_value={"id": 1, "is_favorite": False})
    db.links.create_or_update_link = MagicMock(return_value=1)
    return db


@pytest.fixture
def mock_scheduler() -> MagicMock:
    """Provide a scheduler stub with a thread pool."""
    scheduler = MagicMock()
    pool = MagicMock()
    pool.activeThreadCount.return_value = 0
    scheduler.get_thread_pool.return_value = pool
    return scheduler


def test_links_business_uses_reentrant_lock(mock_db: MagicMock, mock_scheduler: MagicMock) -> None:
    """Ensure `LinksBusinessLogic` guards mutations with `threading.RLock`."""
    logic = LinksBusinessLogic(db=mock_db, scheduler=mock_scheduler)
    assert isinstance(logic._mutex, threading.RLock)  # type: ignore[attr-defined]

    # Validate reentrancy: acquiring twice should not deadlock and release twice.
    logic._mutex.acquire()  # type: ignore[attr-defined]
    logic._mutex.acquire()  # type: ignore[attr-defined]
    logic._mutex.release()  # type: ignore[attr-defined]
    logic._mutex.release()  # type: ignore[attr-defined]


@pytest.fixture
def structure_logic(monkeypatch: pytest.MonkeyPatch) -> Tuple[StructureBusinessLogic, MagicMock]:
    """Instantiate `StructureBusinessLogic` with lightweight dependencies."""
    db = MagicMock(spec=Database)

    mock_structure_model = MagicMock()
    mock_structure_service = MagicMock()
    mock_export_service = MagicMock()
    mock_integrity_service = MagicMock()
    mock_loader_service = MagicMock()
    mock_selection_service = MagicMock()
    mock_validation_service = MagicMock()
    mock_import_service = MagicMock()
    mock_utility_service = MagicMock()

    async_operations = MagicMock()
    async_operations.shutdown = MagicMock()
    async_operations.connect_signal_handlers = MagicMock()
    async_signal_handlers = MagicMock()

    monkeypatch.setattr(
        "app.controllers.business.structure_business.StructureModel",
        MagicMock(return_value=mock_structure_model),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.StructureService",
        MagicMock(return_value=mock_structure_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.ExportService",
        MagicMock(return_value=mock_export_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.IntegrityService",
        MagicMock(return_value=mock_integrity_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.LoaderService",
        MagicMock(return_value=mock_loader_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.SelectionService",
        MagicMock(return_value=mock_selection_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.ValidationService",
        MagicMock(return_value=mock_validation_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.ImportService",
        MagicMock(return_value=mock_import_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.UtilityService",
        MagicMock(return_value=mock_utility_service),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.AsyncOperations",
        MagicMock(return_value=async_operations),
    )
    monkeypatch.setattr(
        "app.controllers.business.structure_business.AsyncSignalHandlers",
        MagicMock(return_value=async_signal_handlers),
    )

    logic = StructureBusinessLogic(db=db, logger=logging.getLogger("test"))
    return logic, async_operations


def test_structure_business_shutdown_stops_timers_and_pool(
    structure_logic: Tuple[StructureBusinessLogic, MagicMock]
) -> None:
    """`shutdown()` must stop timers, flush caches and close async operations."""
    logic, async_operations = structure_logic

    # Prepare timer state
    assert isinstance(logic._structure_reload_timer, QTimer)
    logic._structure_reload_timer.start(1)
    assert logic._structure_reload_timer.isActive()

    # Ensure cache warm-up to populate cache manager
    logic.cache_manager.set("dummy", object())

    logic.shutdown(timeout=1234)

    assert not logic._structure_reload_timer.isActive()
    async_operations.shutdown.assert_called_once_with(timeout=1234)
    assert logic.cache_manager.get("dummy") is None
*** End Patch
