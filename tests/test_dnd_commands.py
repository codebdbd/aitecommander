import pytest

from app.utils.ui.dnd.commands import (
    MoveCategoriesCommand,
    MoveCategoryCommand,
    _get_structure_business,
    _require_main,
    _require_structure_business,
)


class DummyEventService:
    def __init__(self) -> None:
        self.replaced_sections: set[int] | None = None

    def replace_touched_sections(self, sections: set[int]) -> None:
        self.replaced_sections = sections


class DummySelection:
    def __init__(self) -> None:
        self.begin_called = False
        self.end_called = False

    def begin_suppress_selection(self) -> None:
        self.begin_called = True

    def end_suppress_selection(self) -> None:
        self.end_called = True


class DummyTree:
    def __init__(self) -> None:
        self.block_calls: list[bool] = []

    def blockSignals(self, value: bool) -> None:  # noqa: N802 - Qt naming
        self.block_calls.append(value)


class DummyStructureUI:
    def __init__(self) -> None:
        self.tree = DummyTree()
        self.selection_handler = DummySelection()


class DummyStructureBusiness:
    def __init__(self) -> None:
        self.categories = {
            1: {"id": 1, "name": "Original", "section_id": 10, "position": 0, "icon_path": ""}
        }
        self.selected_category: int | None = None
        self.begin_called = False
        self.end_called = False
        self.batch_args: tuple[tuple[int, ...], int, int] | None = None
        self.updated_payloads: list[tuple[int, dict[str, object]]] = []
        self.event_service = DummyEventService()

    def get_category_data(self, cid: int) -> dict[str, object] | None:
        return self.categories.get(cid)

    def has_duplicate_category(self, section_id: int, name: str, category_id: int) -> bool:
        return False

    def update_category(self, category_id: int, payload: dict[str, object]) -> dict[str, object]:
        current = self.categories.setdefault(category_id, {"id": category_id})
        current.update(payload)
        self.updated_payloads.append((category_id, payload))
        return current

    def select_category(self, category_id: int) -> None:
        self.selected_category = category_id

    def move_categories_batch(self, ids, section_id: int, base_row: int):
        self.batch_args = (tuple(ids), section_id, base_row)
        return list(ids)

    def begin_batch(self) -> None:
        self.begin_called = True

    def end_batch(self) -> None:
        self.end_called = True


class DummyMainWindow:
    def __init__(self) -> None:
        self.structure_business = DummyStructureBusiness()
        self.structure = DummyStructureUI()


def test_require_main_raises_when_absent():
    with pytest.raises(RuntimeError, match="requires an attached main window"):
        _require_main(None)


def test_get_structure_business_returns_none_when_absent():
    assert _get_structure_business(object()) is None


def test_move_category_prepare_data_uses_structure_business():
    main = DummyMainWindow()
    cmd = MoveCategoryCommand(category_id=1, new_section_id=20, main_window=main)

    cmd._prepare_data()

    assert cmd.old_section_id == 10
    assert cmd.cat_name == "Original"


def test_move_categories_apply_states_updates_payload_and_batch():
    main = DummyMainWindow()
    cmd = MoveCategoriesCommand([1], new_section_id=20, base_row=0, main_window=main)
    cmd._old_states = [
        {"id": 1, "name": "Original", "section_id": 10, "position": 0, "icon_path": ""}
    ]
    cmd._new_states = [
        {"id": 1, "name": "Original", "section_id": 20, "position": 0, "icon_path": ""}
    ]

    cmd._apply_states(cmd._new_states)

    business = main.structure_business
    assert business.categories[1]["section_id"] == 20
    assert business.begin_called is True
    assert business.end_called is True
    assert business.batch_args == ((1,), 20, 0)
    assert business.event_service.replaced_sections == {10, 20}
