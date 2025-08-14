from __future__ import annotations

import logging
import os
import warnings
from typing import Optional

_STRICT = os.getenv("OSTEEN_STRICT_IMPORTS", "0") == "1"

if _STRICT:
    raise ImportError(
        "Legacy compatibility module '...structure.compat.legacy' is disabled in strict mode. "
        "Migrate imports to '...structure.structure_business' and stop using legacy adapters."
    )

# Алиасы/адаптеры для обратной совместимости
try:  # pragma: no cover
    from app.controllers.structure_modules import StructureBusinessLogicLegacy  # type: ignore
except Exception:  # noqa: BLE001
    # Фоллбек: используем актуальную бизнес-логику как легаси-совместимый алиас
    from app.controllers.domain.structure.structure_business import StructureBusinessLogic  # type: ignore
    StructureBusinessLogicLegacy = StructureBusinessLogic  # type: ignore
else:
    # Если легаси-класс доступен, алиасим базовый класс для адаптера,
    # чтобы избежать NameError при определении адаптера ниже.
    StructureBusinessLogic = StructureBusinessLogicLegacy  # type: ignore

# Одноразовое предупреждение о депрекации
warnings.warn(
    "Importing legacy compatibility from '...structure.compat.legacy' is deprecated and will be removed. ",
    DeprecationWarning,
    stacklevel=2,
)


class StructureBusinessLogicAdapter(StructureBusinessLogic):  # type: ignore[name-defined]
    """
    Адаптер для полной совместимости со старой версией API.
    Можно дополнять методами по мере необходимости.
    """

    def __init__(self, db, logger: Optional[logging.Logger] = None):
        super().__init__(db, logger)
