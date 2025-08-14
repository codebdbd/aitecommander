# app/controllers/domain/structure/business.py
"""Лёгкий шлюзовой модуль для обратной совместимости.

Делает ленивый реэкспорт `StructureBusinessLogic`, чтобы не тянуть тяжёлые
зависимости при простом импорте модуля, если класс фактически не используется.
"""

from __future__ import annotations

import os
import warnings
from typing import TYPE_CHECKING

__all__ = ["StructureBusinessLogic"]

_STRICT = os.getenv("OSTEEN_STRICT_IMPORTS", "0") == "1"
_warned = False
_cache = {}

if TYPE_CHECKING:
    # Для подсветки типов и статического анализа — не влияет на рантайм
    from .structure_business import StructureBusinessLogic as StructureBusinessLogic


def __getattr__(name: str):
    global _warned
    if name == "StructureBusinessLogic":
        if _STRICT:
            raise ImportError(
                "Deprecated import path 'app.controllers.domain.structure.business.StructureBusinessLogic' is disabled in strict mode. "
                "Import 'StructureBusinessLogic' from 'app.controllers.domain.structure.structure_business' instead."
            )
        if name in _cache:
            return _cache[name]
        # Одноразовое предупреждение о депрекации
        if not _warned:
            warnings.warn(
                "Importing StructureBusinessLogic via '...structure.business' is deprecated. "
                "Use '...structure.structure_business' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            _warned = True
        from .structure_business import StructureBusinessLogic as _StructureBusinessLogic
        _cache[name] = _StructureBusinessLogic
        return _StructureBusinessLogic
    raise AttributeError(name)
