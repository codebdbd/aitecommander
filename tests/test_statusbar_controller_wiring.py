from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from app.controllers.system.window_setup.wiring import (
    _connect_statusbar_controller_signals,
)


class _Signal:
    def __init__(self) -> None:
        self._callbacks: list = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


def test_connect_statusbar_controller_signals_wires_all_sources() -> None:
    update_statusbar = Mock()
    database_controller = SimpleNamespace(
        database_connected=_Signal(),
        database_restored=_Signal(),
        favorites_cleared=_Signal(),
    )
    structure_business = SimpleNamespace(
        active_sphere_changed=_Signal(),
        structure_loaded=_Signal(),
        item_added=_Signal(),
        item_updated=_Signal(),
        item_deleted=_Signal(),
        items_batch_deleted=_Signal(),
        section_selected=_Signal(),
        category_selected=_Signal(),
    )
    link_operations = SimpleNamespace(
        links_changed=_Signal(),
        favorites_changed=_Signal(),
        recents_changed=_Signal(),
        link_saved=_Signal(),
        link_deleted=_Signal(),
    )
    top_panels_controller = SimpleNamespace(data_loaded=_Signal())
    window = SimpleNamespace(
        update_statusbar=update_statusbar,
        database_controller=database_controller,
        structure_business=structure_business,
        link_operations=link_operations,
        top_panels_controller=top_panels_controller,
    )

    _connect_statusbar_controller_signals(window)

    database_controller.database_connected.emit(object())
    structure_business.items_batch_deleted.emit("category", [1, 2])
    link_operations.link_deleted.emit({"id": 5})
    top_panels_controller.data_loaded.emit()

    assert update_statusbar.call_count == 4
