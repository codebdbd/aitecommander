# app/controllers/structure_modules/helpers.py
from __future__ import annotations

from typing import Any, Dict, Optional

from .base import StructureItemType


def process_item(self: Any, data: Dict[str, Any], item_type: StructureItemType,
                 item_id: Optional[int] = None, is_update: bool = False) -> bool:
    """Общий помощник для создания/обновления элементов структуры с валидацией.
    Ожидает, что `self` имеет методы `_upsert_and_emit`, `_emit_signal` и `_execute_with_validation`.
    """
    def _process_operation():
        return self._upsert_and_emit(
            item_type=item_type,
            data=data,
            is_update=is_update,
            item_id=item_id,
            emit_signal=self._emit_signal,
        )

    operation_name = "обновления" if is_update else "создания"
    result = self._execute_with_validation(
        _process_operation,
        data,
        item_type,
        operation_name,
        require_parent=not is_update,
    )
    return result if result is not None else False
