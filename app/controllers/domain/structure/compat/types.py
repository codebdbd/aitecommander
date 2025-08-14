from __future__ import annotations

from enum import Enum

# Импортируем типы из старого места, если доступны, иначе используем fallback
try:  # pragma: no cover - совместимость
    from app.controllers.structure_modules import ItemTypes, ItemTypeStr, StructureItemType  # type: ignore
except Exception:  # noqa: BLE001
    class ItemTypes:
        SECTION = "section"
        CATEGORY = "category"

    ItemTypeStr = str

    class StructureItemType(Enum):
        SECTION = "section"
        CATEGORY = "category"
