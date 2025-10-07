# app/controllers/structure_modules/helpers.py
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable

from ..models.types import StructureItemType

logger = logging.getLogger(__name__)

__all__ = [
    "StructureController",
    "process_item",
]


@runtime_checkable
class StructureController(Protocol):
    """Protocol for structural element controller."""

    def _upsert_and_emit(
        self,
        *,
        item_type: StructureItemType,
        data: Dict[str, Any],
        is_update: bool,
        item_id: Optional[int],
        emit_signal: Callable[..., None],
    ) -> Any:
        """Create/update element with signal emission."""
        ...

    def _emit_signal(self, *args, **kwargs) -> None:
        """Emit signal about event."""
        ...

    def _execute_with_validation(
        self,
        operation: Callable[[], Any],
        data: Dict[str, Any],
        item_type: StructureItemType,
        operation_name: str,
        *,
        require_parent: bool = True,
    ) -> Any:
        """Execute operation with validation."""
        ...


def process_item(
    controller: StructureController,
    data: Dict[str, Any],
    item_type: StructureItemType,
    item_id: Optional[int] = None,
    is_update: bool = False,
    *,
    require_parent: bool = True,
) -> bool:
    """
    General helper for creating/updating structure elements with validation.

    Args:
        controller: Controller implementing StructureController protocol
        data: Data for creating/updating element
        item_type: Type of structural element
        item_id: ID of element to update (optional)
        is_update: True for update, False for creation
        require_parent: Require parent presence (sphere_id/section_id/...).
            Defaults to True. Disable explicitly only if operation allows missing parent.

    Returns:
        bool: True on success, False on failure

    Raises:
        TypeError: If controller doesn't implement required protocol
        ValueError: If incorrect data is passed
    """
    # Check that controller implements required protocol
    if not isinstance(controller, StructureController):
        error_msg = f"Controller must implement StructureController protocol, got {type(controller)}"
        logger.error(error_msg)
        raise TypeError(error_msg)

    # Validate input data
    if not isinstance(data, dict):
        error_msg = f"Argument data must be dict, got {type(data)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if is_update and item_id is None:
        error_msg = "item_id is required for update operations"
        logger.error(error_msg)
        raise ValueError(error_msg)

    def _process_operation():
        """Internal function to perform create/update operation."""
        try:
            return controller._upsert_and_emit(
                item_type=item_type,
                data=data,
                is_update=is_update,
                item_id=item_id,
                emit_signal=controller._emit_signal,
            )
        except Exception as e:
            logger.error("Error in _upsert_and_emit: %s", e)
            raise

    operation_name = "update" if is_update else "creation"

    try:
        result = controller._execute_with_validation(
            _process_operation,
            data,
            item_type,
            operation_name,
            require_parent=require_parent,
        )

        # Явно обрабатываем различные типы результатов
        if result is None:
            logger.warning(
                "Operation %s returned None (item_type=%s, item_id=%s)",
                operation_name,
                getattr(item_type, "name", item_type),
                item_id,
            )
            return False

        # Преобразуем результат в boolean, учитывая различные типы
        success = bool(result)

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            "Element: %s (%s)",
            "successfully updated"
            if is_update and success
            else (
                "not updated"
                if is_update and not success
                else ("successfully created" if success else "not created")
            ),
            getattr(item_type, "name", item_type),
        )

        return success

    except Exception as e:
        logger.exception("Error during %s operation: %s", operation_name, e)
        return False
