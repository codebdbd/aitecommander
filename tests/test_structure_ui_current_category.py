from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.controllers.ui.structure.structure_ui_controller import StructureUIController


class _StackStub:
    def __init__(self, idx: int) -> None:
        self._idx = idx

    def currentIndex(self) -> int:
        return self._idx


def _build_controller(*, stack_index: int, current_category_id: int | None, tile_current_id: int | None, tree_category_id: int | None) -> StructureUIController:
    controller = StructureUIController.__new__(StructureUIController)
    controller.main = SimpleNamespace(
        stack=_StackStub(stack_index),
        tiles=SimpleNamespace(_current_item_id=tile_current_id),
        current_category_id=current_category_id,
    )
    controller.tree_manager = SimpleNamespace(
        get_current_category_id=lambda: tree_category_id
    )
    controller.tree = SimpleNamespace(currentIndex=lambda: None)
    controller.business = SimpleNamespace(get_first_category_id=lambda: 999)
    return controller


@patch("app.controllers.ui.structure.structure_ui_controller.get_tiles_stack_index", return_value=0)
@patch("app.controllers.ui.structure.structure_ui_controller.get_table_stack_index", return_value=1)
def test_get_current_category_id_prefers_table_state_after_tiles_navigation(
    _table_idx: object,
    _tiles_idx: object,
) -> None:
    controller = _build_controller(
        stack_index=1,
        current_category_id=11817,
        tile_current_id=65,
        tree_category_id=42,
    )

    assert controller.get_current_category_id() == 11817


@patch("app.controllers.ui.structure.structure_ui_controller.get_tiles_stack_index", return_value=0)
@patch("app.controllers.ui.structure.structure_ui_controller.get_table_stack_index", return_value=1)
def test_get_current_category_id_keeps_tiles_priority_when_tiles_active(
    _table_idx: object,
    _tiles_idx: object,
) -> None:
    controller = _build_controller(
        stack_index=0,
        current_category_id=11817,
        tile_current_id=65,
        tree_category_id=42,
    )

    assert controller.get_current_category_id() == 65

