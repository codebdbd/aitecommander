from __future__ import annotations

import logging
from typing import Optional

from app.models.db import Database
from app.controllers.domain.structure.structure_business import StructureBusinessLogic


def create_structure_business_logic(db: Database, logger: Optional[logging.Logger] = None) -> StructureBusinessLogic:
    """Фабричная функция для создания экземпляра StructureBusinessLogic."""
    return StructureBusinessLogic(db, logger)
