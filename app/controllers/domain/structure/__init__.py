# app/controllers/domain/structure/__init__.py

import os
from .structure_business import StructureBusinessLogic

# Совместимость: адаптеры и легаси-алиасы (отключаемы строгим режимом)
_STRICT = os.getenv("OSTEEN_STRICT_IMPORTS", "0") == "1"

if not _STRICT:
    from .compat.legacy import (  # type: ignore
        StructureBusinessLogicAdapter,
        StructureBusinessLogicLegacy,  # type: ignore
    )

# Фабрика для создания фасада
from .wiring.factory import create_structure_business_logic

__all__ = [
    "StructureBusinessLogic",
    "create_structure_business_logic",
]

if not _STRICT:
    __all__ += [
        "StructureBusinessLogicAdapter",
        "StructureBusinessLogicLegacy",
    ]
