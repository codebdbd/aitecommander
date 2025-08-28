# tests/test_require_parent.py
import logging
from typing import Any, Callable, Dict, Optional

from app.controllers.structure_modules.base import (
    DefaultValidationStrategy,
    StructureItemType,
    ValidationError,
)
from app.controllers.structure_modules import helpers


class FakeController:
    """Минимальная реализация протокола StructureController для тестов."""

    def __init__(self) -> None:
        self.valid = DefaultValidationStrategy()
        self.logger = logging.getLogger(__name__)

    def _upsert_and_emit(
        self,
        *,
        item_type: StructureItemType,
        data: Dict[str, Any],
        is_update: bool,
        item_id: Optional[int],
        emit_signal: Callable[..., None],
    ) -> Any:
        # Успех, если до сюда дошли (валидация уже пройдена)
        return True

    def _emit_signal(self, *args, **kwargs) -> None:  # pragma: no cover - не используется
        pass

    def _execute_with_validation(
        self,
        operation: Callable[[], Any],
        data: Dict[str, Any],
        item_type: StructureItemType,
        operation_name: str,
        *,
        require_parent: bool = True,
    ) -> Any:
        # Эмулируем базовую логику: сначала валидация, затем операция
        self.valid.validate(data, item_type, require_parent=require_parent)
        return operation()


def test_update_section_without_parent_fails() -> None:
    ctrl = FakeController()
    data = {"name": "Sec A"}  # нет sphere_id
    ok = helpers.process_item(
        ctrl,
        data,
        StructureItemType.SECTION,
        item_id=1,
        is_update=True,
        require_parent=True,
    )
    assert ok is False


def test_update_category_without_parent_fails() -> None:
    ctrl = FakeController()
    data = {"name": "Cat A"}  # нет section_id
    ok = helpers.process_item(
        ctrl,
        data,
        StructureItemType.CATEGORY,
        item_id=2,
        is_update=True,
        require_parent=True,
    )
    assert ok is False


def test_update_with_parent_succeeds() -> None:
    ctrl = FakeController()
    # Для раздела требуется sphere_id, для категории — section_id
    sec_ok = helpers.process_item(
        ctrl,
        {"name": "Sec A", "sphere_id": 10},
        StructureItemType.SECTION,
        item_id=1,
        is_update=True,
        require_parent=True,
    )
    cat_ok = helpers.process_item(
        ctrl,
        {"name": "Cat A", "section_id": 20},
        StructureItemType.CATEGORY,
        item_id=2,
        is_update=True,
        require_parent=True,
    )
    assert sec_ok is True and cat_ok is True


def test_update_link_without_parent_fails() -> None:
    ctrl = FakeController()
    data = {"name": "Link A"}  # нет category_id
    ok = helpers.process_item(
        ctrl,
        data,
        StructureItemType.LINK,
        item_id=3,
        is_update=True,
        require_parent=True,
    )
    assert ok is False


def test_update_link_with_parent_succeeds() -> None:
    ctrl = FakeController()
    data = {"name": "Link A", "category_id": 30}
    ok = helpers.process_item(
        ctrl,
        data,
        StructureItemType.LINK,
        item_id=3,
        is_update=True,
        require_parent=True,
    )
    assert ok is True
